// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

import "forge-std/Test.sol";
import "../contracts/ClawEscrow.sol";
import "@openzeppelin/contracts/token/ERC20/ERC20.sol";

// ── Mock USDC ──────────────────────────────────────────────────────────────────
contract MockUSDC is ERC20 {
    constructor() ERC20("USD Coin", "USDC") {}
    function decimals() public pure override returns (uint8) { return 6; }
    function mint(address to, uint256 amount) external { _mint(to, amount); }
}

// ── Test Contract ──────────────────────────────────────────────────────────────
contract ClawEscrowTest is Test {
    ClawEscrow escrow;
    MockUSDC usdc;

    address owner     = makeAddr("owner");
    address resolver  = makeAddr("resolver");
    address feeAddr   = makeAddr("feeRecipient");
    address player1   = makeAddr("player1");
    address player2   = makeAddr("player2");
    address attacker  = makeAddr("attacker");

    uint256 constant STAKE = 10e6; // $10 USDC
    bytes32 constant MATCH_ID = keccak256("match-001");

    function setUp() public {
        vm.startPrank(owner);
        usdc = new MockUSDC();
        escrow = new ClawEscrow(address(usdc), feeAddr, resolver);
        vm.stopPrank();

        // Fund players
        usdc.mint(player1, 1000e6);
        usdc.mint(player2, 1000e6);
        usdc.mint(attacker, 1000e6);

        vm.prank(player1); usdc.approve(address(escrow), type(uint256).max);
        vm.prank(player2); usdc.approve(address(escrow), type(uint256).max);
        vm.prank(attacker); usdc.approve(address(escrow), type(uint256).max);
    }

    // ── createMatch ────────────────────────────────────────────────────────────

    function test_createMatch_success() public {
        vm.prank(player1);
        escrow.createMatch(MATCH_ID, STAKE);

        ClawEscrow.Match memory m = escrow.getMatch(MATCH_ID);
        assertEq(m.player1, player1);
        assertEq(m.stakePerPlayer, STAKE);
        assertEq(uint(m.status), uint(ClawEscrow.MatchStatus.OPEN));
        assertEq(usdc.balanceOf(address(escrow)), STAKE);
    }

    function test_createMatch_duplicateReverts() public {
        vm.prank(player1); escrow.createMatch(MATCH_ID, STAKE);
        vm.prank(player2);
        vm.expectRevert(ClawEscrow.MatchAlreadyExists.selector);
        escrow.createMatch(MATCH_ID, STAKE);
    }

    function test_createMatch_zeroStakeReverts() public {
        vm.prank(player1);
        vm.expectRevert(ClawEscrow.ZeroStake.selector);
        escrow.createMatch(MATCH_ID, 0);
    }

    function test_createMatch_exceedsMaxReverts() public {
        vm.prank(player1);
        usdc.mint(player1, 20_000e6);
        vm.expectRevert(abi.encodeWithSelector(ClawEscrow.StakeExceedsMax.selector, 10_001e6));
        escrow.createMatch(MATCH_ID, 10_001e6);
    }

    // ── joinMatch ──────────────────────────────────────────────────────────────

    function test_joinMatch_success() public {
        vm.prank(player1); escrow.createMatch(MATCH_ID, STAKE);
        vm.prank(player2); escrow.joinMatch(MATCH_ID);

        ClawEscrow.Match memory m = escrow.getMatch(MATCH_ID);
        assertEq(m.player2, player2);
        assertEq(uint(m.status), uint(ClawEscrow.MatchStatus.LOCKED));
        assertEq(usdc.balanceOf(address(escrow)), STAKE * 2);
    }

    function test_joinMatch_samePlayerReverts() public {
        vm.prank(player1); escrow.createMatch(MATCH_ID, STAKE);
        vm.prank(player1);
        vm.expectRevert(abi.encodeWithSelector(ClawEscrow.NotPlayer.selector, player1));
        escrow.joinMatch(MATCH_ID);
    }

    function test_joinMatch_wrongStatusReverts() public {
        vm.prank(player1); escrow.createMatch(MATCH_ID, STAKE);
        vm.prank(player2); escrow.joinMatch(MATCH_ID);
        vm.prank(attacker);
        vm.expectRevert(
            abi.encodeWithSelector(
                ClawEscrow.InvalidStatus.selector,
                ClawEscrow.MatchStatus.OPEN,
                ClawEscrow.MatchStatus.LOCKED
            )
        );
        escrow.joinMatch(MATCH_ID);
    }

    // ── resolveMatch ───────────────────────────────────────────────────────────

    function test_resolveMatch_player1Wins() public {
        vm.prank(player1); escrow.createMatch(MATCH_ID, STAKE);
        vm.prank(player2); escrow.joinMatch(MATCH_ID);

        uint256 p1Before = usdc.balanceOf(player1);
        uint256 feesBefore = usdc.balanceOf(feeAddr);

        vm.prank(resolver);
        escrow.resolveMatch(MATCH_ID, player1);

        uint256 totalPot = STAKE * 2;
        uint256 fee = (totalPot * 300) / 10_000; // 3%
        uint256 payout = totalPot - fee;

        assertEq(usdc.balanceOf(player1), p1Before + payout);
        assertEq(usdc.balanceOf(feeAddr), feesBefore + fee);
        assertEq(usdc.balanceOf(address(escrow)), 0);
        assertEq(uint(escrow.getMatch(MATCH_ID).status), uint(ClawEscrow.MatchStatus.RESOLVED));
    }

    function test_resolveMatch_invalidWinnerReverts() public {
        vm.prank(player1); escrow.createMatch(MATCH_ID, STAKE);
        vm.prank(player2); escrow.joinMatch(MATCH_ID);

        vm.prank(resolver);
        vm.expectRevert(abi.encodeWithSelector(ClawEscrow.InvalidWinner.selector, attacker));
        escrow.resolveMatch(MATCH_ID, attacker);
    }

    function test_resolveMatch_nonResolverReverts() public {
        vm.prank(player1); escrow.createMatch(MATCH_ID, STAKE);
        vm.prank(player2); escrow.joinMatch(MATCH_ID);

        vm.prank(attacker);
        vm.expectRevert(abi.encodeWithSelector(ClawEscrow.NotResolver.selector, attacker));
        escrow.resolveMatch(MATCH_ID, player1);
    }

    // ── flagDispute ────────────────────────────────────────────────────────────

    function test_flagDispute_success() public {
        vm.prank(player1); escrow.createMatch(MATCH_ID, STAKE);
        vm.prank(player2); escrow.joinMatch(MATCH_ID);
        vm.prank(resolver); escrow.flagDispute(MATCH_ID);

        assertEq(uint(escrow.getMatch(MATCH_ID).status), uint(ClawEscrow.MatchStatus.DISPUTED));
    }

    function test_resolveDisputedMatch() public {
        vm.prank(player1); escrow.createMatch(MATCH_ID, STAKE);
        vm.prank(player2); escrow.joinMatch(MATCH_ID);
        vm.prank(resolver); escrow.flagDispute(MATCH_ID);

        // AI mediator decides — resolver calls resolveMatch
        vm.prank(resolver);
        escrow.resolveMatch(MATCH_ID, player2);
        assertEq(uint(escrow.getMatch(MATCH_ID).status), uint(ClawEscrow.MatchStatus.RESOLVED));
    }

    // ── cancelMatch ────────────────────────────────────────────────────────────

    function test_cancelMatch_openRefundsPlayer1Only() public {
        vm.prank(player1); escrow.createMatch(MATCH_ID, STAKE);

        uint256 p1Before = usdc.balanceOf(player1);
        vm.prank(resolver); escrow.cancelMatch(MATCH_ID);

        assertEq(usdc.balanceOf(player1), p1Before + STAKE);
        assertEq(usdc.balanceOf(address(escrow)), 0);
    }

    function test_cancelMatch_lockedRefundsBoth() public {
        vm.prank(player1); escrow.createMatch(MATCH_ID, STAKE);
        vm.prank(player2); escrow.joinMatch(MATCH_ID);

        uint256 p1Before = usdc.balanceOf(player1);
        uint256 p2Before = usdc.balanceOf(player2);

        vm.prank(resolver); escrow.cancelMatch(MATCH_ID);

        assertEq(usdc.balanceOf(player1), p1Before + STAKE);
        assertEq(usdc.balanceOf(player2), p2Before + STAKE);
    }

    // ── Pause ──────────────────────────────────────────────────────────────────

    function test_pausePreventsCreation() public {
        vm.prank(owner); escrow.pause();
        vm.prank(player1);
        vm.expectRevert();
        escrow.createMatch(MATCH_ID, STAKE);
    }

    function test_unpauseRestoresCreation() public {
        vm.prank(owner); escrow.pause();
        vm.prank(owner); escrow.unpause();
        vm.prank(player1);
        escrow.createMatch(MATCH_ID, STAKE); // should not revert
    }

    // ── Fee math fuzz ──────────────────────────────────────────────────────────

    function testFuzz_feeMath(uint256 stake) public {
        stake = bound(stake, 1e6, 10_000e6); // $1–$10k
        usdc.mint(player1, stake);
        usdc.mint(player2, stake);

        vm.prank(player1); usdc.approve(address(escrow), stake);
        vm.prank(player2); usdc.approve(address(escrow), stake);

        bytes32 id = keccak256(abi.encode(stake, block.timestamp));
        vm.prank(player1); escrow.createMatch(id, stake);
        vm.prank(player2); escrow.joinMatch(id);

        uint256 totalPot = stake * 2;
        uint256 expectedFee = (totalPot * 100) / 10_000;
        uint256 expectedPayout = totalPot - expectedFee;

        uint256 p1Before = usdc.balanceOf(player1);

        vm.prank(resolver); escrow.resolveMatch(id, player1);

        assertEq(usdc.balanceOf(player1) - p1Before, expectedPayout);
        assertEq(usdc.balanceOf(feeAddr), expectedFee);
    }
}
