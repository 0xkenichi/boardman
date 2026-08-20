// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

import "@openzeppelin/contracts/token/ERC20/IERC20.sol";
import "@openzeppelin/contracts/token/ERC20/utils/SafeERC20.sol";
import "@openzeppelin/contracts/access/Ownable.sol";
import "@openzeppelin/contracts/utils/ReentrancyGuard.sol";
import "@openzeppelin/contracts/utils/Pausable.sol";

/**
 * @title BoardmanEscrow
 * @notice Trustless dual-lock escrow for Boardman by sideQuest (formerly Rematch).
 *         USDC staking; admin/resolver settles winners; dispute path off-chain.
 * @dev V1 product contract. Legacy ClawEscrow remains V0 archive only.
 */
contract BoardmanEscrow is Ownable, ReentrancyGuard, Pausable {
    using SafeERC20 for IERC20;

    // ─── Constants ────────────────────────────────────────────────────────────
    uint256 public constant FEE_BPS = 700;       // 7% platform fee (700 basis points)
    uint256 public constant BPS_DENOM = 10_000;
    uint256 public constant MAX_STAKE = 10_000e6; // $10,000 USDC cap per match

    // ─── State ────────────────────────────────────────────────────────────────
    IERC20 public immutable usdc;
    address public feeRecipient;
    address public resolver; // backend admin wallet that calls resolve/cancel

    enum MatchStatus {
        OPEN,       // creator staked, waiting for player2
        LOCKED,     // both staked, match in progress
        DISPUTED,   // conflict flagged, AI mediator deciding
        RESOLVED,   // winner paid out
        CANCELLED   // refunded
    }

    struct Match {
        address player1;
        address player2;
        uint256 stakePerPlayer; // USDC amount (6 decimals)
        MatchStatus status;
        uint256 createdAt;
        uint256 lockedAt;
    }

    mapping(bytes32 => Match) public matches;
    uint256 public totalFeesCollected;

    // ─── Events ───────────────────────────────────────────────────────────────
    event MatchCreated(bytes32 indexed matchId, address indexed player1, uint256 stake);
    event MatchJoined(bytes32 indexed matchId, address indexed player2);
    event MatchLocked(bytes32 indexed matchId);
    event MatchResolved(bytes32 indexed matchId, address indexed winner, uint256 payout, uint256 fee);
    event MatchDisputed(bytes32 indexed matchId);
    event MatchCancelled(bytes32 indexed matchId);
    event ResolverUpdated(address indexed oldResolver, address indexed newResolver);
    event FeeRecipientUpdated(address indexed oldRecipient, address indexed newRecipient);

    // ─── Errors ───────────────────────────────────────────────────────────────
    error MatchAlreadyExists();
    error MatchNotFound();
    error InvalidStatus(MatchStatus expected, MatchStatus actual);
    error NotPlayer(address caller);
    error NotResolver(address caller);
    error InvalidWinner(address winner);
    error StakeExceedsMax(uint256 stake);
    error ZeroStake();
    error ZeroAddress();

    // ─── Modifiers ────────────────────────────────────────────────────────────
    modifier onlyResolver() {
        if (msg.sender != resolver && msg.sender != owner()) revert NotResolver(msg.sender);
        _;
    }

    modifier matchExists(bytes32 matchId) {
        if (matches[matchId].player1 == address(0)) revert MatchNotFound();
        _;
    }

    // ─── Constructor ──────────────────────────────────────────────────────────
    constructor(
        address _usdc,
        address _feeRecipient,
        address _resolver
    ) Ownable(msg.sender) {
        if (_usdc == address(0) || _feeRecipient == address(0) || _resolver == address(0))
            revert ZeroAddress();
        usdc = IERC20(_usdc);
        feeRecipient = _feeRecipient;
        resolver = _resolver;
    }

    // ─── Player Actions ───────────────────────────────────────────────────────

    /**
     * @notice Player1 creates a match and stakes USDC into escrow.
     * @param matchId  Unique match ID generated off-chain (keccak256 of backend UUID).
     * @param stake    USDC amount to stake (6 decimals). Both players stake this amount.
     */
    function createMatch(bytes32 matchId, uint256 stake)
        external
        nonReentrant
        whenNotPaused
    {
        if (stake == 0) revert ZeroStake();
        if (stake > MAX_STAKE) revert StakeExceedsMax(stake);
        if (matches[matchId].player1 != address(0)) revert MatchAlreadyExists();

        matches[matchId] = Match({
            player1: msg.sender,
            player2: address(0),
            stakePerPlayer: stake,
            status: MatchStatus.OPEN,
            createdAt: block.timestamp,
            lockedAt: 0
        });

        usdc.safeTransferFrom(msg.sender, address(this), stake);

        emit MatchCreated(matchId, msg.sender, stake);
    }

    /**
     * @notice Player2 joins an open match and stakes the same amount as player1.
     * @param matchId  The match to join.
     */
    function joinMatch(bytes32 matchId)
        external
        nonReentrant
        whenNotPaused
        matchExists(matchId)
    {
        Match storage m = matches[matchId];
        if (m.status != MatchStatus.OPEN) revert InvalidStatus(MatchStatus.OPEN, m.status);
        if (msg.sender == m.player1) revert NotPlayer(msg.sender); // can't match yourself

        m.player2 = msg.sender;
        m.status = MatchStatus.LOCKED;
        m.lockedAt = block.timestamp;

        usdc.safeTransferFrom(msg.sender, address(this), m.stakePerPlayer);

        emit MatchJoined(matchId, msg.sender);
        emit MatchLocked(matchId);
    }

    // ─── Resolver Actions ─────────────────────────────────────────────────────

    /**
     * @notice Resolver pays out the winner after both players report matching scores,
     *         or after AI mediator determines the winner from a dispute.
     * @param matchId  The match to resolve.
     * @param winner   Address of the winning player (must be player1 or player2).
     */
    function resolveMatch(bytes32 matchId, address winner)
        external
        nonReentrant
        onlyResolver
        matchExists(matchId)
    {
        Match storage m = matches[matchId];
        if (m.status != MatchStatus.LOCKED && m.status != MatchStatus.DISPUTED)
            revert InvalidStatus(MatchStatus.LOCKED, m.status);
        if (winner != m.player1 && winner != m.player2)
            revert InvalidWinner(winner);

        uint256 totalPot = m.stakePerPlayer * 2;
        uint256 fee = (totalPot * FEE_BPS) / BPS_DENOM;
        uint256 payout = totalPot - fee;

        m.status = MatchStatus.RESOLVED;
        totalFeesCollected += fee;

        usdc.safeTransfer(winner, payout);
        usdc.safeTransfer(feeRecipient, fee);

        emit MatchResolved(matchId, winner, payout, fee);
    }

    /**
     * @notice Resolver flags a match as disputed (triggers AI mediator off-chain).
     * @param matchId  The match to flag.
     */
    function flagDispute(bytes32 matchId)
        external
        onlyResolver
        matchExists(matchId)
    {
        Match storage m = matches[matchId];
        if (m.status != MatchStatus.LOCKED) revert InvalidStatus(MatchStatus.LOCKED, m.status);

        m.status = MatchStatus.DISPUTED;
        emit MatchDisputed(matchId);
    }

    /**
     * @notice Cancels a match and refunds both players.
     * @param matchId  The match to cancel.
     */
    function cancelMatch(bytes32 matchId)
        external
        nonReentrant
        onlyResolver
        matchExists(matchId)
    {
        Match storage m = matches[matchId];
        if (m.status == MatchStatus.RESOLVED || m.status == MatchStatus.CANCELLED)
            revert InvalidStatus(MatchStatus.OPEN, m.status);

        m.status = MatchStatus.CANCELLED;

        usdc.safeTransfer(m.player1, m.stakePerPlayer);

        if (m.player2 != address(0)) {
            usdc.safeTransfer(m.player2, m.stakePerPlayer);
        }

        emit MatchCancelled(matchId);
    }

    // ─── Admin ────────────────────────────────────────────────────────────────

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

    function pause() external onlyOwner { _pause(); }
    function unpause() external onlyOwner { _unpause(); }

    // ─── Views ────────────────────────────────────────────────────────────────

    function getMatch(bytes32 matchId) external view returns (Match memory) {
        return matches[matchId];
    }

    function getMatchStatus(bytes32 matchId) external view returns (MatchStatus) {
        return matches[matchId].status;
    }

    function contractBalance() external view returns (uint256) {
        return usdc.balanceOf(address(this));
    }
}
