// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

import "@openzeppelin/contracts/token/ERC20/IERC20.sol";
import "@openzeppelin/contracts/token/ERC20/utils/SafeERC20.sol";
import "@openzeppelin/contracts/access/Ownable2Step.sol";
import "@openzeppelin/contracts/utils/ReentrancyGuard.sol";
import "@openzeppelin/contracts/utils/Pausable.sol";

/**
 * @title SpectatorPool (v2)
 * @notice Match-keyed pari-mutuel spectator pot, separate from BoardmanEscrow.
 *         Fans deposit USDC on side 0 (agent A), 1 (agent B) or 2 (draw).
 *         The resolver opens, closes and resolves books; winners pull-claim.
 *         The House custodial path uses depositFor.
 * @dev    v2 hardening over v1 (commit 555a348):
 *         - Every book has a `closeAt` deadline fixed at openBook. Deposits
 *           and seeds revert from closeAt on, and a book can only be resolved
 *           once it is Closed or past closeAt, so nobody can bet on a known
 *           result even if the backend forgets to call close().
 *         - If a book is still unresolved at `closeAt + refundGrace`, anyone
 *           can turn it into a refund, and resolve is no longer possible.
 *         - Fee tiers are hard-capped and versioned; each book snapshots the
 *           schedule id at open.
 *         - Platform fees and creator shares accrue and are pulled, so a
 *           USDC-blacklisted treasury or creator cannot block resolve.
 *         - Each settled book tracks its own `remaining` balance. Claims can
 *           never exceed it, and after `claimWindow` the owner can sweep that
 *           book's remainder (rounding dust, unclaimed winnings) and nothing else.
 *         - Ownable2Step; owner, resolver and treasury are distinct permissions.
 *         - Pause blocks openBook / seed / deposit / depositFor only.
 *         deposit(bytes32,uint256,uint8) is frozen to match spectator_escrow.py.
 *         Assumes a standard ERC-20 with no transfer fee or rebasing (USDC).
 */
