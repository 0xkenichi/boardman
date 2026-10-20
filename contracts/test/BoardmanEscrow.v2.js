import hre from "hardhat";
const { ethers } = hre;
import { expect } from "chai";
import { time } from "@nomicfoundation/hardhat-network-helpers";
import {
  CREATE_MATCH_TYPES,
  DAY,
  HOUR,
  LOCK_TIMEOUT,
  OPEN_TIMEOUT,
  createMatch,
  deadlineIn,
  deployEscrow,
  escrowDomain,
  prng,
  randBig,
  signCreate,
} from "./helpers/boardman.js";

const STAKE = 5_000_000n;
const OPEN = 0, LOCKED = 1, DISPUTED = 2, RESOLVED = 3, CANCELLED = 4;

describe("BoardmanEscrow v2 safety", function () {
  let usdc, escrow, owner, resolver, feeRecipient, player1, player2, stranger, multisig;

  async function setup(Token = "MockUSDC") {
    [owner, resolver, feeRecipient, player1, player2, stranger, multisig] = await ethers.getSigners();
    usdc = await (await ethers.getContractFactory(Token)).deploy();
    await usdc.waitForDeployment();
    escrow = await deployEscrow(usdc, feeRecipient, resolver);
    for (const s of [player1, player2, stranger]) {
      await usdc.mint(s.address, 100_000_000_000n);
      await usdc.connect(s).approve(await escrow.getAddress(), ethers.MaxUint256);
    }
  }

  const create = (id, stake = STAKE, p1 = player1, p2 = player2) =>
    createMatch(escrow, resolver, id, stake, p1, p2);

  async function locked(id, stake = STAKE) {
    await create(id, stake);
    await escrow.connect(player2).joinMatch(id);
  }

  /** balance == stakes held + accrued fees + deferred payouts, exactly. */
  async function expectSolvent() {
    const bal = await usdc.balanceOf(await escrow.getAddress());
    const owed = (await escrow.totalLocked()) + (await escrow.accruedFees()) + (await escrow.totalOwed());
    expect(bal).to.equal(owed);
  }

  beforeEach(() => setup());

  // ─── Permit + opponent binding (front-running) ───────────────────────────

  describe("create permit and opponent binding", function () {
    it("hashCreateMatch matches the standard EIP-712 digest", async function () {
      const id = ethers.id("digest");
      const deadline = 123456789n;
      const expected = ethers.TypedDataEncoder.hash(await escrowDomain(escrow), CREATE_MATCH_TYPES, {
        matchId: id,
        player1: player1.address,
        player2: player2.address,
        stake: STAKE,
        deadline,
      });
      expect(await escrow.hashCreateMatch(id, player1.address, player2.address, STAKE, deadline)).to.equal(expected);
      expect(await escrow.DOMAIN_SEPARATOR()).to.equal(
        ethers.TypedDataEncoder.hashDomain(await escrowDomain(escrow))
      );
    });

    it("emits MatchTerms with the bound opponent and fee snapshot", async function () {
      const id = ethers.id("terms");
      const deadline = await deadlineIn();
      const sig = await signCreate(escrow, resolver, {
        matchId: id, player1: player1.address, player2: player2.address, stake: STAKE, deadline,
      });
      await expect(escrow.connect(player1).createMatch(id, player2.address, STAKE, deadline, sig))
        .to.emit(escrow, "MatchTerms")
        .withArgs(id, player2.address, 700_000n, deadline);
      expect((await escrow.getMatch(id)).platformFee).to.equal(700_000n);
    });

    it("rejects a permit not signed by the resolver (owner, stranger, player)", async function () {
      const id = ethers.id("bad_signer");
      const deadline = await deadlineIn();
      for (const signer of [owner, stranger, player1]) {
        const sig = await signCreate(escrow, signer, {
          matchId: id, player1: player1.address, player2: player2.address, stake: STAKE, deadline,
        });
        await expect(
          escrow.connect(player1).createMatch(id, player2.address, STAKE, deadline, sig)
        ).to.be.revertedWithCustomError(escrow, "InvalidPermit");
      }
    });

    it("a front-runner cannot replay the backend's permit to squat the matchId", async function () {
      const id = ethers.id("squat");
      const deadline = await deadlineIn();
      const sig = await signCreate(escrow, resolver, {
        matchId: id, player1: player1.address, player2: player2.address, stake: STAKE, deadline,
      });
      // Attacker copies the pending calldata and submits it first.
      await expect(
        escrow.connect(stranger).createMatch(id, player2.address, STAKE, deadline, sig)
      ).to.be.revertedWithCustomError(escrow, "InvalidPermit");
      // ...or tweaks it to bind themselves as the opponent / change the stake.
      await expect(
        escrow.connect(player1).createMatch(id, stranger.address, STAKE, deadline, sig)
      ).to.be.revertedWithCustomError(escrow, "InvalidPermit");
      await expect(
        escrow.connect(player1).createMatch(id, player2.address, STAKE + 1n, deadline, sig)
      ).to.be.revertedWithCustomError(escrow, "InvalidPermit");
      await expect(
        escrow.connect(player1).createMatch(id, player2.address, STAKE, deadline + 1n, sig)
      ).to.be.revertedWithCustomError(escrow, "InvalidPermit");
      // The legitimate player1 still gets the id.
      await escrow.connect(player1).createMatch(id, player2.address, STAKE, deadline, sig);
      expect((await escrow.getMatch(id)).player1).to.equal(player1.address);
    });

    it("rejects garbage and wrong-length signatures", async function () {
      const id = ethers.id("garbage");
      const deadline = await deadlineIn();
      await expect(
        escrow.connect(player1).createMatch(id, player2.address, STAKE, deadline, "0x")
      ).to.be.revertedWithCustomError(escrow, "InvalidPermit");
      await expect(
        escrow.connect(player1).createMatch(id, player2.address, STAKE, deadline, "0x" + "11".repeat(65))
      ).to.be.revertedWithCustomError(escrow, "InvalidPermit");
    });

    it("rejects an expired permit", async function () {
      const id = ethers.id("expired_permit");
      const deadline = await deadlineIn(60n);
      const sig = await signCreate(escrow, resolver, {
        matchId: id, player1: player1.address, player2: player2.address, stake: STAKE, deadline,
      });
      await time.increaseTo(deadline + 1n);
      await expect(
        escrow.connect(player1).createMatch(id, player2.address, STAKE, deadline, sig)
      ).to.be.revertedWithCustomError(escrow, "PermitExpired");
    });

    it("rotating the resolver invalidates outstanding permits", async function () {
      const id = ethers.id("rotated");
      const deadline = await deadlineIn();
      const sig = await signCreate(escrow, resolver, {
        matchId: id, player1: player1.address, player2: player2.address, stake: STAKE, deadline,
      });
      await escrow.connect(owner).setResolver(stranger.address);
      await expect(
        escrow.connect(player1).createMatch(id, player2.address, STAKE, deadline, sig)
      ).to.be.revertedWithCustomError(escrow, "InvalidPermit");
    });

    it("rejects zero or self opponent", async function () {
      const id = ethers.id("bad_opponent");
      const deadline = await deadlineIn();
      await expect(
        escrow.connect(player1).createMatch(id, ethers.ZeroAddress, STAKE, deadline, "0x")
      ).to.be.revertedWithCustomError(escrow, "ZeroAddress");
      await expect(
        escrow.connect(player1).createMatch(id, player1.address, STAKE, deadline, "0x")
      ).to.be.revertedWithCustomError(escrow, "NotPlayer");
    });

    it("only the bound player2 can join", async function () {
      const id = ethers.id("bound_join");
      await create(id);
      await expect(escrow.connect(stranger).joinMatch(id))
        .to.be.revertedWithCustomError(escrow, "NotPlayer")
        .withArgs(stranger.address);
      await escrow.connect(player2).joinMatch(id);
      expect(await escrow.getMatchStatus(id)).to.equal(LOCKED);
    });

    it("matches() keeps the v1 six-field shape", async function () {
      const id = ethers.id("compat");
      await create(id);
      const r = await escrow.matches(id);
      expect(r.length).to.equal(6);
      expect(r[0]).to.equal(player1.address);
      expect(r[1]).to.equal(player2.address);
      expect(r[2]).to.equal(STAKE);
      expect(r[3]).to.equal(OPEN);
    });
  });

  // ─── Fee caps and snapshot ───────────────────────────────────────────────

  describe("fee caps and snapshot", function () {
    it("caps bps at 10% and the flat fee at MIN_STAKE / 4", async function () {
      expect(await escrow.MAX_FEE_BPS()).to.equal(1000);
      expect(await escrow.MAX_FLAT_FEE_PER_PLAYER()).to.equal(500_000n);
      const bad = [
        [500_000n, 1001, 1001, 5_000_000n, 500_000_000n], // mid bps over cap
        [500_000n, 700, 1001, 5_000_000n, 500_000_000n], // premium over cap
        [500_001n, 700, 1000, 5_000_000n, 500_000_000n], // flat over cap
        [500_000n, 10_000, 10_000, 5_000_000n, 500_000_000n], // v1 allowed 100%
        [ethers.MaxUint256, 700, 1000, 5_000_000n, 500_000_000n], // v1 allowed uncapped flat
      ];
      for (const args of bad) {
        await expect(escrow.connect(owner).setFeeTiers(...args)).to.be.revertedWithCustomError(
          escrow,
          "InvalidFeeTiers"
        );
      }
      // exactly at the caps is fine
      await escrow.connect(owner).setFeeTiers(500_000n, 1000, 1000, 5_000_000n, 500_000_000n);
    });

    it("resolve uses the fee snapshotted at create, not the current tiers", async function () {
      const id = ethers.id("snapshot");
      await locked(id, 25_000_000n); // 7% of $50 = $3.50
      await escrow.connect(owner).setFeeTiers(500_000n, 1000, 1000, 5_000_000n, 500_000_000n);
      expect(await escrow.quotePlatformFee(25_000_000n)).to.equal(5_000_000n); // new matches pay 10%
      await expect(escrow.connect(resolver).resolveMatch(id, player1.address))
        .to.emit(escrow, "MatchResolved")
        .withArgs(id, player1.address, 50_000_000n - 3_500_000n, 3_500_000n);

      const id2 = ethers.id("snapshot_after");
      await locked(id2, 25_000_000n);
      expect((await escrow.getMatch(id2)).platformFee).to.equal(5_000_000n);
    });

    it("property: fee ≤ pot/4 and payout + fee == pot for random stakes and max tiers", async function () {
      await escrow.connect(owner).setFeeTiers(500_000n, 1000, 1000, 10_000e6, 10_000e6);
      const rand = prng(0xb0a7d);
      for (let i = 0; i < 200; i++) {
        const stake = randBig(rand, 2_000_000n, 10_000_000_000n);
        const fee = await escrow.quotePlatformFee(stake);
        expect(fee).to.be.lte((stake * 2n) / 4n);
      }
      // a handful of full lifecycles at random stakes
      for (let i = 0; i < 6; i++) {
        const stake = randBig(rand, 2_000_000n, 1_000_000_000n);
        const id = ethers.id(`prop_${i}`);
        await locked(id, stake);
        const before = await usdc.balanceOf(player2.address);
        await escrow.connect(resolver).resolveMatch(id, player2.address);
        const fee = (await escrow.getMatch(id)).platformFee;
        expect((await usdc.balanceOf(player2.address)) - before + fee).to.equal(stake * 2n);
        await expectSolvent();
      }
    });
  });

  // ─── Timeouts / liveness ─────────────────────────────────────────────────

  describe("timeouts", function () {
    it("constructor bounds the timeouts", async function () {
      const bad = [
        [HOUR - 1n, LOCK_TIMEOUT],
        [7n * DAY + 1n, LOCK_TIMEOUT],
        [OPEN_TIMEOUT, DAY - 1n],
        [OPEN_TIMEOUT, 30n * DAY + 1n],
      ];
      for (const [o, l] of bad) {
        await expect(deployEscrow(usdc, feeRecipient, resolver, o, l)).to.be.revertedWithCustomError(
          escrow,
          "InvalidTimeout"
        );
      }
      await deployEscrow(usdc, feeRecipient, resolver, HOUR, DAY);
      await deployEscrow(usdc, feeRecipient, resolver, 7n * DAY, 30n * DAY);
    });

    it("OPEN past openTimeout: anyone refunds player1 only; join is closed", async function () {
      const id = ethers.id("open_expiry");
      await create(id);
      const created = (await escrow.getMatch(id)).createdAt;
      expect(await escrow.refundableAt(id)).to.equal(created + OPEN_TIMEOUT);

      await expect(escrow.connect(stranger).refundExpired(id)).to.be.revertedWithCustomError(escrow, "NotExpired");
      await time.increaseTo(created + OPEN_TIMEOUT);
      await expect(escrow.connect(player2).joinMatch(id)).to.be.revertedWithCustomError(
        escrow,
        "MatchExpiredForJoin"
      );

      const p1 = await usdc.balanceOf(player1.address);
      const p2 = await usdc.balanceOf(player2.address);
      await expect(escrow.connect(stranger).refundExpired(id))
        .to.emit(escrow, "MatchExpired")
        .withArgs(id, stranger.address)
        .and.to.emit(escrow, "MatchCancelled");
      expect(await usdc.balanceOf(player1.address)).to.equal(p1 + STAKE);
      expect(await usdc.balanceOf(player2.address)).to.equal(p2);
      expect(await escrow.getMatchStatus(id)).to.equal(CANCELLED);
      await expectSolvent();
      await expect(escrow.refundExpired(id)).to.be.revertedWithCustomError(escrow, "InvalidStatus");
    });

    it("LOCKED past lockTimeout: anyone refunds both; resolver can no longer resolve", async function () {
      const id = ethers.id("lock_expiry");
      await locked(id);
      const lockedAt = (await escrow.getMatch(id)).lockedAt;
      await time.increaseTo(lockedAt + LOCK_TIMEOUT - 2n);
      await expect(escrow.connect(stranger).refundExpired(id)).to.be.revertedWithCustomError(escrow, "NotExpired");

      await time.increaseTo(lockedAt + LOCK_TIMEOUT);
      await expect(
        escrow.connect(resolver).resolveMatch(id, player1.address)
      ).to.be.revertedWithCustomError(escrow, "ResolveWindowElapsed");

      const p1 = await usdc.balanceOf(player1.address);
      const p2 = await usdc.balanceOf(player2.address);
      await escrow.connect(stranger).refundExpired(id);
      expect(await usdc.balanceOf(player1.address)).to.equal(p1 + STAKE);
      expect(await usdc.balanceOf(player2.address)).to.equal(p2 + STAKE);
      expect(await escrow.contractBalance()).to.equal(0);
    });

    it("DISPUTED is refundable after lockTimeout too", async function () {
      const id = ethers.id("dispute_expiry");
      await locked(id);
      await escrow.connect(resolver).flagDispute(id);
      await time.increase(LOCK_TIMEOUT);
      await escrow.connect(player1).refundExpired(id);
      expect(await escrow.getMatchStatus(id)).to.equal(CANCELLED);
    });

    it("refundExpired rejects missing and settled matches", async function () {
      await expect(escrow.refundExpired(ethers.id("nope"))).to.be.revertedWithCustomError(escrow, "MatchNotFound");
      const id = ethers.id("settled");
      await locked(id);
      await escrow.connect(resolver).resolveMatch(id, player1.address);
      await time.increase(LOCK_TIMEOUT);
      await expect(escrow.refundExpired(id)).to.be.revertedWithCustomError(escrow, "InvalidStatus");
      expect(await escrow.refundableAt(id)).to.equal(0);
    });
  });

  // ─── Pull payments ───────────────────────────────────────────────────────

  describe("pull payments with a blacklisting token", function () {
    beforeEach(() => setup("MockBlacklistUSDC"));

    it("a blacklisted winner cannot block resolve; payout becomes withdrawable", async function () {
      const id = ethers.id("bl_winner");
      await locked(id);
      await usdc.setBlacklisted(player1.address, true);
      const payout = STAKE * 2n - 700_000n;
      await expect(escrow.connect(resolver).resolveMatch(id, player1.address))
        .to.emit(escrow, "PayoutDeferred")
        .withArgs(player1.address, payout);
      expect(await escrow.owed(player1.address)).to.equal(payout);
      await expectSolvent();

      await usdc.setBlacklisted(player1.address, false);
      await expect(escrow.connect(player1).withdraw())
        .to.emit(escrow, "Withdrawn")
        .withArgs(player1.address, payout);
      expect(await escrow.owed(player1.address)).to.equal(0);
      await expect(escrow.connect(player1).withdraw()).to.be.revertedWithCustomError(escrow, "NothingToWithdraw");
      await expectSolvent();
    });

    it("a blacklisted treasury cannot block resolve; owner rotates it to collect", async function () {
      const id = ethers.id("bl_treasury");
      await locked(id);
      await usdc.setBlacklisted(feeRecipient.address, true);
      await escrow.connect(resolver).resolveMatch(id, player2.address);
      await expect(escrow.withdrawFees()).to.be.reverted;
      await escrow.connect(owner).setFeeRecipient(multisig.address);
      await expect(escrow.connect(stranger).withdrawFees())
        .to.emit(escrow, "FeesWithdrawn")
        .withArgs(multisig.address, 700_000n);
      expect(await usdc.balanceOf(multisig.address)).to.equal(700_000n);
      await expect(escrow.withdrawFees()).to.be.revertedWithCustomError(escrow, "NothingToWithdraw");
    });

    it("one blacklisted player cannot block the other's refund", async function () {
      const id = ethers.id("bl_cancel");
      await locked(id);
      await usdc.setBlacklisted(player2.address, true);
      const p1 = await usdc.balanceOf(player1.address);
      await escrow.connect(resolver).cancelMatch(id);
      expect(await usdc.balanceOf(player1.address)).to.equal(p1 + STAKE);
      expect(await escrow.owed(player2.address)).to.equal(STAKE);
      await expectSolvent();
    });
  });

  // ─── Roles ───────────────────────────────────────────────────────────────

  describe("stake cap (launch posture)", function () {
    it("defaults to MAX_STAKE and only the owner can lower or raise it within bounds", async function () {
      expect(await escrow.maxStakePerPlayer()).to.equal(await escrow.MAX_STAKE());
      await expect(escrow.connect(resolver).setMaxStake(25_000_000n)).to.be.revertedWithCustomError(
        escrow,
        "OwnableUnauthorizedAccount"
      );
      await expect(escrow.connect(owner).setMaxStake(1_999_999n))
        .to.be.revertedWithCustomError(escrow, "InvalidStakeCap")
        .withArgs(1_999_999n);
      await expect(escrow.connect(owner).setMaxStake(10_000_000_001n)).to.be.revertedWithCustomError(
        escrow,
        "InvalidStakeCap"
      );
      await expect(escrow.connect(owner).setMaxStake(25_000_000n))
        .to.emit(escrow, "MaxStakeUpdated")
        .withArgs(10_000_000_000n, 25_000_000n);
    });

    it("refuses a create above the cap even with a valid permit; joins of older matches still work", async function () {
      const old = ethers.id("cap_old");
      await create(old, 100_000_000n);
      await escrow.connect(owner).setMaxStake(25_000_000n);
      await expect(create(ethers.id("cap_over"), 25_000_001n))
        .to.be.revertedWithCustomError(escrow, "StakeExceedsMax")
        .withArgs(25_000_001n);
      await create(ethers.id("cap_at"), 25_000_000n);
      await escrow.connect(player2).joinMatch(old);
      expect(await escrow.getMatchStatus(old)).to.equal(LOCKED);
      await expectSolvent();
    });
  });

  describe("roles", function () {
    it("ownership moves in two steps and cannot be renounced", async function () {
      await expect(escrow.connect(owner).transferOwnership(multisig.address))
        .to.emit(escrow, "OwnershipTransferStarted")
        .withArgs(owner.address, multisig.address);
      expect(await escrow.owner()).to.equal(owner.address);
      expect(await escrow.pendingOwner()).to.equal(multisig.address);
      await expect(escrow.connect(stranger).acceptOwnership()).to.be.revertedWithCustomError(
        escrow,
        "OwnableUnauthorizedAccount"
      );
      await expect(escrow.connect(multisig).acceptOwnership())
        .to.emit(escrow, "OwnershipTransferred")
        .withArgs(owner.address, multisig.address);
      expect(await escrow.owner()).to.equal(multisig.address);
      await expect(escrow.connect(owner).pause()).to.be.revertedWithCustomError(escrow, "OwnableUnauthorizedAccount");
      await expect(escrow.connect(multisig).renounceOwnership()).to.be.revertedWithCustomError(
        escrow,
        "RenounceDisabled"
      );
      await expect(escrow.connect(stranger).renounceOwnership()).to.be.revertedWithCustomError(
        escrow,
        "OwnableUnauthorizedAccount"
      );
    });

    it("owner cannot act as resolver; resolver cannot act as owner", async function () {
      const id = ethers.id("roles");
      await locked(id);
      await expect(escrow.connect(owner).flagDispute(id)).to.be.revertedWithCustomError(escrow, "NotResolver");
      await expect(escrow.connect(owner).cancelMatch(id)).to.be.revertedWithCustomError(escrow, "NotResolver");
      await expect(escrow.connect(resolver).pause()).to.be.revertedWithCustomError(
        escrow,
        "OwnableUnauthorizedAccount"
      );
      await expect(
        escrow.connect(resolver).setFeeTiers(500_000n, 700, 1000, 5_000_000n, 500_000_000n)
      ).to.be.revertedWithCustomError(escrow, "OwnableUnauthorizedAccount");
      await expect(escrow.connect(resolver).setResolver(stranger.address)).to.be.revertedWithCustomError(
        escrow,
        "OwnableUnauthorizedAccount"
      );
    });

    it("rejects zero addresses for roles", async function () {
      await expect(escrow.connect(owner).setResolver(ethers.ZeroAddress)).to.be.revertedWithCustomError(
        escrow,
        "ZeroAddress"
      );
      await expect(escrow.connect(owner).setFeeRecipient(ethers.ZeroAddress)).to.be.revertedWithCustomError(
        escrow,
        "ZeroAddress"
      );
    });

    it("pause blocks money in only; settle, cancel, refund and withdraw still work", async function () {
      const a = ethers.id("p_a"), b = ethers.id("p_b"), c = ethers.id("p_c"), d = ethers.id("p_d");
      await locked(a);
      await locked(b);
      await locked(c);
      await create(d);
      await escrow.connect(owner).pause();

      await expect(create(ethers.id("p_new"))).to.be.revertedWithCustomError(escrow, "EnforcedPause");
      await expect(escrow.connect(player2).joinMatch(d)).to.be.revertedWithCustomError(escrow, "EnforcedPause");

      await escrow.connect(resolver).resolveMatch(a, player1.address);
      await escrow.connect(resolver).cancelMatch(b);
      await escrow.withdrawFees();
      await time.increase(LOCK_TIMEOUT);
      await escrow.connect(stranger).refundExpired(c);
      await escrow.connect(stranger).refundExpired(d);
      expect(await escrow.contractBalance()).to.equal(0);
    });
  });

  // ─── Invariant run ───────────────────────────────────────────────────────

  it("property: random lifecycles keep balance == locked + fees + owed and never lose funds", async function () {
    const rand = prng(20261014);
    const players = [player1, player2, stranger];
    const ids = [];
    let totalIn = 0n;
    const startBal = {};
    for (const p of players) startBal[p.address] = await usdc.balanceOf(p.address);

    for (let step = 0; step < 60; step++) {
      const roll = rand();
      const live = [];
      for (const id of ids) {
        const st = Number(await escrow.getMatchStatus(id));
        if (st <= DISPUTED) live.push({ id, st });
      }
      if (roll < 0.35 || live.length === 0) {
        const i = Math.floor(rand() * 3);
        const p1 = players[i];
        const p2 = players[(i + 1 + Math.floor(rand() * 2)) % 3];
        const stake = randBig(rand, 2_000_000n, 2_000_000_000n);
        const id = ethers.id(`inv_${step}`);
        await createMatch(escrow, resolver, id, stake, p1, p2);
        ids.push(id);
        totalIn += stake;
      } else {
        const { id, st } = live[Math.floor(rand() * live.length)];
        const m = await escrow.getMatch(id);
        const r = rand();
        if (BigInt(await time.latest()) + 1n >= (await escrow.refundableAt(id))) {
          await escrow.connect(stranger).refundExpired(id); // timed out by an earlier jump
        } else if (st === OPEN) {
          if (r < 0.6) {
            await escrow.connect(players.find((p) => p.address === m.player2)).joinMatch(id);
            totalIn += m.stakePerPlayer;
          } else {
            await escrow.connect(resolver).cancelMatch(id);
          }
        } else if (r < 0.15 && st === LOCKED) {
          await escrow.connect(resolver).flagDispute(id);
        } else if (r < 0.75) {
          await escrow.connect(resolver).resolveMatch(id, rand() < 0.5 ? m.player1 : m.player2);
        } else if (r < 0.9) {
          await escrow.connect(resolver).cancelMatch(id);
        } else {
          await time.increase(LOCK_TIMEOUT);
          await escrow.connect(stranger).refundExpired(id);
        }
      }
      await expectSolvent();
    }
    // Settle everything, drain fees: players + treasury got back exactly what went in.
    await time.increase(LOCK_TIMEOUT);
    for (const id of ids) {
      if (Number(await escrow.getMatchStatus(id)) <= DISPUTED) await escrow.refundExpired(id);
    }
    if ((await escrow.accruedFees()) > 0n) await escrow.withdrawFees();
    expect(await escrow.contractBalance()).to.equal(0);
    expect(await escrow.totalLocked()).to.equal(0);
    let playersNet = 0n;
    for (const p of players) playersNet += (await usdc.balanceOf(p.address)) - startBal[p.address];
    expect(playersNet + (await usdc.balanceOf(feeRecipient.address))).to.equal(0n);
    expect(totalIn).to.be.gt(0n);
  });
});
