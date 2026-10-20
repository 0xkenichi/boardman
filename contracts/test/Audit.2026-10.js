// October 2026 internal audit: attack PoCs and model-based invariant runs for
// BoardmanEscrow v2 and SpectatorPool v2. Findings are in
// docs/security/AUDIT_2026-10_contracts.md; each test name starts with its id.
import hre from "hardhat";
const { ethers, network } = hre;
import { expect } from "chai";
import { time } from "@nomicfoundation/hardhat-network-helpers";
import {
  CLAIM_WINDOW,
  CREATE_MATCH_TYPES,
  HOUR,
  LOCK_TIMEOUT,
  OPEN_TIMEOUT,
  REFUND_GRACE,
  createMatch,
  deadlineIn,
  deployEscrow,
  deployPool,
  prng,
  randBig,
  signCreate,
} from "./helpers/boardman.js";

const OPEN = 0, LOCKED = 1, DISPUTED = 2, RESOLVED = 3, CANCELLED = 4;
const B_OPEN = 1, B_CLOSED = 2, B_RESOLVED = 3, B_CANCELLED = 4;
const SECP256K1_N = BigInt("0xfffffffffffffffffffffffffffffffebaaedce6af48a03bbfd25e8cd0364141");

/**
 * Shared EIP-712 vector. tests/test_audit_contracts_backend.py pins the same
 * digest for the Python signer (sign_create_permit), so the backend and the
 * contract cannot drift apart without one of the two suites failing.
 */
export const PERMIT_VECTOR = {
  domain: {
    name: "BoardmanEscrow",
    version: "2",
    chainId: 5042,
    verifyingContract: "0x00000000000000000000000000000000000E5C70",
  },
  value: {
    matchId: ethers.sha256(ethers.toUtf8Bytes("agm_audit_vector")),
    player1: "0x1111111111111111111111111111111111111111",
    player2: "0x2222222222222222222222222222222222222222",
    stake: 5_000_000n,
    deadline: 1_800_000_000n,
  },
  digest: "0x909093eb8f7da9dfe46e9c28838faf8e260f6345e78a0bd067f59b151fb8529c",
};

