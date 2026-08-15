// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

import "@openzeppelin/contracts/token/ERC20/IERC20.sol";
import "@openzeppelin/contracts/token/ERC20/utils/SafeERC20.sol";
import "@openzeppelin/contracts/access/Ownable.sol";
import "@openzeppelin/contracts/utils/ReentrancyGuard.sol";
import "@openzeppelin/contracts/utils/Pausable.sol";

/**
 * @title SpectatorPool
 * @notice Match-keyed spectator pot. Separate from BoardmanEscrow.
 *         Fans deposit USDC on side 0 or 1. Resolver opens / closes / resolves.
 *         Winners pull-claim. Laptop-hub House uses depositFor (custodial).
 * @dev deposit(bytes32,uint256,uint8) is frozen to match spectator_escrow.py.
 */
contract SpectatorPool is Ownable, ReentrancyGuard, Pausable {
    using SafeERC20 for IERC20;

    uint16 public constant PLATFORM_FEE_BPS = 300;
    uint16 public constant CREATOR_BPS = 200;
    /// @notice Of the 2% creator pool, the winner's creator gets this % (75),
    ///         the loser's creator the rest. Draws split 50/50.
    uint16 public constant WINNER_CREATOR_PCT = 75;
    uint16 public constant BPS_DENOM = 10_000;
    /// @notice Resolve sentinel for a draw outcome (winnerSide = -2). Draw
    ///         tickets win the entire pot; A/B tickets lose.
    int8 public constant DRAW_SIDE = -2;

    IERC20 public immutable usdc;
    address public feeRecipient;
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
        // v2 draw book — appended so getBook positions 0..18 stay stable.
        address seedPayerDrawA;
        address seedPayerDrawB;
        uint256 seedDrawA;
        uint256 seedDrawB;
        uint256 totalDraw;
    }

    mapping(bytes32 => Book) public books;
    mapping(bytes32 => mapping(address => uint256)) public fanDepositA;
    mapping(bytes32 => mapping(address => uint256)) public fanDepositB;
    mapping(bytes32 => mapping(address => uint256)) public fanDepositDraw;
    mapping(bytes32 => mapping(address => bool)) public claimed;

    event BookOpened(
        bytes32 indexed matchId,
        bytes32 indexed gameId,
        bytes32 agentA,
        bytes32 agentB,
        address walletA,
        address walletB,
        uint256 potCap
    );
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
    event Claimed(bytes32 indexed matchId, address indexed user, uint256 amount);
    event ResolverUpdated(address indexed oldResolver, address indexed newResolver);
    event FeeRecipientUpdated(address indexed oldRecipient, address indexed newRecipient);

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

    modifier onlyResolver() {
        if (msg.sender != resolver && msg.sender != owner()) revert NotResolver(msg.sender);
        _;
    }

    constructor(address _usdc, address _feeRecipient, address _resolver) Ownable(msg.sender) {
        if (_usdc == address(0) || _feeRecipient == address(0) || _resolver == address(0)) {
            revert ZeroAddress();
        }
        usdc = IERC20(_usdc);
        feeRecipient = _feeRecipient;
        resolver = _resolver;
    }

    function openBook(
        bytes32 matchId,
        bytes32 gameId,
        bytes32 agentA,
        bytes32 agentB,
        address agentWalletA,
        address agentWalletB,
        address creatorA,
        address creatorB,
        uint256 potCap
    ) external onlyResolver whenNotPaused {
        if (books[matchId].status != BookStatus.None) revert BookExists();
        if (agentA == agentB || agentWalletA == agentWalletB) revert DuplicateAgents();
        if (agentWalletA == address(0) || agentWalletB == address(0)) revert ZeroAddress();
        if (potCap == 0) revert ZeroAmount();

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

        emit BookOpened(matchId, gameId, agentA, agentB, agentWalletA, agentWalletB, potCap);
    }

    function seed(bytes32 matchId, uint8 side, uint256 amount) external whenNotPaused nonReentrant {
        if (side > 2) revert InvalidSide();
        if (amount == 0) revert ZeroAmount();
        Book storage b = books[matchId];
        if (b.status != BookStatus.Open) revert BookNotOpen();
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
    ///         side: 0 = agent A, 1 = agent B, 2 = draw.
    function deposit(bytes32 matchId, uint256 amount, uint8 side) external whenNotPaused nonReentrant {
        _creditDeposit(matchId, msg.sender, amount, side);
        usdc.safeTransferFrom(msg.sender, address(this), amount);
        emit Deposited(matchId, msg.sender, side, amount);
    }

    /// @notice House custodial path. Resolver pulls USDC from itself and credits `user`.
    ///         side: 0 = agent A, 1 = agent B, 2 = draw.
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

    /// @notice winnerSide: 0 = agent A, 1 = agent B, -2 = draw (DRAW_SIDE).
    ///         Draw tickets win the whole pot; A/B tickets lose.
    function resolve(bytes32 matchId, int8 winnerSide) external onlyResolver {
        _resolve(matchId, winnerSide, false);
    }

    function cancel(bytes32 matchId) external onlyResolver {
        Book storage b = books[matchId];
        if (b.status == BookStatus.None) revert BookNotFound();
        if (b.status == BookStatus.Resolved) revert AlreadyResolved();
        if (b.status == BookStatus.Cancelled) return;
        _resolve(matchId, -1, true);
    }

    function claim(bytes32 matchId) external nonReentrant {
        uint256 amt = claimable(matchId, msg.sender);
        if (amt == 0) revert NothingToClaim();
        claimed[matchId][msg.sender] = true;
        usdc.safeTransfer(msg.sender, amt);
        emit Claimed(matchId, msg.sender, amt);
    }

    function getBook(bytes32 matchId) external view returns (Book memory) {
        return books[matchId];
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

    function claimable(bytes32 matchId, address user) public view returns (uint256) {
        if (claimed[matchId][user]) return 0;
        Book storage b = books[matchId];
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

    function pause() external onlyOwner {
        _pause();
    }

    function unpause() external onlyOwner {
        _unpause();
    }

    function contractBalance() external view returns (uint256) {
        return usdc.balanceOf(address(this));
    }

    function _pot(Book storage b) internal view returns (uint256) {
        return b.totalA + b.totalB + b.totalDraw;
    }

    function _creditDeposit(bytes32 matchId, address user, uint256 amount, uint8 side) internal {
        if (side > 2) revert InvalidSide();
        if (amount == 0) revert ZeroAmount();
        Book storage b = books[matchId];
        if (b.status != BookStatus.Open) revert BookNotOpen();
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

    function _resolve(bytes32 matchId, int8 winnerSide, bool asCancel) internal {
        Book storage b = books[matchId];
        if (b.status == BookStatus.None) revert BookNotFound();
        if (b.status == BookStatus.Resolved || b.status == BookStatus.Cancelled) {
            revert AlreadyResolved();
        }
        if (winnerSide < -2 || winnerSide > 1) revert InvalidSide();

        uint256 pot = _pot(b);
        if ((winnerSide < 0 && winnerSide != DRAW_SIDE) || pot == 0) {
            _markRefund(matchId, b, asCancel, pot);
            return;
        }

        uint256 fanWin_;
        int8 storedSide;
        if (winnerSide == DRAW_SIDE) {
            // Draw outcome: draw tickets win the whole pot; A/B tickets lose.
            fanWin_ = b.totalDraw - b.seedDrawA - b.seedDrawB;
            storedSide = DRAW_SIDE;
        } else {
            fanWin_ = winnerSide == 0 ? b.totalA - b.seedA : b.totalB - b.seedB;
            storedSide = winnerSide;
        }
        if (fanWin_ == 0) {
            _markRefund(matchId, b, asCancel, pot);
            return;
        }

        uint256 platformFee = (pot * PLATFORM_FEE_BPS) / BPS_DENOM;
        uint256 creatorPool = (pot * CREATOR_BPS) / BPS_DENOM;
        uint256 distributable_ = pot - platformFee - creatorPool;

        b.winnerSide = storedSide;
        b.distributable = distributable_;
        b.fanWin = fanWin_;
        b.status = BookStatus.Resolved;

        if (platformFee > 0) {
            usdc.safeTransfer(feeRecipient, platformFee);
        }
        if (creatorPool > 0) {
            _payCreators(b, creatorPool, storedSide);
        }

        emit BookResolved(matchId, storedSide, pot, platformFee, creatorPool, distributable_, fanWin_);
    }

    /// @notice Winner's creator takes WINNER_CREATOR_PCT of the creator pool
    ///         (the losing side's money flows to the winning agent); the other
    ///         creator takes the rest. Draws split 50/50. Zero addresses fall
    ///         back to feeRecipient.
    function _payCreators(Book storage b, uint256 creatorPool, int8 winnerSide) internal {
        address winCreator;
        address loseCreator;
        if (winnerSide == DRAW_SIDE) {
            winCreator = b.creatorA;
            loseCreator = b.creatorB;
        } else if (winnerSide == 0) {
            winCreator = b.creatorA;
            loseCreator = b.creatorB;
        } else {
            winCreator = b.creatorB;
            loseCreator = b.creatorA;
        }
        uint256 winShare;
        if (winnerSide == DRAW_SIDE) {
            winShare = creatorPool / 2; // draw: both creators split evenly
        } else {
            winShare = (creatorPool * WINNER_CREATOR_PCT) / 100;
        }
        uint256 loseShare = creatorPool - winShare;
        usdc.safeTransfer(winCreator == address(0) ? feeRecipient : winCreator, winShare);
        if (loseShare > 0) {
            usdc.safeTransfer(loseCreator == address(0) ? feeRecipient : loseCreator, loseShare);
        }
    }

    function _markRefund(bytes32 matchId, Book storage b, bool asCancel, uint256 pot) internal {
        b.winnerSide = -1;
        b.distributable = 0;
        b.fanWin = 0;
        b.status = asCancel ? BookStatus.Cancelled : BookStatus.Resolved;
        emit BookResolved(matchId, -1, pot, 0, 0, 0, 0);
    }
}
