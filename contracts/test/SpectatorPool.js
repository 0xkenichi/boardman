const { expect } = require("chai");
const { ethers } = require("hardhat");

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
    await pool.connect(resolver).openBook(
      matchId,
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
    // pot = 2.4e6; fee 3% = 72_000; creator 2% = 48_000; dist = 2_280_000
    // fanWin side 0 = 1_000_000; fan1 claim = 2_280_000
    await pool.connect(resolver).resolve(matchId, 0);
    const b = await pool.getBook(matchId);
    expect(b.status).to.equal(3); // Resolved
    expect(b.winnerSide).to.equal(0);
    expect(b.fanWin).to.equal(1_000_000n);
    expect(b.distributable).to.equal(2_280_000n);
    expect(await pool.claimable(matchId, fan1.address)).to.equal(2_280_000n);
    expect(await pool.claimable(matchId, fan2.address)).to.equal(0);
    expect(await pool.claimable(matchId, agentA.address)).to.equal(0);

    await pool.connect(owner).pause();
    await pool.connect(fan1).claim(matchId);
    expect(await usdc.balanceOf(fan1.address)).to.equal(1_000_000_000n - 1_000_000n + 2_280_000n);
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
    expect(await pool.claimable(matchId, fan1.address)).to.equal(950_000n); // 1e6 * 95%
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
});
