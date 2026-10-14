// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

import "@openzeppelin/contracts/token/ERC20/IERC20.sol";
import "@openzeppelin/contracts/token/ERC20/utils/SafeERC20.sol";
import "@openzeppelin/contracts/access/Ownable2Step.sol";
import "@openzeppelin/contracts/utils/ReentrancyGuard.sol";
import "@openzeppelin/contracts/utils/Pausable.sol";
import "@openzeppelin/contracts/utils/cryptography/ECDSA.sol";

/**
 * @title BoardmanEscrow (v2)
 * @notice Dual-lock USDC escrow for Boardman skill matches. Player1 stakes with
 *         a resolver-signed permit that binds the opponent, the stake and a
 *         deadline; only that opponent can join. The resolver settles the
 *         winner or cancels; if the resolver disappears, anyone can refund the
 *         stakes after a fixed timeout.
 * @dev    v2 hardening over v1 (commit 555a348):
 *         - Ownable2Step; owner, resolver and treasury (feeRecipient) are
 *           distinct permissions. The owner can no longer act as resolver.
 *         - Hard fee caps; the platform fee is snapshotted at create and can
 *           never exceed the pot.
 *         - Liveness: OPEN past `openTimeout` and LOCKED/DISPUTED past
 *           `lockTimeout` are refundable by anyone.
 *         - Fees accrue and are pulled to the treasury. Player payouts are
 *           pushed, but fall back to a withdrawable credit if the transfer
 *           fails (e.g. a USDC-blacklisted recipient), so settlement of one
 *           match can never be blocked by a single address.
 *         - Pause stops new money coming in (create/join) only; resolve,
 *           cancel, refunds and withdrawals keep working while paused.
 *         Assumes a standard ERC-20 with no transfer fee or rebasing (USDC).
 *         EIP-712 is implemented inline (instead of OZ EIP712) so the contract
 *         builds with solc 0.8.20 (evm paris) like v1; OZ 5.6 EIP712 needs
 *         0.8.24 and MCOPY (cancun).
 */
