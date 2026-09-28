import hre from "hardhat";
const { ethers } = hre;
import { expect } from "chai";

describe("BoardmanEscrow", function () {
  let usdc, escrow, owner, resolver, feeRecipient, player1, player2, stranger;
  const STAKE = 5_000_000n; // 5 USDC

  async function deploy() {
    [owner, resolver, feeRecipient, player1, player2, stranger] = await ethers.getSigners();

    const Mock = await ethers.getContractFactory("MockUSDC");
    usdc = await Mock.deploy();
    await usdc.waitForDeployment();

    const Escrow = await ethers.getContractFactory("BoardmanEscrow");
    escrow = await Escrow.deploy(
      await usdc.getAddress(),
      feeRecipient.address,
      resolver.address
    );
    await escrow.waitForDeployment();

    for (const s of [player1, player2, stranger]) {
      await usdc.mint(s.address, 100_000_000n); // 100 USDC
      await usdc.connect(s).approve(await escrow.getAddress(), ethers.MaxUint256);
    }
  }

  beforeEach(deploy);

  // ─── Constructor ──────────────────────────────────────────────────────

  it("initializes with correct state", async function () {
    expect(await escrow.usdc()).to.equal(await usdc.getAddress());
    expect(await escrow.feeRecipient()).to.equal(feeRecipient.address);
    expect(await escrow.resolver()).to.equal(resolver.address);
    expect(await escrow.owner()).to.equal(owner.address);
    expect(await escrow.FEE_BPS()).to.equal(700);
    expect(await escrow.PREMIUM_FEE_BPS()).to.equal(1000);
    expect(await escrow.FLAT_FEE_PER_PLAYER()).to.equal(500_000n);
    expect(await escrow.MIN_STAKE()).to.equal(2_000_000n);
    expect(await escrow.MAX_STAKE()).to.equal(10_000e6);
  });

  // ─── Tiered fees ──────────────────────────────────────────────────────

  it("reverts when stake is below the $2 minimum", async function () {
    const matchId = ethers.id("match_dust");
    await expect(
      escrow.connect(player1).createMatch(matchId, 1_999_999n)
    ).to.be.revertedWithCustomError(escrow, "StakeBelowMin");
    // boundary: exactly $2 is allowed
    await escrow.connect(player1).createMatch(ethers.id("match_min_ok"), 2_000_000n);
  });

  it("quotes the tiered platform fee correctly", async function () {
    // dust tier: $3/player → pot $6 → flat $1 total
    expect(await escrow.quotePlatformFee(3_000_000n)).to.equal(1_000_000n);
    // mid tier: $25/player → pot $50 → 7% = $3.50
    expect(await escrow.quotePlatformFee(25_000_000n)).to.equal(3_500_000n);
    // mid-tier upper boundary: $500/player → pot $1000 → 7% = $70
    expect(await escrow.quotePlatformFee(500_000_000n)).to.equal(70_000_000n);
    // premium tier: $600/player → pot $1200 → 10% = $120
    expect(await escrow.quotePlatformFee(600_000_000n)).to.equal(120_000_000n);
  });

  it("applies the flat $1 fee on sub-$5 stakes", async function () {
    const matchId = ethers.id("match_flat_fee");
    await usdc.mint(player1.address, 10_000_000n);
    await usdc.mint(player2.address, 10_000_000n);
    await escrow.connect(player1).createMatch(matchId, 3_000_000n); // $3
    await escrow.connect(player2).joinMatch(matchId);

    const totalPot = 6_000_000n;
    const expectedFee = 1_000_000n; // flat $1.00
    const expectedPayout = totalPot - expectedFee;

    await expect(escrow.connect(resolver).resolveMatch(matchId, player1.address))
      .to.emit(escrow, "MatchResolved")
      .withArgs(matchId, player1.address, expectedPayout, expectedFee);
    expect(await usdc.balanceOf(feeRecipient.address)).to.equal(expectedFee);
  });

  it("applies the 10% premium fee above $500 stakes", async function () {
    const matchId = ethers.id("match_premium");
    await usdc.mint(player1.address, 1_000_000_000n);
    await usdc.mint(player2.address, 1_000_000_000n);
    await escrow.connect(player1).createMatch(matchId, 600_000_000n); // $600
    await escrow.connect(player2).joinMatch(matchId);

    const totalPot = 1_200_000_000n;
    const expectedFee = 120_000_000n; // 10%
    const expectedPayout = totalPot - expectedFee;

    await expect(escrow.connect(resolver).resolveMatch(matchId, player2.address))
      .to.emit(escrow, "MatchResolved")
      .withArgs(matchId, player2.address, expectedPayout, expectedFee);
    expect(await escrow.totalFeesCollected()).to.equal(expectedFee);
  });

  it("owner can retune tiers via setFeeTiers; invalid sets revert", async function () {
    await expect(
      escrow.connect(owner).setFeeTiers(1_000_000n, 500, 800, 4_000_000n, 600_000_000n)
    )
      .to.emit(escrow, "FeeTiersUpdated")
      .withArgs(1_000_000n, 500, 800, 4_000_000n, 600_000_000n);
    expect(await escrow.FEE_BPS()).to.equal(500);
    expect(await escrow.PREMIUM_FEE_BPS()).to.equal(800);
    expect(await escrow.FLAT_FEE_PER_PLAYER()).to.equal(1_000_000n);

    // premium below mid
    await expect(
      escrow.connect(owner).setFeeTiers(1_000_000n, 800, 500, 4_000_000n, 600_000_000n)
    ).to.be.revertedWithCustomError(escrow, "InvalidFeeTiers");
    // flat boundary below min stake
    await expect(
      escrow.connect(owner).setFeeTiers(1_000_000n, 500, 800, 1_000_000n, 600_000_000n)
    ).to.be.revertedWithCustomError(escrow, "InvalidFeeTiers");
    // non-owner
    await expect(
      escrow.connect(stranger).setFeeTiers(1_000_000n, 500, 800, 4_000_000n, 600_000_000n)
    ).to.be.revertedWithCustomError(escrow, "OwnableUnauthorizedAccount");
  });

  it("reverts on zero addresses in constructor", async function () {
    const Escrow = await ethers.getContractFactory("BoardmanEscrow");
    await expect(
      Escrow.deploy(ethers.ZeroAddress, feeRecipient.address, resolver.address)
    ).to.be.revertedWithCustomError(escrow, "ZeroAddress");
  });

  // ─── Create Match ─────────────────────────────────────────────────────

  it("player1 creates a match and stakes USDC", async function () {
    const matchId = ethers.id("match_1");
    await expect(escrow.connect(player1).createMatch(matchId, STAKE))
      .to.emit(escrow, "MatchCreated")
      .withArgs(matchId, player1.address, STAKE);

    const m = await escrow.getMatch(matchId);
    expect(m.player1).to.equal(player1.address);
    expect(m.player2).to.equal(ethers.ZeroAddress);
    expect(m.stakePerPlayer).to.equal(STAKE);
    expect(m.status).to.equal(0); // OPEN
    expect(await usdc.balanceOf(await escrow.getAddress())).to.equal(STAKE);
  });

  it("reverts on zero stake", async function () {
    const matchId = ethers.id("match_zero");
    await expect(
      escrow.connect(player1).createMatch(matchId, 0)
    ).to.be.revertedWithCustomError(escrow, "ZeroStake");
  });

  it("reverts when stake exceeds max", async function () {
    const matchId = ethers.id("match_max");
    await expect(
      escrow.connect(player1).createMatch(matchId, 10_000_000_001n)
    ).to.be.revertedWithCustomError(escrow, "StakeExceedsMax");
  });

  it("reverts on duplicate matchId", async function () {
    const matchId = ethers.id("match_dup");
    await escrow.connect(player1).createMatch(matchId, STAKE);
    await expect(
      escrow.connect(player2).createMatch(matchId, STAKE)
    ).to.be.revertedWithCustomError(escrow, "MatchAlreadyExists");
  });

  it("reverts when paused", async function () {
    const matchId = ethers.id("match_paused");
    await escrow.connect(owner).pause();
    await expect(
      escrow.connect(player1).createMatch(matchId, STAKE)
    ).to.be.revertedWithCustomError(escrow, "EnforcedPause");
  });

  // ─── Join Match ───────────────────────────────────────────────────────

  it("player2 joins and match locks", async function () {
    const matchId = ethers.id("match_join");
    await escrow.connect(player1).createMatch(matchId, STAKE);

    await expect(escrow.connect(player2).joinMatch(matchId))
      .to.emit(escrow, "MatchJoined")
      .withArgs(matchId, player2.address)
      .and.to.emit(escrow, "MatchLocked")
      .withArgs(matchId);

    const m = await escrow.getMatch(matchId);
    expect(m.player2).to.equal(player2.address);
    expect(m.status).to.equal(1); // LOCKED
    expect(m.lockedAt).to.be.gt(0);
    expect(await usdc.balanceOf(await escrow.getAddress())).to.equal(STAKE * 2n);
  });

  it("player1 cannot join their own match", async function () {
    const matchId = ethers.id("match_self");
    await escrow.connect(player1).createMatch(matchId, STAKE);
    await expect(
      escrow.connect(player1).joinMatch(matchId)
    ).to.be.revertedWithCustomError(escrow, "NotPlayer");
  });

  it("reverts joining a non-existent match", async function () {
    const matchId = ethers.id("match_nope");
    await expect(
      escrow.connect(player2).joinMatch(matchId)
    ).to.be.revertedWithCustomError(escrow, "MatchNotFound");
  });

  it("reverts joining an already locked match", async function () {
    const matchId = ethers.id("match_locked");
    await escrow.connect(player1).createMatch(matchId, STAKE);
    await escrow.connect(player2).joinMatch(matchId);
    await expect(
      escrow.connect(stranger).joinMatch(matchId)
    ).to.be.revertedWithCustomError(escrow, "InvalidStatus");
  });

  // ─── Resolve Match ────────────────────────────────────────────────────

  it("resolver pays winner with correct fee split", async function () {
    const matchId = ethers.id("match_resolve");
    await escrow.connect(player1).createMatch(matchId, STAKE);
    await escrow.connect(player2).joinMatch(matchId);

    const totalPot = STAKE * 2n;
    const expectedFee = (totalPot * 700n) / 10_000n; // 7%
    const expectedPayout = totalPot - expectedFee;

    const p1Before = await usdc.balanceOf(player1.address);
    const feeBefore = await usdc.balanceOf(feeRecipient.address);

    await expect(escrow.connect(resolver).resolveMatch(matchId, player1.address))
      .to.emit(escrow, "MatchResolved")
      .withArgs(matchId, player1.address, expectedPayout, expectedFee);

    expect(await usdc.balanceOf(player1.address)).to.equal(p1Before + expectedPayout);
    expect(await usdc.balanceOf(feeRecipient.address)).to.equal(feeBefore + expectedFee);
    expect((await escrow.getMatch(matchId)).status).to.equal(3); // RESOLVED
    expect(await escrow.totalFeesCollected()).to.equal(expectedFee);
  });

  it("resolver can pay either player", async function () {
    const matchId = ethers.id("match_resolve2");
    await escrow.connect(player1).createMatch(matchId, STAKE);
    await escrow.connect(player2).joinMatch(matchId);

    const p2Before = await usdc.balanceOf(player2.address);
    await escrow.connect(resolver).resolveMatch(matchId, player2.address);

    const totalPot = STAKE * 2n;
    const fee = (totalPot * 700n) / 10_000n;
    expect(await usdc.balanceOf(player2.address)).to.equal(p2Before + totalPot - fee);
  });

  it("owner can also resolve", async function () {
    const matchId = ethers.id("match_owner_resolve");
    await escrow.connect(player1).createMatch(matchId, STAKE);
    await escrow.connect(player2).joinMatch(matchId);
    await escrow.connect(owner).resolveMatch(matchId, player1.address);
    expect((await escrow.getMatch(matchId)).status).to.equal(3);
  });

  it("reverts resolver paying an address that is not a player", async function () {
    const matchId = ethers.id("match_bad_winner");
    await escrow.connect(player1).createMatch(matchId, STAKE);
    await escrow.connect(player2).joinMatch(matchId);
    await expect(
      escrow.connect(resolver).resolveMatch(matchId, stranger.address)
    ).to.be.revertedWithCustomError(escrow, "InvalidWinner");
  });

  it("reverts resolving an OPEN match", async function () {
    const matchId = ethers.id("match_open_resolve");
    await escrow.connect(player1).createMatch(matchId, STAKE);
    await expect(
      escrow.connect(resolver).resolveMatch(matchId, player1.address)
    ).to.be.revertedWithCustomError(escrow, "InvalidStatus");
  });

  it("reverts non-resolver resolving", async function () {
    const matchId = ethers.id("match_no_resolve");
    await escrow.connect(player1).createMatch(matchId, STAKE);
    await escrow.connect(player2).joinMatch(matchId);
    await expect(
      escrow.connect(stranger).resolveMatch(matchId, player1.address)
    ).to.be.revertedWithCustomError(escrow, "NotResolver");
  });

  it("can resolve a DISPUTED match", async function () {
    const matchId = ethers.id("match_dispute_resolve");
    await escrow.connect(player1).createMatch(matchId, STAKE);
    await escrow.connect(player2).joinMatch(matchId);
    await escrow.connect(resolver).flagDispute(matchId);
    await escrow.connect(resolver).resolveMatch(matchId, player2.address);
    expect((await escrow.getMatch(matchId)).status).to.equal(3);
  });

  // ─── Flag Dispute ─────────────────────────────────────────────────────

  it("resolver flags a match as disputed", async function () {
    const matchId = ethers.id("match_dispute");
    await escrow.connect(player1).createMatch(matchId, STAKE);
    await escrow.connect(player2).joinMatch(matchId);
    await expect(escrow.connect(resolver).flagDispute(matchId))
      .to.emit(escrow, "MatchDisputed")
      .withArgs(matchId);
    expect((await escrow.getMatch(matchId)).status).to.equal(2); // DISPUTED
  });

  it("cannot dispute an OPEN match", async function () {
    const matchId = ethers.id("match_dispute_open");
    await escrow.connect(player1).createMatch(matchId, STAKE);
    await expect(
      escrow.connect(resolver).flagDispute(matchId)
    ).to.be.revertedWithCustomError(escrow, "InvalidStatus");
  });

  // ─── Cancel Match ─────────────────────────────────────────────────────

  it("cancel refunds both players", async function () {
    const matchId = ethers.id("match_cancel");
    await escrow.connect(player1).createMatch(matchId, STAKE);
    await escrow.connect(player2).joinMatch(matchId);

    const p1Before = await usdc.balanceOf(player1.address);
    const p2Before = await usdc.balanceOf(player2.address);

    await expect(escrow.connect(resolver).cancelMatch(matchId))
      .to.emit(escrow, "MatchCancelled")
      .withArgs(matchId);

    expect(await usdc.balanceOf(player1.address)).to.equal(p1Before + STAKE);
    expect(await usdc.balanceOf(player2.address)).to.equal(p2Before + STAKE);
    expect((await escrow.getMatch(matchId)).status).to.equal(4); // CANCELLED
    expect(await usdc.balanceOf(await escrow.getAddress())).to.equal(0);
  });

  it("cancel OPEN match refunds only player1", async function () {
    const matchId = ethers.id("match_cancel_open");
    await escrow.connect(player1).createMatch(matchId, STAKE);
    const p1Before = await usdc.balanceOf(player1.address);
    await escrow.connect(resolver).cancelMatch(matchId);
    expect(await usdc.balanceOf(player1.address)).to.equal(p1Before + STAKE);
  });

  it("cannot cancel a RESOLVED match", async function () {
    const matchId = ethers.id("match_cancel_resolved");
    await escrow.connect(player1).createMatch(matchId, STAKE);
    await escrow.connect(player2).joinMatch(matchId);
    await escrow.connect(resolver).resolveMatch(matchId, player1.address);
    await expect(
      escrow.connect(resolver).cancelMatch(matchId)
    ).to.be.revertedWithCustomError(escrow, "InvalidStatus");
  });

  // ─── Admin ────────────────────────────────────────────────────────────

  it("owner can setResolver and setFeeRecipient", async function () {
    await expect(escrow.connect(owner).setResolver(stranger.address))
      .to.emit(escrow, "ResolverUpdated")
      .withArgs(resolver.address, stranger.address);
    expect(await escrow.resolver()).to.equal(stranger.address);

    await expect(escrow.connect(owner).setFeeRecipient(stranger.address))
      .to.emit(escrow, "FeeRecipientUpdated")
      .withArgs(feeRecipient.address, stranger.address);
    expect(await escrow.feeRecipient()).to.equal(stranger.address);
  });

  it("non-owner cannot setResolver", async function () {
    await expect(
      escrow.connect(stranger).setResolver(stranger.address)
    ).to.be.revertedWithCustomError(escrow, "OwnableUnauthorizedAccount");
  });

  it("pause/unpause works", async function () {
    await escrow.connect(owner).pause();
    const matchId = ethers.id("match_paused2");
    await expect(
      escrow.connect(player1).createMatch(matchId, STAKE)
    ).to.be.revertedWithCustomError(escrow, "EnforcedPause");

    await escrow.connect(owner).unpause();
    await escrow.connect(player1).createMatch(matchId, STAKE); // should succeed
  });

  // ─── Views ────────────────────────────────────────────────────────────

  it("contractBalance returns escrow USDC balance", async function () {
    expect(await escrow.contractBalance()).to.equal(0);
    const matchId = ethers.id("match_bal");
    await escrow.connect(player1).createMatch(matchId, STAKE);
    expect(await escrow.contractBalance()).to.equal(STAKE);
  });

  it("getMatchStatus returns the status enum", async function () {
    const matchId = ethers.id("match_status");
    await escrow.connect(player1).createMatch(matchId, STAKE);
    expect(await escrow.getMatchStatus(matchId)).to.equal(0); // OPEN
    await escrow.connect(player2).joinMatch(matchId);
    expect(await escrow.getMatchStatus(matchId)).to.equal(1); // LOCKED
  });
});
