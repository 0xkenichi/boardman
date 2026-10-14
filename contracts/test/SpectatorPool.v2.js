import hre from "hardhat";
const { ethers } = hre;
import { expect } from "chai";
import { time } from "@nomicfoundation/hardhat-network-helpers";
import {
  CLAIM_WINDOW,
  DAY,
  HOUR,
  REFUND_GRACE,
  deadlineIn,
  deployPool,
  prng,
  randBig,
} from "./helpers/boardman.js";

const OPEN = 1, CLOSED = 2, RESOLVED = 3, CANCELLED = 4;

describe("SpectatorPool v2 safety", function () {
  let usdc, pool, owner, resolver, fee, agentA, agentB, fans, multisig, creatorA, creatorB;
  const gameId = ethers.id("agentic.chess_standard");
  const agentIdA = ethers.id("agent_a");
  const agentIdB = ethers.id("agent_b");
  const books = []; // every matchId opened in a test, for the solvency check

  async function setup(Token = "MockUSDC") {
    const s = await ethers.getSigners();
    [owner, resolver, fee, agentA, agentB, multisig, creatorA, creatorB] = s;
    fans = s.slice(8, 14);
    usdc = await (await ethers.getContractFactory(Token)).deploy();
    await usdc.waitForDeployment();
    pool = await deployPool(usdc, fee, resolver);
    for (const x of [agentA, agentB, resolver, ...fans]) {
      await usdc.mint(x.address, 100_000_000_000n);
      await usdc.connect(x).approve(await pool.getAddress(), ethers.MaxUint256);
    }
    books.length = 0;
  }

  async function open(id, { cap = 10_000_000_000n, closeIn = HOUR, creators = true } = {}) {
    const closeAt = await deadlineIn(closeIn);
    await pool.connect(resolver).openBook(
      id,
      gameId,
      agentIdA,
      agentIdB,
      agentA.address,
      agentB.address,
      creators ? creatorA.address : ethers.ZeroAddress,
      creators ? creatorB.address : ethers.ZeroAddress,
      cap,
      closeAt
    );
    books.push(id);
    return closeAt;
  }

  /** balance == fees + creator credits + live pots + settled remainders, exactly. */
  async function expectSolvent() {
    let held = (await pool.protocolFees()) + (await pool.totalOwed());
    for (const id of books) {
      const b = await pool.getBook(id);
      if (Number(b.status) === OPEN || Number(b.status) === CLOSED) held += b.totalA + b.totalB + b.totalDraw;
      else held += b.remaining;
    }
    expect(await usdc.balanceOf(await pool.getAddress())).to.equal(held);
  }

  beforeEach(() => setup());

  // ─── closeAt deadline ────────────────────────────────────────────────────

  describe("betting deadline", function () {
    it("openBook bounds closeAt and emits BookTerms", async function () {
      const id = ethers.id("bounds");
      const now = BigInt(await time.latest());
      const args = [id, gameId, agentIdA, agentIdB, agentA.address, agentB.address, creatorA.address, creatorB.address, 1_000_000n];
      await expect(pool.connect(resolver).openBook(...args, now)).to.be.revertedWithCustomError(pool, "InvalidCloseAt");
      await expect(pool.connect(resolver).openBook(...args, now + 7n * DAY + 10n)).to.be.revertedWithCustomError(
        pool,
        "InvalidCloseAt"
      );
      const closeAt = now + 2n * HOUR;
      await expect(pool.connect(resolver).openBook(...args, closeAt))
        .to.emit(pool, "BookTerms")
        .withArgs(id, closeAt, 0);
      expect((await pool.getBook(id)).closeAt).to.equal(closeAt);
    });

    it("deposits, seeds and depositFor revert from closeAt even if close() was never called", async function () {
      const id = ethers.id("deadline");
      const closeAt = await open(id);
      await pool.connect(fans[0]).deposit(id, 1_000_000n, 0);
      expect(await pool.isBettingOpen(id)).to.equal(true);

      await time.increaseTo(closeAt);
      expect(await pool.isBettingOpen(id)).to.equal(false);
      expect((await pool.getBook(id)).status).to.equal(OPEN); // backend "forgot"
      await expect(pool.connect(fans[1]).deposit(id, 1_000_000n, 1))
        .to.be.revertedWithCustomError(pool, "BettingClosed")
        .withArgs(closeAt);
      await expect(pool.connect(resolver).depositFor(id, fans[1].address, 1_000_000n, 2)).to.be.revertedWithCustomError(
        pool,
        "BettingClosed"
      );
      await expect(pool.connect(agentA).seed(id, 0, 100_000n)).to.be.revertedWithCustomError(pool, "BettingClosed");
    });

    it("resolve needs Closed or closeAt; it reverts while betting is live", async function () {
      const id = ethers.id("resolve_gate");
      const closeAt = await open(id);
      await pool.connect(fans[0]).deposit(id, 2_000_000n, 0);
      await pool.connect(fans[1]).deposit(id, 2_000_000n, 1);
      await expect(pool.connect(resolver).resolve(id, 0))
        .to.be.revertedWithCustomError(pool, "BookStillOpen")
        .withArgs(closeAt);
      await time.increaseTo(closeAt);
      await pool.connect(resolver).resolve(id, 0); // no close() needed past the deadline
      expect((await pool.getBook(id)).status).to.equal(RESOLVED);
    });

    it("close() before closeAt stops deposits and allows resolve", async function () {
      const id = ethers.id("early_close");
      await open(id);
      await pool.connect(fans[0]).deposit(id, 2_000_000n, 0);
      await expect(pool.connect(resolver).close(id)).to.emit(pool, "BookClosed").withArgs(id);
      await expect(pool.connect(fans[1]).deposit(id, 1_000_000n, 1)).to.be.revertedWithCustomError(pool, "BookNotOpen");
      await pool.connect(resolver).resolve(id, 0);
    });
  });

  // ─── Refund timeout ──────────────────────────────────────────────────────

  describe("refund timeout", function () {
    it("constructor bounds refundGrace and claimWindow", async function () {
      const bad = [
        [HOUR - 1n, CLAIM_WINDOW],
        [30n * DAY + 1n, CLAIM_WINDOW],
        [REFUND_GRACE, 30n * DAY - 1n],
        [REFUND_GRACE, 730n * DAY + 1n],
      ];
      for (const [g, c] of bad) {
        await expect(deployPool(usdc, fee, resolver, g, c)).to.be.revertedWithCustomError(pool, "InvalidTimeout");
      }
    });

    it("unresolved past closeAt + grace: anyone refunds, resolve is no longer possible", async function () {
      const id = ethers.id("expire");
      const closeAt = await open(id);
      await pool.connect(agentA).seed(id, 0, 300_000n);
      await pool.connect(fans[0]).deposit(id, 1_000_000n, 0);
      await pool.connect(fans[1]).deposit(id, 2_000_000n, 2);
      await time.increaseTo(closeAt + REFUND_GRACE - 2n);
      await expect(pool.connect(fans[2]).refundExpired(id)).to.be.revertedWithCustomError(pool, "NotExpired");

      await time.increaseTo(closeAt + REFUND_GRACE);
      await expect(pool.connect(resolver).resolve(id, 0)).to.be.revertedWithCustomError(pool, "ResolveWindowElapsed");
      await pool.connect(owner).pause(); // refunds must work while paused
      await expect(pool.connect(fans[2]).refundExpired(id))
        .to.emit(pool, "BookExpired")
        .withArgs(id, fans[2].address);
      expect((await pool.getBook(id)).status).to.equal(CANCELLED);
      expect(await pool.claimable(id, agentA.address)).to.equal(300_000n);
      expect(await pool.claimable(id, fans[0].address)).to.equal(1_000_000n);
      expect(await pool.claimable(id, fans[1].address)).to.equal(2_000_000n);
      for (const x of [agentA, fans[0], fans[1]]) await pool.connect(x).claim(id);
      expect(await pool.contractBalance()).to.equal(0);
      await expect(pool.refundExpired(id)).to.be.revertedWithCustomError(pool, "AlreadyResolved");
      await expect(pool.refundExpired(ethers.id("none"))).to.be.revertedWithCustomError(pool, "BookNotFound");
    });
  });

  // ─── Fee caps and snapshot ───────────────────────────────────────────────

  describe("fee caps and snapshot", function () {
    it("caps bps at 10% and the flat fee at $1", async function () {
      const bad = [
        [1_000_000n, 1001, 1001, 10_000_000n, 1_000_000_000n],
        [1_000_000n, 700, 1001, 10_000_000n, 1_000_000_000n],
        [1_000_001n, 700, 1000, 10_000_000n, 1_000_000_000n],
        [1_000_000n, 10_000, 10_000, 10_000_000n, 1_000_000_000n], // v1 allowed 100%
        [1_000_000n, 700, 1000, 10_000_000n, 2n ** 96n], // overflow of the packed tier
      ];
      for (const args of bad) {
        await expect(pool.connect(owner).setSpectatorFeeTiers(...args)).to.be.revertedWithCustomError(
          pool,
          "InvalidFeeTiers"
        );
      }
      await pool.connect(owner).setSpectatorFeeTiers(1_000_000n, 1000, 1000, 10_000_000n, 1_000_000_000n);
      expect(await pool.feeScheduleCount()).to.equal(2);
    });

    it("a book keeps the fee schedule it was opened with", async function () {
      const before = ethers.id("snap_before");
      await open(before);
      await pool.connect(owner).setSpectatorFeeTiers(1_000_000n, 1000, 1000, 10_000_000n, 1_000_000_000n);
      const after = ethers.id("snap_after");
      await open(after);
      expect((await pool.getBook(before)).feeScheduleId).to.equal(0);
      expect((await pool.getBook(after)).feeScheduleId).to.equal(1);
      for (const id of [before, after]) {
        await pool.connect(fans[0]).deposit(id, 50_000_000n, 0);
        await pool.connect(fans[1]).deposit(id, 50_000_000n, 1);
        await pool.connect(resolver).close(id);
      }
      await expect(pool.connect(resolver).resolve(before, 0))
        .to.emit(pool, "BookResolved")
        .withArgs(before, 0, 100_000_000n, 7_000_000n, 2_000_000n, 91_000_000n, 50_000_000n);
      await expect(pool.connect(resolver).resolve(after, 0))
        .to.emit(pool, "BookResolved")
        .withArgs(after, 0, 100_000_000n, 10_000_000n, 2_000_000n, 88_000_000n, 50_000_000n);
    });
  });

  // ─── Pull payments ───────────────────────────────────────────────────────

  describe("pull payments with a blacklisting token", function () {
    beforeEach(() => setup("MockBlacklistUSDC"));

    it("blacklisted treasury and creator cannot block resolve", async function () {
      const id = ethers.id("bl");
      await open(id);
      await pool.connect(fans[0]).deposit(id, 50_000_000n, 0);
      await pool.connect(fans[1]).deposit(id, 50_000_000n, 1);
      await pool.connect(resolver).close(id);
      await usdc.setBlacklisted(fee.address, true);
      await usdc.setBlacklisted(creatorA.address, true);
      await pool.connect(resolver).resolve(id, 0);

      expect(await pool.owed(creatorA.address)).to.equal(1_500_000n);
      expect(await pool.owed(creatorB.address)).to.equal(500_000n);
      await pool.connect(fans[0]).claim(id); // winners are unaffected
      await pool.connect(creatorB).withdraw();
      await expect(pool.connect(creatorA).withdraw()).to.be.reverted; // still blacklisted, funds stay put
      await expect(pool.withdrawFees()).to.be.reverted;
      await pool.connect(owner).setFeeRecipient(multisig.address);
      await expect(pool.withdrawFees()).to.emit(pool, "FeesWithdrawn").withArgs(multisig.address, 7_000_000n);
      await expectSolvent();
    });
  });

  // ─── Sweep ───────────────────────────────────────────────────────────────

  describe("sweep", function () {
    it("sweeps only one settled book's dust and unclaimed winnings, after claimWindow", async function () {
      const id = ethers.id("sweep");
      const other = ethers.id("sweep_other");
      const live = ethers.id("sweep_live");
      await open(id);
      await open(other);
      // three winners whose split does not divide evenly
      await pool.connect(fans[0]).deposit(id, 1_000_001n, 0);
      await pool.connect(fans[1]).deposit(id, 2_000_003n, 0);
      await pool.connect(fans[2]).deposit(id, 3_333_333n, 0);
      await pool.connect(fans[3]).deposit(id, 7_777_777n, 1);
      await pool.connect(fans[0]).deposit(other, 5_000_000n, 0);
      await pool.connect(fans[1]).deposit(other, 5_000_000n, 1);
      await pool.connect(resolver).close(id);
      await pool.connect(resolver).close(other);
      await pool.connect(resolver).resolve(id, 0);
      await pool.connect(resolver).resolve(other, 1);
      await open(live, { closeIn: 7n * DAY });
      await pool.connect(fans[4]).deposit(live, 4_000_000n, 2);

      await expect(pool.connect(owner).sweep(live)).to.be.revertedWithCustomError(pool, "NotSettled");
      await expect(pool.connect(owner).sweep(id)).to.be.revertedWithCustomError(pool, "ClaimWindowActive");
      await expect(pool.connect(resolver).sweep(id)).to.be.revertedWithCustomError(pool, "OwnableUnauthorizedAccount");

      await pool.connect(fans[0]).claim(id);
      await pool.connect(fans[1]).claim(id); // fans[2] never claims
      const b = await pool.getBook(id);
      const unclaimed = await pool.claimable(id, fans[2].address);
      expect(b.remaining).to.be.gt(unclaimed); // rounding dust is on top
      expect(b.remaining - unclaimed).to.equal(2n); // floor dust from three winners

      await time.increase(CLAIM_WINDOW);
      const feesBefore = await pool.protocolFees();
      await expect(pool.connect(owner).sweep(id)).to.emit(pool, "BookSwept").withArgs(id, b.remaining);
      expect(await pool.protocolFees()).to.equal(feesBefore + b.remaining);
      expect((await pool.getBook(id)).remaining).to.equal(0);
      expect(await pool.claimable(id, fans[2].address)).to.equal(0);
      await expect(pool.connect(fans[2]).claim(id)).to.be.revertedWithCustomError(pool, "NothingToClaim");
      await expect(pool.connect(owner).sweep(id)).to.be.revertedWithCustomError(pool, "AlreadySwept");

      // the neighbouring settled book and the live one are untouched
      expect((await pool.getBook(other)).remaining).to.equal(9_100_000n); // 10M - 7% - 2%
      await pool.connect(fans[1]).claim(other);
      await expectSolvent();
    });

    it("nothing to sweep once every claimant has claimed a refund book", async function () {
      const id = ethers.id("sweep_empty");
      await open(id);
      await pool.connect(fans[0]).deposit(id, 1_000_000n, 0);
      await pool.connect(resolver).cancel(id);
      await pool.connect(fans[0]).claim(id);
      await time.increase(CLAIM_WINDOW);
      await expect(pool.connect(owner).sweep(id)).to.be.revertedWithCustomError(pool, "NothingToSweep");
    });
  });

  // ─── Roles and pause ─────────────────────────────────────────────────────

  describe("roles and pause", function () {
    it("owner cannot run books; ownership is two-step and cannot be renounced", async function () {
      const id = ethers.id("roles");
      const closeAt = await deadlineIn();
      await expect(
        pool.connect(owner).openBook(id, gameId, agentIdA, agentIdB, agentA.address, agentB.address, creatorA.address, creatorB.address, 1n, closeAt)
      ).to.be.revertedWithCustomError(pool, "NotResolver");
      await open(id);
      for (const call of [
        () => pool.connect(owner).close(id),
        () => pool.connect(owner).resolve(id, 0),
        () => pool.connect(owner).cancel(id),
        () => pool.connect(owner).depositFor(id, fans[0].address, 1n, 0),
      ]) {
        await expect(call()).to.be.revertedWithCustomError(pool, "NotResolver");
      }
      await expect(pool.connect(resolver).pause()).to.be.revertedWithCustomError(pool, "OwnableUnauthorizedAccount");

      await pool.connect(owner).transferOwnership(multisig.address);
      expect(await pool.owner()).to.equal(owner.address);
      await pool.connect(multisig).acceptOwnership();
      expect(await pool.owner()).to.equal(multisig.address);
      await expect(pool.connect(multisig).renounceOwnership()).to.be.revertedWithCustomError(pool, "RenounceDisabled");
      await expect(pool.connect(multisig).setResolver(fans[0].address))
        .to.emit(pool, "ResolverUpdated")
        .withArgs(resolver.address, fans[0].address);
    });

    it("pause blocks money in only; close, resolve, cancel, claim, withdraw, sweep keep working", async function () {
      const a = ethers.id("pa"), c = ethers.id("pc");
      await open(a);
      await open(c);
      await pool.connect(fans[0]).deposit(a, 20_000_000n, 0);
      await pool.connect(fans[1]).deposit(a, 20_000_000n, 1);
      await pool.connect(fans[2]).deposit(c, 1_000_000n, 1);
      await pool.connect(owner).pause();

      await expect(open(ethers.id("pnew"))).to.be.revertedWithCustomError(pool, "EnforcedPause");
      await expect(pool.connect(fans[0]).deposit(a, 1n, 0)).to.be.revertedWithCustomError(pool, "EnforcedPause");
      await expect(pool.connect(agentA).seed(a, 0, 1n)).to.be.revertedWithCustomError(pool, "EnforcedPause");

      await pool.connect(resolver).close(a);
      await pool.connect(resolver).resolve(a, 1);
      await pool.connect(resolver).cancel(c);
      await pool.connect(fans[1]).claim(a);
      await pool.connect(creatorB).withdraw();
      await pool.withdrawFees();
      await time.increase(CLAIM_WINDOW);
      await pool.connect(owner).sweep(c);
      await expectSolvent();
    });
  });

  // ─── Property: shares never over-allocate; the pool stays solvent ────────

  it("property: random books never pay out more than they hold", async function () {
    const rand = prng(0x5bec7);
    const sides = [0, 1, 2];
    for (let round = 0; round < 6; round++) {
      const id = ethers.id(`prop_${round}`);
      await open(id, { creators: rand() < 0.5 });
      if (rand() < 0.5) await pool.connect(agentA).seed(id, 0, randBig(rand, 1n, 2_000_000n));
      if (rand() < 0.5) await pool.connect(agentB).seed(id, 2, randBig(rand, 1n, 2_000_000n));
      const n = 3 + Math.floor(rand() * 10);
      for (let i = 0; i < n; i++) {
        const fan = fans[Math.floor(rand() * fans.length)];
        const amt = randBig(rand, 1n, rand() < 0.3 ? 5_000_000n : 500_000_000n);
        await pool.connect(fan).deposit(id, amt, sides[Math.floor(rand() * 3)]);
      }
      await expectSolvent();
      const outcome = [0, 1, -2, "cancel", "expire"][Math.floor(rand() * 5)];
      if (outcome === "cancel") {
        await pool.connect(resolver).cancel(id);
      } else if (outcome === "expire") {
        await time.increase(HOUR + REFUND_GRACE);
        await pool.refundExpired(id);
      } else {
        await pool.connect(resolver).close(id);
        await pool.connect(resolver).resolve(id, outcome);
      }
      const b = await pool.getBook(id);
      const pot = b.totalA + b.totalB + b.totalDraw;
      const claimants = [...fans, agentA, agentB];
      let sum = 0n;
      let winners = 0n;
      for (const x of claimants) {
        const c = await pool.claimable(id, x.address);
        if (c > 0n) {
          winners += 1n;
          sum += c;
          await pool.connect(x).claim(id);
        }
      }
      if (b.fanWin > 0n) {
        // pari-mutuel: never more than distributable, dust < one unit per winner
        expect(sum).to.be.lte(b.distributable);
        expect(b.distributable - sum).to.be.lt(winners + 1n);
      } else {
        expect(sum).to.equal(pot); // refunds are exact
      }
      expect((await pool.getBook(id)).remaining).to.equal(b.remaining - sum);
      await expectSolvent();
    }
  });
});