contract BoardmanEscrow is Ownable2Step, ReentrancyGuard, Pausable {
    using SafeERC20 for IERC20;

    // ─── Constants ────────────────────────────────────────────────────────────

    /// @notice Interface version, probed by the backend to pick the right ABI.
    uint8 public constant ESCROW_VERSION = 2;

    /// @notice Minimum stake per player ($2 USDC).
    uint256 public constant MIN_STAKE = 2e6;
    /// @notice Maximum stake per player ($10,000 USDC).
    uint256 public constant MAX_STAKE = 10_000e6;
    /// @notice Default flat-tier boundary (stakes below this pay the flat fee).
    uint256 public constant TIER_FLAT_MAX = 5e6;
    /// @notice Default mid-tier boundary (stakes up to this pay FEE_BPS).
    uint256 public constant TIER_BPS_MAX = 500e6;
    uint256 public constant BPS_DENOM = 10_000;

    /// @notice Hard cap on any percentage fee tier (10%).
    uint256 public constant MAX_FEE_BPS = 1_000;
    /// @notice Hard cap on the flat fee per player: 25% of the minimum stake,
    ///         so the flat tier can never take more than a quarter of a pot.
    uint256 public constant MAX_FLAT_FEE_PER_PLAYER = MIN_STAKE / 4;

    /// @notice Bounds for the constructor-set timeouts.
    uint256 public constant MIN_OPEN_TIMEOUT = 1 hours;
    uint256 public constant MAX_OPEN_TIMEOUT = 7 days;
    uint256 public constant MIN_LOCK_TIMEOUT = 1 days;
    uint256 public constant MAX_LOCK_TIMEOUT = 30 days;

    /// @notice EIP-712 typehash of the resolver permit that authorises createMatch.
    bytes32 public constant CREATE_MATCH_TYPEHASH = keccak256(
        "CreateMatch(bytes32 matchId,address player1,address player2,uint256 stake,uint256 deadline)"
    );

    bytes32 private constant _DOMAIN_TYPEHASH = keccak256(
        "EIP712Domain(string name,string version,uint256 chainId,address verifyingContract)"
    );
    bytes32 private constant _NAME_HASH = keccak256("BoardmanEscrow");
    bytes32 private constant _VERSION_HASH = keccak256("2");

    // ─── Fee state (owner-settable within caps; snapshotted per match) ───────

    /// @notice Mid-tier fee in bps (default 7%). Capped at MAX_FEE_BPS.
    uint256 public FEE_BPS = 700;
    /// @notice Premium-tier fee in bps (default 10%). Capped at MAX_FEE_BPS.
    uint256 public PREMIUM_FEE_BPS = 1000;
    /// @notice Flat fee per player for stakes below the flat boundary.
    uint256 public FLAT_FEE_PER_PLAYER = 500_000;
    /// @notice Active flat-tier boundary.
    uint256 public TIER_FLAT_MAX_OVERRIDE = 5e6;
    /// @notice Active mid-tier boundary.
    uint256 public TIER_BPS_MAX_OVERRIDE = 500e6;

    // ─── Immutable config ─────────────────────────────────────────────────────

    IERC20 public immutable usdc;
    /// @notice Seconds after createdAt when an unjoined match becomes refundable.
    uint256 public immutable openTimeout;
    /// @notice Seconds after lockedAt when an unresolved match becomes refundable
    ///         and the resolver can no longer resolve it.
    uint256 public immutable lockTimeout;
    bytes32 private immutable _cachedDomainSeparator;
    uint256 private immutable _cachedChainId;

    // ─── Roles ────────────────────────────────────────────────────────────────

    /// @notice Treasury that receives accrued platform fees.
    address public feeRecipient;
    /// @notice Backend key that signs create permits and settles matches.
    address public resolver;

    // ─── Match state ──────────────────────────────────────────────────────────

    enum MatchStatus {
        OPEN,       // creator staked, waiting for the bound player2
        LOCKED,     // both staked, match in progress
        DISPUTED,   // conflict flagged, mediator deciding off-chain
        RESOLVED,   // winner paid out
        CANCELLED   // refunded
    }

    /// @dev Packed into 3 slots. player2 is bound at create (v1 set it on join).
    struct Match {
        address player1;
        address player2;
        uint96 stakePerPlayer;
        MatchStatus status;
        uint40 createdAt;
        uint40 lockedAt;
        uint96 platformFee; // total fee on the pot, snapshotted at create
    }

    mapping(bytes32 => Match) internal _matches;

    /// @notice Lifetime platform fees earned.
    uint256 public totalFeesCollected;
    /// @notice Platform fees earned but not yet withdrawn to the treasury.
    uint256 public accruedFees;
    /// @notice Stakes currently held for OPEN / LOCKED / DISPUTED matches.
    uint256 public totalLocked;
    /// @notice Payouts whose push transfer failed, withdrawable by the recipient.
    mapping(address => uint256) public owed;
    /// @notice Sum of all `owed` balances.
    uint256 public totalOwed;

    // ─── Events ───────────────────────────────────────────────────────────────

    event MatchCreated(bytes32 indexed matchId, address indexed player1, uint256 stake);
    /// @notice Terms bound at create: opponent, fee snapshot, permit deadline.
    event MatchTerms(bytes32 indexed matchId, address indexed player2, uint256 platformFee, uint256 permitDeadline);
    event MatchJoined(bytes32 indexed matchId, address indexed player2);
    event MatchLocked(bytes32 indexed matchId);
    event MatchResolved(bytes32 indexed matchId, address indexed winner, uint256 payout, uint256 fee);
    event MatchDisputed(bytes32 indexed matchId);
    event MatchCancelled(bytes32 indexed matchId);
    /// @notice A timed-out match was refunded by `caller` (emitted with MatchCancelled).
    event MatchExpired(bytes32 indexed matchId, address indexed caller);
    event PayoutDeferred(address indexed to, uint256 amount);
    event Withdrawn(address indexed to, uint256 amount);
    event FeesWithdrawn(address indexed to, uint256 amount);
    event ResolverUpdated(address indexed oldResolver, address indexed newResolver);
    event FeeRecipientUpdated(address indexed oldRecipient, address indexed newRecipient);
    event FeeTiersUpdated(
        uint256 flatFeePerPlayer,
        uint256 feeBps,
        uint256 premiumFeeBps,
        uint256 tierFlatMax,
        uint256 tierBpsMax
    );

    // ─── Errors ───────────────────────────────────────────────────────────────

    error MatchAlreadyExists();
    error MatchNotFound();
    error InvalidStatus(MatchStatus expected, MatchStatus actual);
    error NotPlayer(address caller);
    error NotResolver(address caller);
    error InvalidWinner(address winner);
    error StakeExceedsMax(uint256 stake);
    error StakeBelowMin(uint256 stake);
    error InvalidFeeTiers();
    error InvalidTimeout();
    error ZeroStake();
    error ZeroAddress();
    error PermitExpired(uint256 deadline);
    error InvalidPermit();
    error MatchExpiredForJoin();
    error ResolveWindowElapsed();
    error NotExpired(uint256 refundableAt);
    error NothingToWithdraw();
    error RenounceDisabled();

    // ─── Modifiers ────────────────────────────────────────────────────────────

    /// @dev Resolver only. v1 also let the owner through; v2 keeps roles apart.
    modifier onlyResolver() {
        if (msg.sender != resolver) revert NotResolver(msg.sender);
        _;
    }

    modifier matchExists(bytes32 matchId) {
        if (_matches[matchId].player1 == address(0)) revert MatchNotFound();
        _;
    }

    // ─── Constructor ──────────────────────────────────────────────────────────

    /**
     * @param _usdc          USDC token.
     * @param _feeRecipient  Treasury that receives withdrawn platform fees.
     * @param _resolver      Backend key: signs create permits, settles matches.
     * @param _openTimeout   Seconds an OPEN match waits for player2 (1h..7d).
     * @param _lockTimeout   Seconds a LOCKED match waits for the resolver (1d..30d).
     * @dev The deployer becomes owner and should hand ownership to a multisig
     *      with transferOwnership + acceptOwnership.
     */
    constructor(
        address _usdc,
        address _feeRecipient,
        address _resolver,
        uint256 _openTimeout,
        uint256 _lockTimeout
    ) Ownable(msg.sender) {
        if (_usdc == address(0) || _feeRecipient == address(0) || _resolver == address(0))
            revert ZeroAddress();
        if (_openTimeout < MIN_OPEN_TIMEOUT || _openTimeout > MAX_OPEN_TIMEOUT) revert InvalidTimeout();
        if (_lockTimeout < MIN_LOCK_TIMEOUT || _lockTimeout > MAX_LOCK_TIMEOUT) revert InvalidTimeout();
        usdc = IERC20(_usdc);
        feeRecipient = _feeRecipient;
        resolver = _resolver;
        openTimeout = _openTimeout;
        lockTimeout = _lockTimeout;
        _cachedChainId = block.chainid;
        _cachedDomainSeparator = _buildDomainSeparator();
        emit ResolverUpdated(address(0), _resolver);
        emit FeeRecipientUpdated(address(0), _feeRecipient);
    }

    // ─── Player actions ───────────────────────────────────────────────────────

    /**
     * @notice Player1 creates a match against a bound opponent and stakes USDC.
     * @param matchId      Match id (sha256 of the backend match id).
     * @param player2      The only address allowed to join.
     * @param stake        Stake per player (6 decimals).
     * @param deadline     Permit expiry (unix seconds).
     * @param resolverSig  Resolver EIP-712 signature over
     *                     CreateMatch(matchId, msg.sender, player2, stake, deadline).
     *                     65-byte ECDSA signature from the resolver EOA
     *                     (OZ ECDSA rejects malleable high-s signatures).
     * @dev The fee for this match is computed from the current tiers and
     *      frozen here; later tier changes do not affect it. Replay is
     *      impossible because a matchId can only be created once.
     */
    function createMatch(
        bytes32 matchId,
        address player2,
        uint256 stake,
        uint256 deadline,
        bytes calldata resolverSig
    ) external nonReentrant whenNotPaused {
        if (stake == 0) revert ZeroStake();
        if (stake < MIN_STAKE) revert StakeBelowMin(stake);
        if (stake > MAX_STAKE) revert StakeExceedsMax(stake);
        if (player2 == address(0)) revert ZeroAddress();
        if (player2 == msg.sender) revert NotPlayer(player2);
        if (block.timestamp > deadline) revert PermitExpired(deadline);
        if (_matches[matchId].player1 != address(0)) revert MatchAlreadyExists();

        bytes32 digest = hashCreateMatch(matchId, msg.sender, player2, stake, deadline);
        (address signer, ECDSA.RecoverError err, ) = ECDSA.tryRecover(digest, resolverSig);
        if (err != ECDSA.RecoverError.NoError || signer != resolver) revert InvalidPermit();

        uint256 fee = _platformFee(stake * 2);

        _matches[matchId] = Match({
            player1: msg.sender,
            player2: player2,
            stakePerPlayer: uint96(stake),
            status: MatchStatus.OPEN,
            createdAt: uint40(block.timestamp),
            lockedAt: 0,
            platformFee: uint96(fee)
        });
        totalLocked += stake;

        usdc.safeTransferFrom(msg.sender, address(this), stake);

        emit MatchCreated(matchId, msg.sender, stake);
        emit MatchTerms(matchId, player2, fee, deadline);
    }

    /**
     * @notice The bound player2 joins an OPEN match and stakes the same amount.
     * @dev Reverts once the match is older than `openTimeout`; from then on
     *      the only way out is the player1 refund.
     */
    function joinMatch(bytes32 matchId)
        external
        nonReentrant
        whenNotPaused
        matchExists(matchId)
    {
        Match storage m = _matches[matchId];
        if (m.status != MatchStatus.OPEN) revert InvalidStatus(MatchStatus.OPEN, m.status);
        if (msg.sender != m.player2) revert NotPlayer(msg.sender);
        if (block.timestamp >= uint256(m.createdAt) + openTimeout) revert MatchExpiredForJoin();

        m.status = MatchStatus.LOCKED;
        m.lockedAt = uint40(block.timestamp);
        uint256 stake = m.stakePerPlayer;
        totalLocked += stake;

        usdc.safeTransferFrom(msg.sender, address(this), stake);

        emit MatchJoined(matchId, msg.sender);
        emit MatchLocked(matchId);
    }

    /**
     * @notice Permissionless refund of a timed-out match.
     *         OPEN for `openTimeout` → player1 refunded.
     *         LOCKED/DISPUTED for `lockTimeout` → both players refunded.
     * @dev Works while paused. Refunds go only to the recorded players.
     */
    function refundExpired(bytes32 matchId) external nonReentrant matchExists(matchId) {
        Match storage m = _matches[matchId];
        uint256 at = _refundableAt(m);
        if (at == 0) revert InvalidStatus(MatchStatus.LOCKED, m.status);
        if (block.timestamp < at) revert NotExpired(at);
        _cancel(matchId, m);
        emit MatchExpired(matchId, msg.sender);
    }

    /// @notice Withdraw a payout that could not be pushed at settlement.
    function withdraw() external nonReentrant {
        uint256 amt = owed[msg.sender];
        if (amt == 0) revert NothingToWithdraw();
        owed[msg.sender] = 0;
        totalOwed -= amt;
        usdc.safeTransfer(msg.sender, amt);
        emit Withdrawn(msg.sender, amt);
    }

    /// @notice Send accrued platform fees to the treasury. Callable by anyone;
    ///         the destination is always the current feeRecipient.
    function withdrawFees() external nonReentrant {
        uint256 amt = accruedFees;
        if (amt == 0) revert NothingToWithdraw();
        accruedFees = 0;
        address to = feeRecipient;
        usdc.safeTransfer(to, amt);
        emit FeesWithdrawn(to, amt);
    }

    // ─── Resolver actions ─────────────────────────────────────────────────────

    /**
     * @notice Pay the winner `2*stake - fee`, using the fee snapshotted at create.
     * @dev Only before `lockedAt + lockTimeout`; after that the match is
     *      refundable and can no longer be resolved.
     */
    function resolveMatch(bytes32 matchId, address winner)
        external
        nonReentrant
        onlyResolver
        matchExists(matchId)
    {
        Match storage m = _matches[matchId];
        if (m.status != MatchStatus.LOCKED && m.status != MatchStatus.DISPUTED)
            revert InvalidStatus(MatchStatus.LOCKED, m.status);
        if (winner != m.player1 && winner != m.player2) revert InvalidWinner(winner);
        if (block.timestamp >= uint256(m.lockedAt) + lockTimeout) revert ResolveWindowElapsed();

        uint256 totalPot = uint256(m.stakePerPlayer) * 2;
        uint256 fee = m.platformFee;
        if (fee > totalPot) fee = totalPot; // unreachable under the caps; keeps payout >= 0
        uint256 payout = totalPot - fee;

        m.status = MatchStatus.RESOLVED;
        totalLocked -= totalPot;
        totalFeesCollected += fee;
        accruedFees += fee;

        _pay(winner, payout);

        emit MatchResolved(matchId, winner, payout, fee);
    }

    /// @notice Flag a LOCKED match as disputed. The lock timeout keeps running.
    function flagDispute(bytes32 matchId)
        external
        onlyResolver
        matchExists(matchId)
    {
        Match storage m = _matches[matchId];
        if (m.status != MatchStatus.LOCKED) revert InvalidStatus(MatchStatus.LOCKED, m.status);
        m.status = MatchStatus.DISPUTED;
        emit MatchDisputed(matchId);
    }

    /// @notice Cancel and refund whoever has staked. Works while paused.
    function cancelMatch(bytes32 matchId)
        external
        nonReentrant
        onlyResolver
        matchExists(matchId)
    {
        Match storage m = _matches[matchId];
        if (m.status == MatchStatus.RESOLVED || m.status == MatchStatus.CANCELLED)
            revert InvalidStatus(MatchStatus.OPEN, m.status);
        _cancel(matchId, m);
    }

    // ─── Admin (owner = multisig) ─────────────────────────────────────────────

    function setResolver(address _resolver) external onlyOwner {
        if (_resolver == address(0)) revert ZeroAddress();
        emit ResolverUpdated(resolver, _resolver);
        resolver = _resolver;
    }

    function setFeeRecipient(address _feeRecipient) external onlyOwner {
        if (_feeRecipient == address(0)) revert ZeroAddress();
        emit FeeRecipientUpdated(feeRecipient, _feeRecipient);
        feeRecipient = _feeRecipient;
    }

    /**
     * @notice Retune the fee tiers for matches created from now on.
     * @dev Requirements: feeBps ≤ premiumFeeBps ≤ MAX_FEE_BPS,
     *      flatFeePerPlayer ≤ MAX_FLAT_FEE_PER_PLAYER, MIN_STAKE ≤ tierFlatMax ≤ tierBpsMax.
     *      Existing matches keep their snapshotted fee.
     */
    function setFeeTiers(
        uint256 _flatFeePerPlayer,
        uint256 _feeBps,
        uint256 _premiumFeeBps,
        uint256 _tierFlatMax,
        uint256 _tierBpsMax
    ) external onlyOwner {
        if (_premiumFeeBps < _feeBps) revert InvalidFeeTiers();
        if (_premiumFeeBps > MAX_FEE_BPS) revert InvalidFeeTiers();
        if (_flatFeePerPlayer > MAX_FLAT_FEE_PER_PLAYER) revert InvalidFeeTiers();
        if (_tierFlatMax < MIN_STAKE || _tierBpsMax < _tierFlatMax) revert InvalidFeeTiers();
        FLAT_FEE_PER_PLAYER = _flatFeePerPlayer;
        FEE_BPS = _feeBps;
        PREMIUM_FEE_BPS = _premiumFeeBps;
        TIER_FLAT_MAX_OVERRIDE = _tierFlatMax;
        TIER_BPS_MAX_OVERRIDE = _tierBpsMax;
        emit FeeTiersUpdated(_flatFeePerPlayer, _feeBps, _premiumFeeBps, _tierFlatMax, _tierBpsMax);
    }

    /// @notice Stop new stakes (create/join). Settlement and refunds keep working.
    function pause() external onlyOwner { _pause(); }
    function unpause() external onlyOwner { _unpause(); }

    /// @notice Disabled: the contract is immutable, so losing the owner would
    ///         freeze role rotation and fee governance forever.
    function renounceOwnership() public view override onlyOwner {
        revert RenounceDisabled();
    }

    // ─── Views ────────────────────────────────────────────────────────────────

    /// @notice v1-compatible getter (same six fields, same order). The fee
    ///         snapshot is available through getMatch.
    function matches(bytes32 matchId)
        external
        view
        returns (
            address player1,
            address player2,
            uint256 stakePerPlayer,
            MatchStatus status,
            uint256 createdAt,
            uint256 lockedAt
        )
    {
        Match storage m = _matches[matchId];
        return (m.player1, m.player2, m.stakePerPlayer, m.status, m.createdAt, m.lockedAt);
    }

    function getMatch(bytes32 matchId) external view returns (Match memory) {
        return _matches[matchId];
    }

    function getMatchStatus(bytes32 matchId) external view returns (MatchStatus) {
        return _matches[matchId].status;
    }

    /// @notice Timestamp from which refundExpired succeeds; 0 if the match is
    ///         missing or already settled.
    function refundableAt(bytes32 matchId) external view returns (uint256) {
        Match storage m = _matches[matchId];
        if (m.player1 == address(0)) return 0;
        return _refundableAt(m);
    }

    /// @notice EIP-712 digest the resolver signs to authorise createMatch.
    function hashCreateMatch(
        bytes32 matchId,
        address player1,
        address player2,
        uint256 stake,
        uint256 deadline
    ) public view returns (bytes32) {
        bytes32 structHash =
            keccak256(abi.encode(CREATE_MATCH_TYPEHASH, matchId, player1, player2, stake, deadline));
        return keccak256(abi.encodePacked("\x19\x01", _domainSeparator(), structHash));
    }

    /// @notice EIP-712 domain separator (name "BoardmanEscrow", version "2").
    function DOMAIN_SEPARATOR() external view returns (bytes32) {
        return _domainSeparator();
    }

    /// @notice Quote the total platform fee (on the pot) under the current tiers.
    function quotePlatformFee(uint256 stakePerPlayer) public view returns (uint256) {
        return _platformFee(stakePerPlayer * 2);
    }

    function contractBalance() external view returns (uint256) {
        return usdc.balanceOf(address(this));
    }

    // ─── Internals ────────────────────────────────────────────────────────────

    function _domainSeparator() internal view returns (bytes32) {
        if (block.chainid == _cachedChainId) return _cachedDomainSeparator;
        return _buildDomainSeparator(); // chain fork: rebind to the live chain id
    }

    function _buildDomainSeparator() private view returns (bytes32) {
        return keccak256(
            abi.encode(_DOMAIN_TYPEHASH, _NAME_HASH, _VERSION_HASH, block.chainid, address(this))
        );
    }

    function _refundableAt(Match storage m) internal view returns (uint256) {
        if (m.status == MatchStatus.OPEN) return uint256(m.createdAt) + openTimeout;
        if (m.status == MatchStatus.LOCKED || m.status == MatchStatus.DISPUTED)
            return uint256(m.lockedAt) + lockTimeout;
        return 0;
    }

    /// @dev Refunds player1 always and player2 only if they actually staked
    ///      (player2 is bound at create, so a non-zero address is not enough).
    function _cancel(bytes32 matchId, Match storage m) internal {
        bool p2Staked = m.status == MatchStatus.LOCKED || m.status == MatchStatus.DISPUTED;
        uint256 stake = m.stakePerPlayer;
        m.status = MatchStatus.CANCELLED;
        totalLocked -= p2Staked ? stake * 2 : stake;

        _pay(m.player1, stake);
        if (p2Staked) _pay(m.player2, stake);

        emit MatchCancelled(matchId);
    }

    /// @dev Push the transfer; if it fails, credit `owed` so settlement of the
    ///      match still completes and the recipient can withdraw later.
    function _pay(address to, uint256 amount) internal {
        if (amount == 0) return;
        if (!usdc.trySafeTransfer(to, amount)) {
            owed[to] += amount;
            totalOwed += amount;
            emit PayoutDeferred(to, amount);
        }
    }

    /// @dev Tiered fee on the pot. Under the caps the result is at most 25%
    ///      of the pot (flat tier) or MAX_FEE_BPS (percentage tiers).
    function _platformFee(uint256 pot) internal view returns (uint256) {
        if (pot == 0) return 0;
        uint256 perPlayer = pot / 2;
        uint256 fee;
        if (perPlayer < TIER_FLAT_MAX_OVERRIDE) {
            fee = FLAT_FEE_PER_PLAYER * 2;
        } else if (perPlayer <= TIER_BPS_MAX_OVERRIDE) {
            fee = (pot * FEE_BPS) / BPS_DENOM;
        } else {
            fee = (pot * PREMIUM_FEE_BPS) / BPS_DENOM;
        }
        return fee > pot ? pot : fee;
    }
}
