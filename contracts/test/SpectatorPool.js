import hre from "hardhat";
const { ethers } = hre;
import { expect } from "chai";

describe("SpectatorPool", function () {
  let usdc, pool, owner, resolver, fee, agentA, agentB, fan1, fan2;
  const matchId = ethers.id("agm_test_1");
  const gameId = ethers.id("agentic.chess_standard");
  const agentIdA = ethers.id("agent_a");
  const agentIdB = ethers.id("agent_b");

  async function deploy() {
    [owner, resolver, fee, agentA, agentB, fan1, fan2] = await ethers.getSigners();
    const Mock = await ethers.getContractFactory("MockUSDC");
    usdc = await Mock.deploy();
    await usdc.waitForDeployment();
    const Pool = await ethers.getContractFactory("SpectatorPool");
    pool = await Pool.deploy(await usdc.getAddress(), fee.address, resolver.address);
    await pool.waitForDeployment();
    for (const s of [agentA, agentB, fan1, fan2, resolver]) {
      await usdc.mint(s.address, 1_000_000_000n); // 1000 USDC
      await usdc.connect(s).approve(await pool.getAddress(), ethers.MaxUint256);
    }
  }

  async function open(cap = 20_000_000n) {
    await openBook(matchId, cap);
  }

  async function openBook(id, cap = 20_000_000n) {
    await pool.connect(resolver).openBook(
      id,
      gameId,
      agentIdA,
      agentIdB,
      agentA.address,
      agentB.address,
      ethers.ZeroAddress,
      ethers.ZeroAddress,
      cap
    );
  }

  beforeEach(deploy);

  it("opens a book and records a fan deposit with Deposited event", async function () {
    await open();
    await expect(pool.connect(fan1).deposit(matchId, 1_000_000n, 0))
      .to.emit(pool, "Deposited")
      .withArgs(matchId, fan1.address, 0, 1_000_000n);
    expect(await pool.fanDepositOf(matchId, fan1.address, 0)).to.equal(1_000_000n);
    const b = await pool.getBook(matchId);
    expect(b.status).to.equal(1); // Open
    expect(b.totalA).to.equal(1_000_000n);
  });

  it("depositFor credits the user, pulls USDC from resolver", async function () {
    await open();
    const before = await usdc.balanceOf(resolver.address);
    await expect(pool.connect(resolver).depositFor(matchId, fan1.address, 2_500_000n, 1))
      .to.emit(pool, "Deposited")
      .withArgs(matchId, fan1.address, 1, 2_500_000n);
    expect(await pool.fanDepositOf(matchId, fan1.address, 1)).to.equal(2_500_000n);
    expect(await usdc.balanceOf(resolver.address)).to.equal(before - 2_500_000n);
    expect(await usdc.balanceOf(await pool.getAddress())).to.equal(2_500_000n);
  });

  it("non-resolver cannot depositFor", async function () {
    await open();
    await expect(
      pool.connect(fan1).depositFor(matchId, fan1.address, 1_000_000n, 0)
    ).to.be.revertedWithCustomError(pool, "NotResolver");
  });

  it("reverts deposit when book is not open", async function () {
    await expect(pool.connect(fan1).deposit(matchId, 1_000_000n, 0)).to.be.revertedWithCustomError(
      pool,
      "BookNotOpen"
    );
  });

  it("enforces pot cap", async function () {
    await open(2_000_000n);
    await pool.connect(fan1).deposit(matchId, 1_500_000n, 0);
    await expect(pool.connect(fan2).deposit(matchId, 600_000n, 1)).to.be.revertedWithCustomError(
      pool,
      "PotFull"
    );
  });

  it("seed is once per side and only from the bound agent wallet", async function () {
    await open();
    await expect(pool.connect(fan1).seed(matchId, 0, 100_000n)).to.be.revertedWithCustomError(
      pool,
      "NotAgentWallet"
    );
    await pool.connect(agentA).seed(matchId, 0, 100_000n);
    await expect(pool.connect(agentA).seed(matchId, 0, 50_000n)).to.be.revertedWithCustomError(
      pool,
      "AlreadySeeded"
    );
    const b = await pool.getBook(matchId);
    expect(b.seedA).to.equal(100_000n);
    expect(b.totalA).to.equal(100_000n);
    expect(await pool.seedOf(matchId, agentA.address)).to.equal(100_000n);
    expect(await pool.fanDepositOf(matchId, agentA.address, 0)).to.equal(0);
  });

  it("resolve pays winning fans pro-rata; seeds sink; claim works while paused", async function () {
    await open();
    await pool.connect(agentA).seed(matchId, 0, 200_000n);
    await pool.connect(agentB).seed(matchId, 1, 200_000n);
    await pool.connect(fan1).deposit(matchId, 1_000_000n, 0);
    await pool.connect(fan2).deposit(matchId, 1_000_000n, 1);
    // pot = 2.4e6 ($2.40 dust tier): fee = min($1, 25%) = 600_000; creator 2% = 48_000; dist = 1_752_000
    // fanWin side 0 = 1_000_000; fan1 claim = 1_752_000
    await pool.connect(resolver).resolve(matchId, 0);
    const b = await pool.getBook(matchId);
    expect(b.status).to.equal(3); // Resolved
    expect(b.winnerSide).to.equal(0);
    expect(b.fanWin).to.equal(1_000_000n);
    expect(b.distributable).to.equal(1_752_000n);
    expect(await pool.claimable(matchId, fan1.address)).to.equal(1_752_000n);
    expect(await pool.claimable(matchId, fan2.address)).to.equal(0);
    expect(await pool.claimable(matchId, agentA.address)).to.equal(0);

    await pool.connect(owner).pause();
    await pool.connect(fan1).claim(matchId);
    expect(await usdc.balanceOf(fan1.address)).to.equal(1_000_000_000n - 1_000_000n + 1_752_000n);
    await expect(pool.connect(fan1).claim(matchId)).to.be.revertedWithCustomError(
      pool,
      "NothingToClaim"
    );
  });

  it("cancel refunds fan deposits and seeds", async function () {
    await open();
    await pool.connect(agentA).seed(matchId, 0, 300_000n);
    await pool.connect(fan1).deposit(matchId, 700_000n, 1);
    await pool.connect(resolver).cancel(matchId);
    expect((await pool.getBook(matchId)).status).to.equal(4); // Cancelled
    expect(await pool.claimable(matchId, fan1.address)).to.equal(700_000n);
    expect(await pool.claimable(matchId, agentA.address)).to.equal(300_000n);
    await pool.connect(fan1).claim(matchId);
    await pool.connect(agentA).claim(matchId);
  });

  it("resolve with no winning fans refunds (fanWin == 0)", async function () {
    await open();
    await pool.connect(agentA).seed(matchId, 0, 100_000n);
    await pool.connect(fan1).deposit(matchId, 400_000n, 1);
    await pool.connect(resolver).resolve(matchId, 0); // side 0 has only seed
    const b = await pool.getBook(matchId);
    expect(b.winnerSide).to.equal(-1);
    expect(b.fanWin).to.equal(0);
    expect(await pool.claimable(matchId, fan1.address)).to.equal(400_000n);
    expect(await pool.claimable(matchId, agentA.address)).to.equal(100_000n);
  });

  it("rejects a second openBook and zero potCap", async function () {
    await open();
    await expect(open()).to.be.revertedWithCustomError(pool, "BookExists");
    const other = ethers.id("agm_test_2");
    await expect(
      pool.connect(resolver).openBook(
        other,
        gameId,
        agentIdA,
        agentIdB,
        agentA.address,
        agentB.address,
        ethers.ZeroAddress,
        ethers.ZeroAddress,
        0
      )
    ).to.be.revertedWithCustomError(pool, "ZeroAmount");
  });

  it("rejects duplicate agents / zero wallets", async function () {
    await expect(
      pool.connect(resolver).openBook(
        matchId,
        gameId,
        agentIdA,
        agentIdA,
        agentA.address,
        agentB.address,
        ethers.ZeroAddress,
        ethers.ZeroAddress,
        1_000_000n
      )
    ).to.be.revertedWithCustomError(pool, "DuplicateAgents");
    await expect(
      pool.connect(resolver).openBook(
        matchId,
        gameId,
        agentIdA,
        agentIdB,
        ethers.ZeroAddress,
        agentB.address,
        ethers.ZeroAddress,
        ethers.ZeroAddress,
        1_000_000n
      )
    ).to.be.revertedWithCustomError(pool, "ZeroAddress");
  });

  it("close blocks further deposits; resolve still works", async function () {
    await open();
    await pool.connect(fan1).deposit(matchId, 1_000_000n, 0);
    await pool.connect(resolver).close(matchId);
    await expect(pool.connect(fan2).deposit(matchId, 1_000_000n, 1)).to.be.revertedWithCustomError(
      pool,
      "BookNotOpen"
    );
    await pool.connect(resolver).resolve(matchId, 0);
    expect(await pool.claimable(matchId, fan1.address)).to.equal(730_000n); // dust: 25% fee + 2% creator
  });

  it("pause blocks deposit and depositFor but not claim", async function () {
    await open();
    await pool.connect(fan1).deposit(matchId, 1_000_000n, 0);
    await pool.connect(owner).pause();
    await expect(pool.connect(fan2).deposit(matchId, 1_000_000n, 1)).to.be.revertedWithCustomError(
      pool,
      "EnforcedPause"
    );
    await expect(
      pool.connect(resolver).depositFor(matchId, fan2.address, 1_000_000n, 1)
    ).to.be.revertedWithCustomError(pool, "EnforcedPause");
    await pool.connect(resolver).resolve(matchId, 0);
    await pool.connect(fan1).claim(matchId);
  });

  it("v2: draw side deposits win the whole pot; A/B tickets lose", async function () {
    await open();
    await pool.connect(agentA).seed(matchId, 0, 200_000n);
    await pool.connect(agentB).seed(matchId, 1, 200_000n);
    await pool.connect(agentA).seed(matchId, 2, 150_000n);
    await pool.connect(agentB).seed(matchId, 2, 150_000n);
    await pool.connect(fan1).deposit(matchId, 1_000_000n, 0); // A side — loses
    await pool.connect(fan2).deposit(matchId, 500_000n, 2); // draw — wins
    // pot = 2.2e6 (dust): fee = min($1, 25%) = 550_000; creator 2% = 44_000; dist = 1_606_000
    // fanWin = draw deposits only = 500_000; fan2 claim = 1_606_000
    await pool.connect(resolver).resolve(matchId, -2);
    const b = await pool.getBook(matchId);
    expect(b.status).to.equal(3);
    expect(b.winnerSide).to.equal(-2);
    expect(b.fanWin).to.equal(500_000n);
    expect(b.distributable).to.equal(1_606_000n);
    expect(await pool.claimable(matchId, fan2.address)).to.equal(1_606_000n);
    expect(await pool.claimable(matchId, fan1.address)).to.equal(0);
    expect(await pool.claimable(matchId, agentA.address)).to.equal(0); // seeds sink into pot
    await pool.connect(fan2).claim(matchId);
  });

  it("v2: creator pool is winner-weighted (75/25) with creator wallets set", async function () {
    // openBook with creatorA = agentA, creatorB = agentB
    await pool.connect(resolver).openBook(
      matchId,
      gameId,
      agentIdA,
      agentIdB,
      agentA.address,
      agentB.address,
      agentA.address,
      agentB.address,
      20_000_000n
    );
    await pool.connect(fan1).deposit(matchId, 1_000_000n, 0);
    await pool.connect(fan2).deposit(matchId, 1_000_000n, 1);
    // pot = 2e6 (dust): fee = min($1, 25%) = 500_000; creator 2% = 40_000 (A 75% = 30_000, B 25% = 10_000)
    await pool.connect(resolver).resolve(matchId, 0);
    expect(await usdc.balanceOf(agentA.address)).to.equal(1_000_000_000n + 30_000n);
    expect(await usdc.balanceOf(agentB.address)).to.equal(1_000_000_000n + 10_000n);
    expect(await usdc.balanceOf(fee.address)).to.equal(500_000n);
  });

  // ─── Tiered platform fee ─────────────────────────────────────────────

  it("mid tier 7% applies up to a $1000 pot; premium 10% above", async function () {
    // mid tier: pot $800
    const m1 = ethers.id("agm_tier_mid");
    await openBook(m1, 2_000_000_000n);
    await pool.connect(fan1).deposit(m1, 400_000_000n, 0);
    await pool.connect(fan2).deposit(m1, 400_000_000n, 1);
    await pool.connect(resolver).resolve(m1, 0);
    // platform 7% of 800e6 = 56e6; creator 2% = 16e6 — creators are ZeroAddress
    // here, so the creator pool falls back to feeRecipient too.
    expect(await usdc.balanceOf(fee.address)).to.equal(72_000_000n);

    // premium tier: pot $1200
    const m2 = ethers.id("agm_tier_premium");
    await openBook(m2, 2_000_000_000n);
    await pool.connect(fan1).deposit(m2, 600_000_000n, 0);
    await pool.connect(fan2).deposit(m2, 600_000_000n, 1);
    await pool.connect(resolver).resolve(m2, 1);
    // platform 10% of 1.2e9 = 120e6; creator 2% = 24e6 → feeRecipient (zero creators)
    expect(await usdc.balanceOf(fee.address)).to.equal(72_000_000n + 144_000_000n);
  });

  it("dust boundary: $10 pot is mid tier, just below is flat-capped", async function () {
    // exactly $10 pot → mid tier: 7% = 700_000
    const m1 = ethers.id("agm_tier_edge_1");
    await openBook(m1, 2_000_000_000n);
    await pool.connect(fan1).deposit(m1, 5_000_000n, 0);
    await pool.connect(fan2).deposit(m1, 5_000_000n, 1);
    await pool.connect(resolver).resolve(m1, 0);
    // 7% = 700_000 + creator 2% = 200_000 (zero-creator fallback to feeRecipient)
    expect(await usdc.balanceOf(fee.address)).to.equal(900_000n);

    // $9.99 pot → dust tier: min(1e6, 2_499_999) = 1_000_000
    const m2 = ethers.id("agm_tier_edge_2");
    await openBook(m2, 2_000_000_000n);
    await pool.connect(fan1).deposit(m2, 9_999_999n, 0);
    await pool.connect(resolver).resolve(m2, 0);
    // flat 1_000_000 + creator 199_999 (zero-creator fallback)
    expect(await usdc.balanceOf(fee.address)).to.equal(900_000n + 1_199_999n);
  });

  it("owner can retune spectator tiers; invalid sets revert", async function () {
    await expect(
      pool.connect(owner).setSpectatorFeeTiers(500_000n, 500, 800, 8_000_000n, 800_000_000n)
    )
      .to.emit(pool, "SpectatorFeeTiersUpdated")
      .withArgs(500_000n, 500, 800, 8_000_000n, 800_000_000n);
    expect(await pool.PLATFORM_FEE_BPS()).to.equal(500);
    expect(await pool.PREMIUM_FEE_BPS()).to.equal(800);
    expect(await pool.FLAT_FEE()).to.equal(500_000n);

    await expect(
      pool.connect(owner).setSpectatorFeeTiers(500_000n, 800, 500, 8_000_000n, 800_000_000n)
    ).to.be.revertedWithCustomError(pool, "InvalidFeeTiers");
    await expect(
      pool.connect(fan1).setSpectatorFeeTiers(500_000n, 500, 800, 8_000_000n, 800_000_000n)
    ).to.be.revertedWithCustomError(pool, "OwnableUnauthorizedAccount");
  });

  it("v2: draw seeds return to both agents on cancel", async function () {
    await open();
    await pool.connect(agentA).seed(matchId, 2, 300_000n);
    await pool.connect(agentB).seed(matchId, 2, 300_000n);
    await pool.connect(fan1).deposit(matchId, 400_000n, 2);
    await pool.connect(resolver).cancel(matchId);
    expect(await pool.claimable(matchId, agentA.address)).to.equal(300_000n);
    expect(await pool.claimable(matchId, agentB.address)).to.equal(300_000n);
    expect(await pool.claimable(matchId, fan1.address)).to.equal(400_000n);
    await pool.connect(agentA).claim(matchId);
    await pool.connect(agentB).claim(matchId);
    await pool.connect(fan1).claim(matchId);
  });
});