contract SpectatorPool is Ownable2Step, ReentrancyGuard, Pausable {
    using SafeERC20 for IERC20;

    // ─── Constants ────────────────────────────────────────────────────────────

    /// @notice Interface version, probed by the backend to pick the right ABI.
    uint8 public constant POOL_VERSION = 2;
    /// @notice Creator pool, in bps of the pot.
    uint16 public constant CREATOR_BPS = 200;
    /// @notice Of the creator pool, the winner's creator gets this % (75),
    ///         the loser's creator the rest. Draws split 50/50.
    uint16 public constant WINNER_CREATOR_PCT = 75;
    uint16 public constant BPS_DENOM = 10_000;
    /// @notice Resolve sentinel for a draw outcome. Draw tickets win the pot.
    int8 public constant DRAW_SIDE = -2;

    /// @notice Hard cap on any percentage fee tier (10%).
    uint16 public constant MAX_PLATFORM_FEE_BPS = 1_000;
    /// @notice Hard cap on the dust-tier flat fee ($1). The fee is also
    ///         clamped to 25% of the pot at resolve.
    uint256 public constant MAX_FLAT_FEE = 1_000_000;
    /// @notice Longest allowed betting window from openBook to closeAt.
    uint256 public constant MAX_BETTING_WINDOW = 7 days;
    /// @notice Bounds for the constructor-set timeouts.
    uint256 public constant MIN_REFUND_GRACE = 1 hours;
    uint256 public constant MAX_REFUND_GRACE = 30 days;
    uint256 public constant MIN_CLAIM_WINDOW = 30 days;
    uint256 public constant MAX_CLAIM_WINDOW = 730 days;

    // ─── Fee schedules (append-only; books reference one by id) ──────────────

    /// @dev pot < tierFlatMax → min(flatFee, pot/4); pot ≤ tierBpsMax → feeBps;
    ///      above → premiumFeeBps.
    struct FeeSchedule {
        uint96 flatFee;
        uint16 feeBps;
        uint16 premiumFeeBps;
        uint96 tierFlatMax;
        uint96 tierBpsMax;
    }

    FeeSchedule[] internal _feeSchedules;

    // ─── Immutable config & roles ────────────────────────────────────────────

    IERC20 public immutable usdc;
    /// @notice Seconds after closeAt when an unresolved book becomes refundable.
    uint256 public immutable refundGrace;
    /// @notice Seconds after settlement before the owner may sweep a book.
    uint256 public immutable claimWindow;

    /// @notice Treasury that receives withdrawn platform fees and sweeps.
    address public feeRecipient;
    /// @notice Backend key that opens, closes, resolves and cancels books.
    address public resolver;

    enum BookStatus {
        None,
        Open,
        Closed,
        Resolved,
        Cancelled
    }

    struct Book {
        bytes32 gameId;
        bytes32 agentA;
        bytes32 agentB;
        address agentWalletA;
        address agentWalletB;
        address creatorA;
        address creatorB;
        address seedPayerA;
        address seedPayerB;
        uint256 potCap;
        uint256 seedA;
        uint256 seedB;
        uint256 totalA;
        uint256 totalB;
        uint256 distributable;
        uint256 fanWin;
        uint8 sideCount;
        int8 winnerSide;
        BookStatus status;
        // draw book, appended so getBook positions 0..18 stay stable.
        address seedPayerDrawA;
        address seedPayerDrawB;
        uint256 seedDrawA;
        uint256 seedDrawB;
        uint256 totalDraw;
        // v2 safety fields, appended so positions 0..23 stay stable.
        uint64 closeAt;        // deposits revert from here; resolve allowed from here
        uint64 settledAt;      // resolve / cancel / expiry time (0 while live)
        uint32 feeScheduleId;  // fee schedule snapshotted at openBook
        bool swept;            // remainder swept after claimWindow
        uint256 remaining;     // USDC still owed to this book's claimants
    }

    mapping(bytes32 => Book) public books;
    mapping(bytes32 => mapping(address => uint256)) public fanDepositA;
    mapping(bytes32 => mapping(address => uint256)) public fanDepositB;
    mapping(bytes32 => mapping(address => uint256)) public fanDepositDraw;
    mapping(bytes32 => mapping(address => bool)) public claimed;

    /// @notice Platform fees and sweeps accrued, withdrawable to feeRecipient.
    uint256 public protocolFees;
    /// @notice Creator shares accrued per creator, withdrawable by the creator.
    mapping(address => uint256) public owed;
    /// @notice Sum of all `owed` balances.
    uint256 public totalOwed;

    // ─── Events ───────────────────────────────────────────────────────────────

    event BookOpened(
        bytes32 indexed matchId,
        bytes32 indexed gameId,
        bytes32 agentA,
        bytes32 agentB,
        address walletA,
        address walletB,
        uint256 potCap
    );
    /// @notice v2 terms bound at openBook.
    event BookTerms(bytes32 indexed matchId, uint64 closeAt, uint32 feeScheduleId);
    event Seeded(bytes32 indexed matchId, uint8 side, address indexed payer, uint256 amount);
    event Deposited(bytes32 indexed matchId, address indexed user, uint8 side, uint256 amount);
    event BookClosed(bytes32 indexed matchId);
    event BookResolved(
        bytes32 indexed matchId,
        int8 winnerSide,
        uint256 pot,
        uint256 platformFee,
        uint256 creatorPool,
        uint256 distributable,
        uint256 fanWin
    );
    /// @notice An unresolved book passed closeAt + refundGrace and was turned
    ///         into a refund by `caller`.
    event BookExpired(bytes32 indexed matchId, address indexed caller);
    event BookSwept(bytes32 indexed matchId, uint256 amount);
    event Claimed(bytes32 indexed matchId, address indexed user, uint256 amount);
    event CreatorAccrued(bytes32 indexed matchId, address indexed creator, uint256 amount);
    event Withdrawn(address indexed to, uint256 amount);
    event FeesWithdrawn(address indexed to, uint256 amount);
    event ResolverUpdated(address indexed oldResolver, address indexed newResolver);
    event FeeRecipientUpdated(address indexed oldRecipient, address indexed newRecipient);
    event SpectatorFeeTiersUpdated(
        uint256 flatFee,
        uint256 feeBps,
        uint256 premiumFeeBps,
        uint256 tierFlatMax,
        uint256 tierBpsMax
    );

    // ─── Errors ───────────────────────────────────────────────────────────────

    error InvalidSide();
    error PotFull();
    error BookNotOpen();
    error BookExists();
    error BookNotFound();
    error AlreadyResolved();
    error AlreadySeeded();
    error NotAgentWallet();
    error NothingToClaim();
    error ZeroAmount();
    error ZeroAddress();
    error DuplicateAgents();
    error NotResolver(address caller);
    error InvalidFeeTiers();
    error InvalidTimeout();
    error InvalidCloseAt(uint256 closeAt);
    error BettingClosed(uint256 closeAt);
    error BookStillOpen(uint256 closeAt);
    error ResolveWindowElapsed();
    error NotExpired(uint256 refundableAt);
    error NotSettled();
    error ClaimWindowActive(uint256 sweepableAt);
    error AlreadySwept();
    error NothingToSweep();
    error InsufficientBookBalance();
    error NothingToWithdraw();
    error RenounceDisabled();

    /// @dev Resolver only. v1 also let the owner through; v2 keeps roles apart.
    modifier onlyResolver() {
        if (msg.sender != resolver) revert NotResolver(msg.sender);
        _;
    }

    // ─── Constructor ──────────────────────────────────────────────────────────

    /**
     * @param _usdc          USDC token.
     * @param _feeRecipient  Treasury for withdrawn platform fees and sweeps.
     * @param _resolver      Backend key that runs books.
     * @param _refundGrace   Seconds after closeAt before an unresolved book
     *                       becomes refundable by anyone (1h..30d).
     * @param _claimWindow   Seconds after settlement before the owner may sweep
     *                       a book's remainder (30d..730d).
     * @dev The deployer becomes owner and should hand ownership to a multisig.
     */
    constructor(
        address _usdc,
        address _feeRecipient,
        address _resolver,
        uint256 _refundGrace,
        uint256 _claimWindow
    ) Ownable(msg.sender) {
        if (_usdc == address(0) || _feeRecipient == address(0) || _resolver == address(0)) {
            revert ZeroAddress();
        }
        if (_refundGrace < MIN_REFUND_GRACE || _refundGrace > MAX_REFUND_GRACE) revert InvalidTimeout();
        if (_claimWindow < MIN_CLAIM_WINDOW || _claimWindow > MAX_CLAIM_WINDOW) revert InvalidTimeout();
        usdc = IERC20(_usdc);
        feeRecipient = _feeRecipient;
        resolver = _resolver;
        refundGrace = _refundGrace;
        claimWindow = _claimWindow;
        // Default schedule: $1 flat under $10, 7% to $1000, 10% above.
        _pushFeeSchedule(1_000_000, 700, 1000, 10_000_000, 1_000_000_000);
        emit ResolverUpdated(address(0), _resolver);
        emit FeeRecipientUpdated(address(0), _feeRecipient);
    }

    // ─── Book lifecycle (resolver) ────────────────────────────────────────────

    /**
     * @notice Open a book for a match.
     * @param closeAt  Betting deadline (unix seconds), in (now, now + MAX_BETTING_WINDOW].
     *                 Set it no later than the moment the result could be known.
     * @dev Snapshots the current fee schedule for this book.
     */
    function openBook(
        bytes32 matchId,
        bytes32 gameId,
        bytes32 agentA,
        bytes32 agentB,
        address agentWalletA,
        address agentWalletB,
        address creatorA,
        address creatorB,
        uint256 potCap,
        uint64 closeAt
    ) external onlyResolver whenNotPaused {
        if (books[matchId].status != BookStatus.None) revert BookExists();
        if (agentA == agentB || agentWalletA == agentWalletB) revert DuplicateAgents();
        if (agentWalletA == address(0) || agentWalletB == address(0)) revert ZeroAddress();
        if (potCap == 0) revert ZeroAmount();
        if (closeAt <= block.timestamp || closeAt > block.timestamp + MAX_BETTING_WINDOW) {
            revert InvalidCloseAt(closeAt);
        }

        Book storage b = books[matchId];
        b.gameId = gameId;
        b.agentA = agentA;
        b.agentB = agentB;
        b.agentWalletA = agentWalletA;
        b.agentWalletB = agentWalletB;
        b.creatorA = creatorA;
        b.creatorB = creatorB;
        b.potCap = potCap;
        b.sideCount = 2;
        b.winnerSide = -1;
        b.status = BookStatus.Open;
        b.closeAt = closeAt;
        uint32 scheduleId = uint32(_feeSchedules.length - 1);
        b.feeScheduleId = scheduleId;

        emit BookOpened(matchId, gameId, agentA, agentB, agentWalletA, agentWalletB, potCap);
        emit BookTerms(matchId, closeAt, scheduleId);
    }

    /// @notice Stop new deposits now (before closeAt). Idempotent.
    function close(bytes32 matchId) external onlyResolver {
        Book storage b = books[matchId];
        if (b.status == BookStatus.None) revert BookNotFound();
        if (b.status == BookStatus.Resolved || b.status == BookStatus.Cancelled) {
            revert AlreadyResolved();
        }
        if (b.status == BookStatus.Closed) return;
        b.status = BookStatus.Closed;
        emit BookClosed(matchId);
    }

    /**
     * @notice Settle a book. winnerSide: 0 = agent A, 1 = agent B, -2 = draw.
     *         Draw tickets win the whole pot; A/B tickets lose.
     * @dev Requires the book to be Closed or past closeAt, and not yet past
     *      closeAt + refundGrace. Works while paused.
     */
    function resolve(bytes32 matchId, int8 winnerSide) external onlyResolver {
        Book storage b = books[matchId];
        if (b.status == BookStatus.None) revert BookNotFound();
        if (b.status == BookStatus.Resolved || b.status == BookStatus.Cancelled) {
            revert AlreadyResolved();
        }
        if (b.status == BookStatus.Open && block.timestamp < b.closeAt) revert BookStillOpen(b.closeAt);
        if (block.timestamp >= uint256(b.closeAt) + refundGrace) revert ResolveWindowElapsed();
        _resolve(matchId, winnerSide, false);
    }

    /// @notice Cancel a live book; everyone can claim their stake back.
    ///         Allowed at any time before settlement (it reveals nothing).
    function cancel(bytes32 matchId) external onlyResolver {
        Book storage b = books[matchId];
        if (b.status == BookStatus.None) revert BookNotFound();
        if (b.status == BookStatus.Resolved) revert AlreadyResolved();
        if (b.status == BookStatus.Cancelled) return;
        _resolve(matchId, -1, true);
    }

    /// @notice Permissionless: once closeAt + refundGrace has passed without a
    ///         resolve, turn the book into a full refund. Works while paused.
    function refundExpired(bytes32 matchId) external {
        Book storage b = books[matchId];
        if (b.status == BookStatus.None) revert BookNotFound();
        if (b.status == BookStatus.Resolved || b.status == BookStatus.Cancelled) {
            revert AlreadyResolved();
        }
        uint256 at = uint256(b.closeAt) + refundGrace;
        if (block.timestamp < at) revert NotExpired(at);
        _markRefund(matchId, b, true, _pot(b));
        emit BookExpired(matchId, msg.sender);
    }

    // ─── Money in ─────────────────────────────────────────────────────────────

    /// @notice Agent wallet seeds its own side (0/1) or the draw side (2), once each.
    function seed(bytes32 matchId, uint8 side, uint256 amount) external whenNotPaused nonReentrant {
        if (side > 2) revert InvalidSide();
        if (amount == 0) revert ZeroAmount();
        Book storage b = books[matchId];
        _requireBetting(b);
        if (side == 2) {
            // Draw book: either agent may seed; each may seed once.
            if (msg.sender != b.agentWalletA && msg.sender != b.agentWalletB) revert NotAgentWallet();
            if (msg.sender == b.agentWalletA) {
                if (b.seedPayerDrawA != address(0)) revert AlreadySeeded();
                b.seedPayerDrawA = msg.sender;
                b.seedDrawA = amount;
            } else {
                if (b.seedPayerDrawB != address(0)) revert AlreadySeeded();
                b.seedPayerDrawB = msg.sender;
                b.seedDrawB = amount;
            }
            b.totalDraw += amount;
            if (_pot(b) > b.potCap) {
                revert PotFull();
            }
            usdc.safeTransferFrom(msg.sender, address(this), amount);
            emit Seeded(matchId, side, msg.sender, amount);
            return;
        }
        address expected = side == 0 ? b.agentWalletA : b.agentWalletB;
        if (msg.sender != expected) revert NotAgentWallet();
        if (side == 0) {
            if (b.seedPayerA != address(0)) revert AlreadySeeded();
        } else if (b.seedPayerB != address(0)) {
            revert AlreadySeeded();
        }
        if (_pot(b) + amount > b.potCap) revert PotFull();

        if (side == 0) {
            b.seedPayerA = msg.sender;
            b.seedA = amount;
            b.totalA += amount;
        } else {
            b.seedPayerB = msg.sender;
            b.seedB = amount;
            b.totalB += amount;
        }
        usdc.safeTransferFrom(msg.sender, address(this), amount);
        emit Seeded(matchId, side, msg.sender, amount);
    }

    /// @notice Frozen ABI: deposit(bytes32,uint256,uint8). Fan signs; USDC from msg.sender.
    ///         side: 0 = agent A, 1 = agent B, 2 = draw. Reverts from closeAt on.
    function deposit(bytes32 matchId, uint256 amount, uint8 side) external whenNotPaused nonReentrant {
        _creditDeposit(matchId, msg.sender, amount, side);
        usdc.safeTransferFrom(msg.sender, address(this), amount);
        emit Deposited(matchId, msg.sender, side, amount);
    }

    /// @notice House custodial path. Resolver pulls USDC from itself and credits `user`.
    function depositFor(bytes32 matchId, address user, uint256 amount, uint8 side)
        external
        onlyResolver
        whenNotPaused
        nonReentrant
    {
        if (user == address(0)) revert ZeroAddress();
        _creditDeposit(matchId, user, amount, side);
        usdc.safeTransferFrom(msg.sender, address(this), amount);
        emit Deposited(matchId, user, side, amount);
    }

    // ─── Money out (pull) ─────────────────────────────────────────────────────

    /// @notice Claim winnings (or a refund) from a settled book. Works while paused.
    function claim(bytes32 matchId) external nonReentrant {
        uint256 amt = claimable(matchId, msg.sender);
        if (amt == 0) revert NothingToClaim();
        Book storage b = books[matchId];
        if (amt > b.remaining) revert InsufficientBookBalance(); // invariant guard
        claimed[matchId][msg.sender] = true;
        b.remaining -= amt;
        usdc.safeTransfer(msg.sender, amt);
        emit Claimed(matchId, msg.sender, amt);
    }

    /// @notice Creator withdraws accrued creator shares (to itself only).
    function withdraw() external nonReentrant {
        uint256 amt = owed[msg.sender];
        if (amt == 0) revert NothingToWithdraw();
        owed[msg.sender] = 0;
        totalOwed -= amt;
        usdc.safeTransfer(msg.sender, amt);
        emit Withdrawn(msg.sender, amt);
    }

    /// @notice Send accrued platform fees and sweeps to the treasury.
    ///         Callable by anyone; the destination is always feeRecipient.
    function withdrawFees() external nonReentrant {
        uint256 amt = protocolFees;
        if (amt == 0) revert NothingToWithdraw();
        protocolFees = 0;
        address to = feeRecipient;
        usdc.safeTransfer(to, amt);
        emit FeesWithdrawn(to, amt);
    }

    // ─── Admin (owner = multisig) ─────────────────────────────────────────────

    /**
     * @notice After `claimWindow`, move one settled book's unclaimed remainder
     *         (rounding dust and unclaimed winnings or refunds) to protocolFees.
     * @dev Strictly bounded by that book's `remaining`; claims on the book
     *      stop after a sweep.
     */
    function sweep(bytes32 matchId) external onlyOwner {
        Book storage b = books[matchId];
        if (b.status != BookStatus.Resolved && b.status != BookStatus.Cancelled) revert NotSettled();
        if (b.swept) revert AlreadySwept();
        uint256 at = uint256(b.settledAt) + claimWindow;
        if (block.timestamp < at) revert ClaimWindowActive(at);
        uint256 amt = b.remaining;
        if (amt == 0) revert NothingToSweep();
        b.remaining = 0;
        b.swept = true;
        protocolFees += amt;
        emit BookSwept(matchId, amt);
    }

    /// @notice Owner rotates the resolver. Emits ResolverUpdated.
    function setResolver(address _resolver) external onlyOwner {
        if (_resolver == address(0)) revert ZeroAddress();
        emit ResolverUpdated(resolver, _resolver);
        resolver = _resolver;
    }

    /// @notice Owner rotates the treasury; accrued fees go to the new one on
    ///         the next withdrawFees. Emits FeeRecipientUpdated.
    function setFeeRecipient(address _feeRecipient) external onlyOwner {
        if (_feeRecipient == address(0)) revert ZeroAddress();
        emit FeeRecipientUpdated(feeRecipient, _feeRecipient);
        feeRecipient = _feeRecipient;
    }

    /**
     * @notice Add a fee schedule for books opened from now on.
     * @dev Requirements: feeBps ≤ premiumFeeBps ≤ MAX_PLATFORM_FEE_BPS,
     *      flatFee ≤ MAX_FLAT_FEE, tierFlatMax ≤ tierBpsMax ≤ uint96 max.
     *      Open books keep the schedule they were opened with.
     */
    function setSpectatorFeeTiers(
        uint256 _flatFee,
        uint16 _feeBps,
        uint16 _premiumFeeBps,
        uint256 _tierFlatMax,
        uint256 _tierBpsMax
    ) external onlyOwner {
        if (_premiumFeeBps < _feeBps) revert InvalidFeeTiers();
        if (_premiumFeeBps > MAX_PLATFORM_FEE_BPS) revert InvalidFeeTiers();
        if (_flatFee > MAX_FLAT_FEE) revert InvalidFeeTiers();
        if (_tierBpsMax < _tierFlatMax || _tierBpsMax > type(uint96).max) revert InvalidFeeTiers();
        _pushFeeSchedule(_flatFee, _feeBps, _premiumFeeBps, _tierFlatMax, _tierBpsMax);
        emit SpectatorFeeTiersUpdated(_flatFee, _feeBps, _premiumFeeBps, _tierFlatMax, _tierBpsMax);
    }

    /// @notice Stop new books and money in. Settlement and money out keep working.
    function pause() external onlyOwner {
        _pause();
    }

    function unpause() external onlyOwner {
        _unpause();
    }

    /// @notice Disabled: the contract is immutable, so losing the owner would
    ///         freeze role rotation, fee governance and sweeps forever.
    function renounceOwnership() public view override onlyOwner {
        revert RenounceDisabled();
    }

    // ─── Views ────────────────────────────────────────────────────────────────

    /// @notice Full book record (positions 0..23 as in v1, v2 fields appended).
    function getBook(bytes32 matchId) external view returns (Book memory) {
        return books[matchId];
    }

    /// @notice True while deposits and seeds are accepted.
    function isBettingOpen(bytes32 matchId) external view returns (bool) {
        Book storage b = books[matchId];
        return b.status == BookStatus.Open && block.timestamp < b.closeAt;
    }

    function fanDepositOf(bytes32 matchId, address user, uint8 side) public view returns (uint256) {
        if (side > 1) revert InvalidSide();
        return side == 0 ? fanDepositA[matchId][user] : fanDepositB[matchId][user];
    }

    function seedOf(bytes32 matchId, address user) public view returns (uint256 amt) {
        Book storage b = books[matchId];
        if (user == b.seedPayerA) amt += b.seedA;
        if (user == b.seedPayerB) amt += b.seedB;
        if (user == b.seedPayerDrawA) amt += b.seedDrawA;
        if (user == b.seedPayerDrawB) amt += b.seedDrawB;
    }

    /// @notice What `user` can claim now. Winners get dep * distributable / fanWin
    ///         (rounded down, so the sum never exceeds distributable); refund
    ///         books return every deposit and seed. Zero after a sweep.
    function claimable(bytes32 matchId, address user) public view returns (uint256) {
        if (claimed[matchId][user]) return 0;
        Book storage b = books[matchId];
        if (b.swept) return 0;
        if (b.status == BookStatus.Resolved && b.winnerSide >= 0 && b.fanWin > 0) {
            uint256 dep = fanDepositOf(matchId, user, uint8(uint8(b.winnerSide)));
            return (dep * b.distributable) / b.fanWin;
        }
        if (b.status == BookStatus.Resolved && b.winnerSide == DRAW_SIDE && b.fanWin > 0) {
            uint256 dep = fanDepositDraw[matchId][user];
            return (dep * b.distributable) / b.fanWin;
        }
        if (
            (b.status == BookStatus.Resolved || b.status == BookStatus.Cancelled)
                && (b.winnerSide < 0 || b.fanWin == 0)
        ) {
            return fanDepositA[matchId][user]
                + fanDepositB[matchId][user]
                + fanDepositDraw[matchId][user]
                + seedOf(matchId, user);
        }
        return 0;
    }

    /// @notice Number of fee schedules ever set (the current one is count - 1).
    function feeScheduleCount() external view returns (uint256) {
        return _feeSchedules.length;
    }

    function feeSchedule(uint256 id) external view returns (FeeSchedule memory) {
        return _feeSchedules[id];
    }

    /// @notice Platform fee a pot of `pot` would pay under schedule `id`.
    function quotePlatformFee(uint256 id, uint256 pot) external view returns (uint256) {
        return _platformFee(_feeSchedules[id], pot);
    }

    // v1-compatible getters for the current schedule.
    function PLATFORM_FEE_BPS() external view returns (uint16) {
        return _current().feeBps;
    }

    function PREMIUM_FEE_BPS() external view returns (uint16) {
        return _current().premiumFeeBps;
    }

    function FLAT_FEE() external view returns (uint256) {
        return _current().flatFee;
    }

    function TIER_FLAT_MAX() external view returns (uint256) {
        return _current().tierFlatMax;
    }

    function TIER_BPS_MAX() external view returns (uint256) {
        return _current().tierBpsMax;
    }

    function contractBalance() external view returns (uint256) {
        return usdc.balanceOf(address(this));
    }

    // ─── Internals ────────────────────────────────────────────────────────────

    function _current() internal view returns (FeeSchedule storage) {
        return _feeSchedules[_feeSchedules.length - 1];
    }

    function _pushFeeSchedule(
        uint256 flatFee,
        uint16 feeBps,
        uint16 premiumFeeBps,
        uint256 tierFlatMax,
        uint256 tierBpsMax
    ) internal {
        _feeSchedules.push(
            FeeSchedule({
                flatFee: uint96(flatFee),
                feeBps: feeBps,
                premiumFeeBps: premiumFeeBps,
                tierFlatMax: uint96(tierFlatMax),
                tierBpsMax: uint96(tierBpsMax)
            })
        );
    }

    function _requireBetting(Book storage b) internal view {
        if (b.status != BookStatus.Open) revert BookNotOpen();
        if (block.timestamp >= b.closeAt) revert BettingClosed(b.closeAt);
    }

    function _pot(Book storage b) internal view returns (uint256) {
        return b.totalA + b.totalB + b.totalDraw;
    }

    /// @dev Dust pots pay min(flatFee, 25% of pot); the result never exceeds the pot.
    function _platformFee(FeeSchedule memory s, uint256 pot) internal pure returns (uint256) {
        if (pot == 0) return 0;
        if (pot < s.tierFlatMax) {
            uint256 dustCap = pot / 4;
            return s.flatFee > dustCap ? dustCap : s.flatFee;
        }
        if (pot <= s.tierBpsMax) return (pot * s.feeBps) / BPS_DENOM;
        return (pot * s.premiumFeeBps) / BPS_DENOM;
    }

    function _creditDeposit(bytes32 matchId, address user, uint256 amount, uint8 side) internal {
        if (side > 2) revert InvalidSide();
        if (amount == 0) revert ZeroAmount();
        Book storage b = books[matchId];
        _requireBetting(b);
        if (_pot(b) + amount > b.potCap) revert PotFull();
        if (side == 0) {
            fanDepositA[matchId][user] += amount;
            b.totalA += amount;
        } else if (side == 1) {
            fanDepositB[matchId][user] += amount;
            b.totalB += amount;
        } else {
            fanDepositDraw[matchId][user] += amount;
            b.totalDraw += amount;
        }
    }

    /// @dev Callers have already checked the book exists and is unsettled.
    function _resolve(bytes32 matchId, int8 winnerSide, bool asCancel) internal {
        Book storage b = books[matchId];
        if (winnerSide < -2 || winnerSide > 1) revert InvalidSide();

        uint256 pot = _pot(b);
        if ((winnerSide < 0 && winnerSide != DRAW_SIDE) || pot == 0) {
            _markRefund(matchId, b, asCancel, pot);
            return;
        }

        uint256 fanWin_;
        if (winnerSide == DRAW_SIDE) {
            // Draw outcome: draw tickets win the whole pot; A/B tickets lose.
            fanWin_ = b.totalDraw - b.seedDrawA - b.seedDrawB;
        } else {
            fanWin_ = winnerSide == 0 ? b.totalA - b.seedA : b.totalB - b.seedB;
        }
        if (fanWin_ == 0) {
            _markRefund(matchId, b, asCancel, pot);
            return;
        }

        uint256 platformFee = _platformFee(_feeSchedules[b.feeScheduleId], pot);
        uint256 creatorPool = (pot * CREATOR_BPS) / BPS_DENOM;
        // Never take more than the pot. Unreachable under the caps (≤ 25% + 2%),
        // kept as a guard so `distributable` can never underflow.
        if (platformFee + creatorPool > pot) {
            if (creatorPool > pot) creatorPool = pot;
            platformFee = pot - creatorPool;
        }
        uint256 distributable_ = pot - platformFee - creatorPool;

        b.winnerSide = winnerSide;
        b.distributable = distributable_;
        b.fanWin = fanWin_;
        b.status = BookStatus.Resolved;
        b.settledAt = uint64(block.timestamp);
        b.remaining = distributable_;

        protocolFees += platformFee;
        if (creatorPool > 0) {
            _accrueCreators(matchId, b, creatorPool, winnerSide);
        }

        emit BookResolved(matchId, winnerSide, pot, platformFee, creatorPool, distributable_, fanWin_);
    }

    /// @notice Winner's creator accrues WINNER_CREATOR_PCT of the creator pool,
    ///         the other creator the rest; draws split 50/50. A zero creator
    ///         address falls back to protocolFees. Nothing is transferred here.
    function _accrueCreators(bytes32 matchId, Book storage b, uint256 creatorPool, int8 winnerSide) internal {
        address winCreator = winnerSide == 1 ? b.creatorB : b.creatorA;
        address loseCreator = winnerSide == 1 ? b.creatorA : b.creatorB;
        uint256 winShare = winnerSide == DRAW_SIDE
            ? creatorPool / 2
            : (creatorPool * WINNER_CREATOR_PCT) / 100;
        _accrueCreator(matchId, winCreator, winShare);
        _accrueCreator(matchId, loseCreator, creatorPool - winShare);
    }

    function _accrueCreator(bytes32 matchId, address creator, uint256 amount) internal {
        if (amount == 0) return;
        if (creator == address(0)) {
            protocolFees += amount;
            return;
        }
        owed[creator] += amount;
        totalOwed += amount;
        emit CreatorAccrued(matchId, creator, amount);
    }

    function _markRefund(bytes32 matchId, Book storage b, bool asCancel, uint256 pot) internal {
        b.winnerSide = -1;
        b.distributable = 0;
        b.fanWin = 0;
        b.status = asCancel ? BookStatus.Cancelled : BookStatus.Resolved;
        b.settledAt = uint64(block.timestamp);
        b.remaining = pot;
        emit BookResolved(matchId, -1, pot, 0, 0, 0, 0);
    }
}