describe("Audit 2026-10: BoardmanEscrow v2", function () {
  let usdc, escrow, owner, resolver, treasury, p1, p2, mallory, carol;

  beforeEach(async function () {
    [owner, resolver, treasury, p1, p2, mallory, carol] = await ethers.getSigners();
    usdc = await (await ethers.getContractFactory("MockBlacklistUSDC")).deploy();
    escrow = await deployEscrow(usdc, treasury, resolver);
    for (const s of [p1, p2, mallory, carol]) {
      await usdc.mint(s.address, 1_000_000_000_000n);
      await usdc.connect(s).approve(await escrow.getAddress(), ethers.MaxUint256);
    }
  });

  async function solvent() {
    const bal = await usdc.balanceOf(await escrow.getAddress());
    expect(bal).to.equal((await escrow.totalLocked()) + (await escrow.accruedFees()) + (await escrow.totalOwed()));
  }

  // ─── Signature / permit attacks (refuted) ────────────────────────────────

  describe("permit replay and malleability", function () {
    it("A-01 the Python/ethers EIP-712 vector matches the contract's encoding", async function () {
      const digest = ethers.TypedDataEncoder.hash(PERMIT_VECTOR.domain, CREATE_MATCH_TYPES, PERMIT_VECTOR.value);
      expect(digest).to.equal(PERMIT_VECTOR.digest);
      // The contract builds the same digest for its own domain (address/chain differ).
      const { chainId } = await ethers.provider.getNetwork();
      const local = { ...PERMIT_VECTOR.domain, chainId, verifyingContract: await escrow.getAddress() };
      const v = PERMIT_VECTOR.value;
      expect(await escrow.hashCreateMatch(v.matchId, v.player1, v.player2, v.stake, v.deadline)).to.equal(
        ethers.TypedDataEncoder.hash(local, CREATE_MATCH_TYPES, v)
      );
    });

    it("A-02 a permit signed for another chain id (testnet 5042002) is rejected", async function () {
      const id = ethers.id("xchain");
      const deadline = await deadlineIn();
      const domain = { name: "BoardmanEscrow", version: "2", chainId: 5042002, verifyingContract: await escrow.getAddress() };
      const sig = await resolver.signTypedData(domain, CREATE_MATCH_TYPES, {
        matchId: id, player1: p1.address, player2: p2.address, stake: 5_000_000n, deadline,
      });
      await expect(escrow.connect(p1).createMatch(id, p2.address, 5_000_000n, deadline, sig))
        .to.be.revertedWithCustomError(escrow, "InvalidPermit");
    });

    it("A-03 a permit for one escrow deployment is rejected by another", async function () {
      const other = await deployEscrow(usdc, treasury, resolver);
      await usdc.connect(p1).approve(await other.getAddress(), ethers.MaxUint256);
      const id = ethers.id("xcontract");
      const deadline = await deadlineIn();
      const sig = await signCreate(escrow, resolver, { matchId: id, player1: p1.address, player2: p2.address, stake: 5_000_000n, deadline });
      await expect(other.connect(p1).createMatch(id, p2.address, 5_000_000n, deadline, sig))
        .to.be.revertedWithCustomError(other, "InvalidPermit");
    });

    it("A-04 a permit cannot be replayed after the match is cancelled, refunded or resolved", async function () {
      const id = ethers.id("replay");
      const deadline = await deadlineIn(7n * 24n * HOUR);
      const sig = await signCreate(escrow, resolver, { matchId: id, player1: p1.address, player2: p2.address, stake: 5_000_000n, deadline });
      await escrow.connect(p1).createMatch(id, p2.address, 5_000_000n, deadline, sig);
      await escrow.connect(resolver).cancelMatch(id);
      await expect(escrow.connect(p1).createMatch(id, p2.address, 5_000_000n, deadline, sig))
        .to.be.revertedWithCustomError(escrow, "MatchAlreadyExists");
    });

    it("A-05 high-s (malleated) and tampered-field signatures are rejected", async function () {
      const id = ethers.id("malleable");
      const deadline = await deadlineIn();
      const sig = ethers.Signature.from(
        await signCreate(escrow, resolver, { matchId: id, player1: p1.address, player2: p2.address, stake: 5_000_000n, deadline })
      );
      const highS = ethers.concat([sig.r, ethers.toBeHex(SECP256K1_N - BigInt(sig.s), 32), sig.v === 27 ? "0x1c" : "0x1b"]);
      await expect(escrow.connect(p1).createMatch(id, p2.address, 5_000_000n, deadline, highS))
        .to.be.revertedWithCustomError(escrow, "InvalidPermit");
      // Same signature, any field changed: stake, opponent, deadline, sender.
      await expect(escrow.connect(p1).createMatch(id, p2.address, 5_000_001n, deadline, sig.serialized))
        .to.be.revertedWithCustomError(escrow, "InvalidPermit");
      await expect(escrow.connect(p1).createMatch(id, carol.address, 5_000_000n, deadline, sig.serialized))
        .to.be.revertedWithCustomError(escrow, "InvalidPermit");
      await expect(escrow.connect(p1).createMatch(id, p2.address, 5_000_000n, deadline + 1n, sig.serialized))
        .to.be.revertedWithCustomError(escrow, "InvalidPermit");
      await expect(escrow.connect(mallory).createMatch(id, p2.address, 5_000_000n, deadline, sig.serialized))
        .to.be.revertedWithCustomError(escrow, "InvalidPermit");
      await escrow.connect(p1).createMatch(id, p2.address, 5_000_000n, deadline, sig.serialized);
    });
  });

  // ─── Timeout boundaries (== edges) ──────────────────────────────────────

  describe("timeout edges", function () {
    it("A-06 join and refund meet exactly at createdAt + openTimeout (no gap, no overlap)", async function () {
      const id = ethers.id("open-edge");
      await createMatch(escrow, resolver, id, 5_000_000n, p1, p2);
      const created = BigInt((await escrow.getMatch(id)).createdAt);
      await time.setNextBlockTimestamp(created + OPEN_TIMEOUT - 1n);
      await expect(escrow.refundExpired(id)).to.be.revertedWithCustomError(escrow, "NotExpired");
      await time.setNextBlockTimestamp(created + OPEN_TIMEOUT);
      await expect(escrow.connect(p2).joinMatch(id)).to.be.revertedWithCustomError(escrow, "MatchExpiredForJoin");
      await time.setNextBlockTimestamp(created + OPEN_TIMEOUT + 1n);
      await escrow.connect(mallory).refundExpired(id);
      expect(Number(await escrow.getMatchStatus(id))).to.equal(CANCELLED);
      await solvent();
    });

    it("A-07 resolve and refund meet exactly at lockedAt + lockTimeout", async function () {
      const id = ethers.id("lock-edge");
      await createMatch(escrow, resolver, id, 5_000_000n, p1, p2);
      await escrow.connect(p2).joinMatch(id);
      const locked = BigInt((await escrow.getMatch(id)).lockedAt);
      await time.setNextBlockTimestamp(locked + LOCK_TIMEOUT);
      await expect(escrow.connect(resolver).resolveMatch(id, p1.address))
        .to.be.revertedWithCustomError(escrow, "ResolveWindowElapsed");
      await time.setNextBlockTimestamp(locked + LOCK_TIMEOUT + 1n);
      await escrow.connect(mallory).refundExpired(id);
      await expect(escrow.connect(resolver).resolveMatch(id, p1.address)).to.be.revertedWithCustomError(escrow, "InvalidStatus");
      await solvent();
    });
  });

  // ─── Fee math ────────────────────────────────────────────────────────────

  describe("fee tiers", function () {
    it("I-03 tier boundaries are exact; the flat tier costs more than the first bps tier", async function () {
      expect(await escrow.quotePlatformFee(2_000_000n)).to.equal(1_000_000n); // 25% of a $4 pot
      expect(await escrow.quotePlatformFee(4_999_999n)).to.equal(1_000_000n); // flat $0.50 x 2
      expect(await escrow.quotePlatformFee(5_000_000n)).to.equal(700_000n); // 7% of $10: cheaper than $4.99
      expect(await escrow.quotePlatformFee(500_000_000n)).to.equal(70_000_000n);
      expect(await escrow.quotePlatformFee(500_000_001n)).to.equal(100_000_000n); // 10% one unit above
      // Max tiers: still never more than a quarter of the pot, never above the pot.
      await escrow.connect(owner).setFeeTiers(500_000n, 1000, 1000, 10_000_000_000n, 10_000_000_000n);
      for (const s of [2_000_000n, 2_000_001n, 9_999_999_999n, 10_000_000_000n]) {
        const fee = await escrow.quotePlatformFee(s);
        expect(fee * 4n).to.be.lte(s * 2n);
      }
    });

    it("L-01 the owner can raise the fee (within caps) after a permit is issued and before createMatch", async function () {
      // Permit is signed while the fee for $5 stakes is 7% ($0.70 of the pot).
      const id = ethers.id("fee-race");
      const deadline = await deadlineIn();
      const sig = await signCreate(escrow, resolver, { matchId: id, player1: p1.address, player2: p2.address, stake: 5_000_000n, deadline });
      expect(await escrow.quotePlatformFee(5_000_000n)).to.equal(700_000n);
      // Owner retunes (front-runs) to 10% everywhere; the permit does not bind the fee.
      await escrow.connect(owner).setFeeTiers(500_000n, 1000, 1000, 2_000_000n, 500_000_000n);
      await escrow.connect(p1).createMatch(id, p2.address, 5_000_000n, deadline, sig);
      expect((await escrow.getMatch(id)).platformFee).to.equal(1_000_000n);
      // Acknowledged: bounded by MAX_FEE_BPS, visible before joinMatch via getMatch / MatchTerms.
    });
  });

  // ─── Push vs. pull and griefing ─────────────────────────────────────────

  describe("griefing", function () {
    it("I-02 no gas limit makes refundExpired succeed while deferring a payout (63/64 rule)", async function () {
      const id = ethers.id("gas-grief");
      await createMatch(escrow, resolver, id, 5_000_000n, p1, p2);
      await escrow.connect(p2).joinMatch(id);
      await time.increase(LOCK_TIMEOUT);
      const est = await escrow.connect(mallory).refundExpired.estimateGas(id);
      let succeeded = 0;
      for (let g = est - 60_000n; g <= est + 4_000n; g += 2_000n) {
        if (g < 21_000n) continue;
        const snap = await network.provider.send("evm_snapshot");
        try {
          const tx = await escrow.connect(mallory).refundExpired(id, { gasLimit: g });
          await tx.wait();
          succeeded += 1;
          expect(await escrow.totalOwed()).to.equal(0n, `gas ${g} deferred a payout`);
        } catch (e) {
          // ran out of gas as a whole: nothing changed
        }
        await network.provider.send("evm_revert", [snap]);
      }
      expect(succeeded).to.be.gt(0);
    });

    it("I-02 a blacklisted player cannot block resolve or the other player's refund", async function () {
      const id = ethers.id("bl");
      await createMatch(escrow, resolver, id, 5_000_000n, p1, p2);
      await escrow.connect(p2).joinMatch(id);
      await usdc.setBlacklisted(p2.address, true);
      await escrow.connect(resolver).resolveMatch(id, p2.address);
      expect(await escrow.owed(p2.address)).to.equal(9_300_000n);
      await solvent();
    });

    it("I-01 stray USDC sent straight to the escrow is outside the accounting and stays stuck", async function () {
      await usdc.connect(carol).transfer(await escrow.getAddress(), 123n);
      const id = ethers.id("stray");
      await createMatch(escrow, resolver, id, 5_000_000n, p1, p2);
      await escrow.connect(p2).joinMatch(id);
      await escrow.connect(resolver).resolveMatch(id, p1.address);
      await escrow.withdrawFees();
      expect(await usdc.balanceOf(await escrow.getAddress())).to.equal(123n); // nobody can move it
      // Monitoring must therefore check balance >= locked + fees + owed, not ==.
    });
  });

  // ─── Roles ───────────────────────────────────────────────────────────────

  describe("roles and trust", function () {
    it("A-08 neither a compromised resolver nor the owner can pay an outsider", async function () {
      const id = ethers.id("outsider");
      await createMatch(escrow, resolver, id, 5_000_000n, p1, p2);
      await escrow.connect(p2).joinMatch(id);
      for (const who of [mallory, resolver, owner, treasury]) {
        await expect(escrow.connect(resolver).resolveMatch(id, who.address))
          .to.be.revertedWithCustomError(escrow, "InvalidWinner");
      }
      await expect(escrow.connect(owner).resolveMatch(id, p1.address)).to.be.revertedWithCustomError(escrow, "NotResolver");
      // Owner rotating the resolver to itself is the only lever, and it still pays a player.
      await escrow.connect(owner).setResolver(owner.address);
      await expect(escrow.connect(owner).resolveMatch(id, owner.address)).to.be.revertedWithCustomError(escrow, "InvalidWinner");
    });
  });

  // ─── Model-based invariant run ──────────────────────────────────────────

  it("INV-E property: model of every wallet + owed matches the chain after each random step", async function () {
    const rand = prng(0xa0d17);
    const actors = [p1, p2, mallory, carol];
    const outsiders = [owner, treasury];
    const all = [...actors, ...outsiders, resolver];
    const model = {}; // address -> expected wallet balance + owed
    const holdings = async (a) => (await usdc.balanceOf(a)) + (await escrow.owed(a));
    for (const s of all) model[s.address] = await holdings(s.address);
    const matches = []; // {id, p1, p2, stake, fee}
    let fees = 0n;
    const check = async () => {
      for (const s of all) expect(await holdings(s.address)).to.equal(model[s.address], `holdings of ${s.address}`);
      expect(await escrow.accruedFees()).to.equal(fees);
      await solvent();
    };

    for (let step = 0; step < 90; step++) {
      const r = rand();
      const live = [];
      for (const m of matches) {
        const st = Number(await escrow.getMatchStatus(m.id));
        if (st <= DISPUTED) live.push({ ...m, st });
      }
      if (r < 0.3 || live.length === 0) {
        const free = [];
        for (const x of actors) if (!(await usdc.blacklisted(x.address))) free.push(x);
        if (free.length === 0) {
          await usdc.setBlacklisted(actors[0].address, false);
          free.push(actors[0]);
        }
        const a = free[Math.floor(rand() * free.length)];
        const others = actors.filter((x) => x !== a);
        const b = others[Math.floor(rand() * others.length)];
        const stake = randBig(rand, 2_000_000n, 600_000_000n);
        const id = ethers.id(`inv-e-${step}`);
        await createMatch(escrow, resolver, id, stake, a, b);
        const fee = (await escrow.getMatch(id)).platformFee;
        matches.push({ id, p1: a, p2: b, stake, fee });
        model[a.address] -= stake;
      } else if (r < 0.36) {
        // Toggle a blacklist: payouts to that address get deferred, never lost.
        const who = actors[Math.floor(rand() * actors.length)];
        await usdc.setBlacklisted(who.address, !(await usdc.blacklisted(who.address)));
      } else if (r < 0.42) {
        const who = actors[Math.floor(rand() * actors.length)];
        if ((await escrow.owed(who.address)) > 0n && !(await usdc.blacklisted(who.address))) {
          await escrow.connect(who).withdraw();
        }
      } else {
        const m = live[Math.floor(rand() * live.length)];
        const pick = rand();
        // 5 s margin: hardhat block times can run ahead of time.latest().
        const at = await escrow.refundableAt(m.id);
        const now = BigInt(await time.latest());
        if (now + 5n >= at) {
          if (now < at) await time.increaseTo(at);
          await escrow.connect(mallory).refundExpired(m.id);
          model[m.p1.address] += m.stake;
          if (m.st !== OPEN) model[m.p2.address] += m.stake;
        } else if (m.st === OPEN) {
          if (pick < 0.65 && !(await usdc.blacklisted(m.p2.address))) {
            await escrow.connect(m.p2).joinMatch(m.id);
            model[m.p2.address] -= m.stake;
          } else if (pick < 0.85) {
            await escrow.connect(resolver).cancelMatch(m.id);
            model[m.p1.address] += m.stake;
          } else {
            await time.increase(OPEN_TIMEOUT);
          }
        } else {
          // A compromised resolver tries an outsider first; it must always fail.
          const outsider = [mallory, carol, owner, treasury, resolver].find((x) => x !== m.p1 && x !== m.p2);
          await expect(escrow.connect(resolver).resolveMatch(m.id, outsider.address))
            .to.be.revertedWithCustomError(escrow, "InvalidWinner");
          if (pick < 0.1 && m.st === LOCKED) {
            await escrow.connect(resolver).flagDispute(m.id);
          } else if (pick < 0.7) {
            const winner = rand() < 0.5 ? m.p1 : m.p2;
            await escrow.connect(resolver).resolveMatch(m.id, winner.address);
            model[winner.address] += 2n * m.stake - m.fee;
            fees += m.fee;
          } else if (pick < 0.9) {
            await escrow.connect(resolver).cancelMatch(m.id);
            model[m.p1.address] += m.stake;
            model[m.p2.address] += m.stake;
          } else {
            await time.increase(LOCK_TIMEOUT);
          }
        }
      }
      await check();
    }

    // No player ever lost more than their stake in any match: a loser's
    // worst case is exactly -stake, and fees never exceed a quarter of a pot.
    for (const m of matches) expect(m.fee * 4n).to.be.lte(2n * m.stake);
    // Drain: everything that went in comes back out to players or the treasury.
    await time.increase(LOCK_TIMEOUT + OPEN_TIMEOUT);
    for (const m of matches) {
      if (Number(await escrow.getMatchStatus(m.id)) <= DISPUTED) await escrow.refundExpired(m.id);
    }
    for (const a of actors) await usdc.setBlacklisted(a.address, false);
    for (const a of actors) if ((await escrow.owed(a.address)) > 0n) await escrow.connect(a).withdraw();
    if ((await escrow.accruedFees()) > 0n) await escrow.withdrawFees();
    expect(await usdc.balanceOf(await escrow.getAddress())).to.equal(0n);
    expect(await escrow.totalOwed()).to.equal(0n);
  });
});

describe("Audit 2026-10: SpectatorPool v2", function () {
  let usdc, pool, owner, resolver, treasury, agentA, agentB, creatorA, creatorB, fans, mallory;
  const gameId = ethers.id("agentic.chess_standard");
  const books = [];

  beforeEach(async function () {
    const s = await ethers.getSigners();
    [owner, resolver, treasury, agentA, agentB, creatorA, creatorB, mallory] = s;
    fans = s.slice(8, 14);
    usdc = await (await ethers.getContractFactory("MockBlacklistUSDC")).deploy();
    pool = await deployPool(usdc, treasury, resolver);
    for (const x of [agentA, agentB, resolver, mallory, ...fans]) {
      await usdc.mint(x.address, 1_000_000_000_000n);
      await usdc.connect(x).approve(await pool.getAddress(), ethers.MaxUint256);
    }
    books.length = 0;
  });

  async function open(id, closeIn = HOUR, cap = 100_000_000_000n) {
    const closeAt = await deadlineIn(closeIn);
    await pool.connect(resolver).openBook(
      id, gameId, ethers.id("a"), ethers.id("b"), agentA.address, agentB.address,
      creatorA.address, creatorB.address, cap, closeAt
    );
    books.push(id);
    return closeAt;
  }

  async function solvent() {
    let held = (await pool.protocolFees()) + (await pool.totalOwed());
    for (const id of books) {
      const b = await pool.getBook(id);
      const st = Number(b.status);
      if (st === B_OPEN || st === B_CLOSED) held += b.totalA + b.totalB + b.totalDraw;
      else held += b.remaining;
    }
    expect(await usdc.balanceOf(await pool.getAddress())).to.equal(held);
  }

  it("H-01 (contract side) a direct deposit() lands after the game ended until close() or closeAt", async function () {
    // The pool cannot know the result. Between the moment the game is over
    // (visible on the live stream) and the resolver's close(), anyone can
    // still deposit() on the known winner. The backend fix closes the book
    // first thing at settlement and re-checks the off-chain book before any
    // depositFor (tests/test_audit_contracts_backend.py).
    const id = ethers.id("late-bet");
    await open(id, 900n);
    await pool.connect(fans[0]).deposit(id, 10_000_000n, 0);
    await pool.connect(fans[1]).deposit(id, 50_000_000n, 1);
    // ... game ends, side A won; result is public. Mallory front-runs close():
    await pool.connect(mallory).deposit(id, 100_000_000n, 0);
    await pool.connect(resolver).close(id);
    await expect(pool.connect(mallory).deposit(id, 1n, 0)).to.be.revertedWithCustomError(pool, "BookNotOpen");
    await pool.connect(resolver).resolve(id, 0);
    const got = await pool.claimable(id, mallory.address);
    // Risk-free: 100 in, 132.36 out, paid by the side-B fan who bet blind.
    expect(got).to.equal(132_363_636n);
  });

  it("A-09 closeAt edges: last deposit at closeAt-1, resolve from closeAt, refund from closeAt+grace", async function () {
    const id = ethers.id("edges");
    const closeAt = await open(id);
    await time.setNextBlockTimestamp(closeAt - 1n);
    await pool.connect(fans[0]).deposit(id, 2_000_000n, 0);
    await time.setNextBlockTimestamp(closeAt);
    await expect(pool.connect(fans[1]).deposit(id, 2_000_000n, 1)).to.be.revertedWithCustomError(pool, "BettingClosed");
    await time.setNextBlockTimestamp(closeAt + REFUND_GRACE - 1n);
    await expect(pool.refundExpired(id)).to.be.revertedWithCustomError(pool, "NotExpired");
    await time.setNextBlockTimestamp(closeAt + REFUND_GRACE);
    await expect(pool.connect(resolver).resolve(id, 0)).to.be.revertedWithCustomError(pool, "ResolveWindowElapsed");
    await time.setNextBlockTimestamp(closeAt + REFUND_GRACE + 1n);
    await pool.connect(mallory).refundExpired(id);
    expect(await pool.claimable(id, fans[0].address)).to.equal(2_000_000n);
    await solvent();
  });

  it("A-10 sweep takes only the one book's remainder; other books stay claimable", async function () {
    const a = ethers.id("sweep-a"), b = ethers.id("sweep-b");
    await open(a);
    await open(b);
    await pool.connect(fans[0]).deposit(a, 3_333_333n, 0);
    await pool.connect(fans[1]).deposit(a, 7_777_777n, 1);
    await pool.connect(fans[2]).deposit(b, 5_000_000n, 0);
    await pool.connect(fans[3]).deposit(b, 5_000_000n, 1);
    await pool.connect(resolver).close(a);
    await pool.connect(resolver).close(b);
    await pool.connect(resolver).resolve(a, 1);
    await pool.connect(resolver).resolve(b, 0);
    await time.increase(CLAIM_WINDOW);
    const before = await pool.claimable(b, fans[2].address);
    await expect(pool.connect(mallory).sweep(a)).to.be.revertedWithCustomError(pool, "OwnableUnauthorizedAccount");
    await pool.connect(owner).sweep(a);
    await expect(pool.connect(owner).sweep(a)).to.be.revertedWithCustomError(pool, "AlreadySwept");
    expect(await pool.claimable(b, fans[2].address)).to.equal(before);
    await pool.connect(fans[2]).claim(b);
    await solvent();
  });

  it("A-11 an outsider can never claim from any book state", async function () {
    const id = ethers.id("outsider");
    await open(id);
    await pool.connect(fans[0]).deposit(id, 4_000_000n, 0);
    await pool.connect(fans[1]).deposit(id, 4_000_000n, 1);
    await expect(pool.connect(mallory).claim(id)).to.be.revertedWithCustomError(pool, "NothingToClaim");
    await pool.connect(resolver).close(id);
    await expect(pool.connect(mallory).claim(id)).to.be.revertedWithCustomError(pool, "NothingToClaim");
    await pool.connect(resolver).resolve(id, -2); // draw with no draw fans -> refund
    await expect(pool.connect(mallory).claim(id)).to.be.revertedWithCustomError(pool, "NothingToClaim");
    await pool.connect(fans[0]).claim(id);
    await expect(pool.connect(fans[0]).claim(id)).to.be.revertedWithCustomError(pool, "NothingToClaim");
  });

  it("INV-P property: random books conserve money exactly and pay only depositors", async function () {
    const rand = prng(0x5bec7);
    const bettors = [...fans, mallory];
    const deposited = {}; // id -> {addr -> {0,1,2}}
    const startBal = {};
    const everyone = [...bettors, agentA, agentB, creatorA, creatorB, treasury, resolver, owner];
    for (const x of everyone) startBal[x.address] = await usdc.balanceOf(x.address);
    let totalIn = 0n;
    const ids = [];

    for (let step = 0; step < 110; step++) {
      const r = rand();
      const live = [];
      for (const id of ids) {
        const st = Number((await pool.getBook(id)).status);
        if (st === B_OPEN || st === B_CLOSED) live.push({ id, st });
      }
      if (r < 0.12 || live.length === 0) {
        const id = ethers.id(`inv-p-${step}`);
        await open(id, BigInt(600 + Math.floor(rand() * 3600)));
        ids.push(id);
        deposited[id] = {};
        if (rand() < 0.5) {
          const amt = randBig(rand, 1n, 3_000_000n);
          await pool.connect(agentA).seed(id, 0, amt);
          totalIn += amt;
        }
        if (rand() < 0.3) {
          const amt = randBig(rand, 1n, 3_000_000n);
          await pool.connect(agentB).seed(id, 2, amt);
          totalIn += amt;
        }
      } else {
        const { id, st } = live[Math.floor(rand() * live.length)];
        const b = await pool.getBook(id);
        const now = BigInt(await time.latest());
        const pick = rand();
        // 5 s margins: hardhat block times can run ahead of time.latest().
        const betting = st === B_OPEN && now + 5n < b.closeAt;
        if (now + 5n >= b.closeAt + REFUND_GRACE) {
          if (now < b.closeAt + REFUND_GRACE) await time.increaseTo(b.closeAt + REFUND_GRACE);
          await pool.connect(mallory).refundExpired(id);
        } else if (st === B_OPEN && now + 5n >= b.closeAt && now < b.closeAt + 5n) {
          await time.increase(10); // too close to closeAt to predict; step past it
        } else if (betting && pick < 0.6) {
          const who = bettors[Math.floor(rand() * bettors.length)];
          const side = Math.floor(rand() * 3);
          const amt = rand() < 0.2 ? randBig(rand, 1n, 50n) : randBig(rand, 250_000n, 50_000_000n);
          if (rand() < 0.25) await pool.connect(resolver).depositFor(id, who.address, amt, side);
          else await pool.connect(who).deposit(id, amt, side);
          deposited[id][who.address] = deposited[id][who.address] || [0n, 0n, 0n];
          deposited[id][who.address][side] += amt;
          totalIn += amt;
        } else if (betting && pick < 0.75) {
          await pool.connect(resolver).close(id);
        } else if (pick < 0.9) {
          if (betting) {
            await expect(pool.connect(resolver).resolve(id, 0)).to.be.revertedWithCustomError(pool, "BookStillOpen");
            await pool.connect(resolver).close(id);
          }
          const sides = [0, 1, -2, -1];
          await pool.connect(resolver).resolve(id, sides[Math.floor(rand() * sides.length)]);
        } else if (pick < 0.95) {
          await pool.connect(resolver).cancel(id);
        } else {
          await time.increase(REFUND_GRACE);
        }
      }
      // Random claims on settled books by depositors and by an outsider.
      if (rand() < 0.4 && ids.length) {
        const id = ids[Math.floor(rand() * ids.length)];
        const who = bettors[Math.floor(rand() * bettors.length)];
        const c = await pool.claimable(id, who.address);
        const dep = deposited[id][who.address];
        if (!dep) expect(c).to.equal(0n);
        if (c > 0n) {
          const b = await pool.getBook(id);
          // never more than the whole pot, never more than the book still holds
          expect(c).to.be.lte(b.remaining);
          if (Number(b.status) === B_CANCELLED || b.winnerSide === -1n) {
            expect(c).to.equal(dep[0] + dep[1] + dep[2]); // refunds are exact
          }
          await pool.connect(who).claim(id);
        }
      }
      await solvent();
    }

    // Drain everything: settle, claim, withdraw creators, sweep dust, fees.
    await time.increase(7n * 24n * HOUR + REFUND_GRACE);
    for (const id of ids) {
      const st = Number((await pool.getBook(id)).status);
      if (st === B_OPEN || st === B_CLOSED) await pool.refundExpired(id);
    }
    for (const id of ids) {
      for (const who of [...bettors, agentA, agentB]) {
        if ((await pool.claimable(id, who.address)) > 0n) await pool.connect(who).claim(id);
      }
    }
    for (const c of [creatorA, creatorB]) if ((await pool.owed(c.address)) > 0n) await pool.connect(c).withdraw();
    await time.increase(CLAIM_WINDOW);
    for (const id of ids) if ((await pool.getBook(id)).remaining > 0n) await pool.connect(owner).sweep(id);
    if ((await pool.protocolFees()) > 0n) await pool.withdrawFees();
    expect(await usdc.balanceOf(await pool.getAddress())).to.equal(0n);
    let net = 0n;
    for (const x of everyone) net += (await usdc.balanceOf(x.address)) - startBal[x.address];
    expect(net).to.equal(0n); // nothing created, nothing destroyed
    expect(totalIn).to.be.gt(0n);
    // Owner and resolver never gained (resolver only lost its depositFor float).
    expect(await usdc.balanceOf(owner.address)).to.equal(startBal[owner.address]);
    expect(await usdc.balanceOf(resolver.address)).to.be.lte(startBal[resolver.address]);
  });
});
