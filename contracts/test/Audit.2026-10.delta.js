// October 2026 audit, delta after merging integration/wave1
// (launch/arc-mainnet-humans): maxStakePerPlayer, check_v2_roles.js.
// Findings: docs/security/AUDIT_2026-10_contracts.md section 9.
import hre from "hardhat";
const { ethers } = hre;
import { expect } from "chai";
import { time } from "@nomicfoundation/hardhat-network-helpers";
import { LOCK_TIMEOUT, OPEN_TIMEOUT, createMatch, deadlineIn, deployEscrow, signCreate } from "./helpers/boardman.js";
import { checkRoles } from "../scripts/lib/v2_roles.js";

const OPEN = 0, LOCKED = 1, RESOLVED = 3, CANCELLED = 4;

describe("Audit 2026-10 delta: stake cap (maxStakePerPlayer)", function () {
  let usdc, escrow, owner, resolver, treasury, p1, p2, mallory;

  beforeEach(async function () {
    [owner, resolver, treasury, p1, p2, mallory] = await ethers.getSigners();
    usdc = await (await ethers.getContractFactory("MockUSDC")).deploy();
    escrow = await deployEscrow(usdc, treasury, resolver);
    for (const s of [p1, p2]) {
      await usdc.mint(s.address, 1_000_000_000_000n);
      await usdc.connect(s).approve(await escrow.getAddress(), ethers.MaxUint256);
    }
  });

  async function solvent() {
    expect(await usdc.balanceOf(await escrow.getAddress())).to.equal(
      (await escrow.totalLocked()) + (await escrow.accruedFees()) + (await escrow.totalOwed())
    );
  }

  it("D-A1 lowering the cap mid-match never bricks join, resolve, cancel or refund of bigger matches", async function () {
    const [a, b, c, d] = ["a", "b", "c", "d"].map((x) => ethers.id(`cap-mid-${x}`));
    for (const id of [a, b, c, d]) await createMatch(escrow, resolver, id, 1_000_000_000n, p1, p2);
    await escrow.connect(p2).joinMatch(b);
    await escrow.connect(p2).joinMatch(c);
    await escrow.connect(owner).setMaxStake(2_000_000n); // the floor: $2
    await escrow.connect(owner).pause();
    await escrow.connect(owner).unpause();
    await escrow.connect(p2).joinMatch(a); // OPEN $1000 match still joinable
    await escrow.connect(resolver).resolveMatch(b, p1.address);
    await escrow.connect(resolver).cancelMatch(c);
    await time.increase(OPEN_TIMEOUT);
    await escrow.connect(mallory).refundExpired(d);
    expect(await escrow.getMatchStatus(a)).to.equal(LOCKED);
    expect(await escrow.getMatchStatus(b)).to.equal(RESOLVED);
    expect(await escrow.getMatchStatus(c)).to.equal(CANCELLED);
    expect(await escrow.getMatchStatus(d)).to.equal(CANCELLED);
    await time.increase(LOCK_TIMEOUT);
    await escrow.connect(mallory).refundExpired(a);
    await solvent();
  });

  it("D-A2 the cap is inclusive and checked against the live value at create, not the permit", async function () {
    await escrow.connect(owner).setMaxStake(25_000_000n);
    const id = ethers.id("cap-race");
    const deadline = await deadlineIn();
    const sig = await signCreate(escrow, resolver, { matchId: id, player1: p1.address, player2: p2.address, stake: 25_000_000n, deadline });
    // Owner lowers the cap after the permit was issued: the create reverts, nothing moves.
    await escrow.connect(owner).setMaxStake(20_000_000n);
    const before = await usdc.balanceOf(p1.address);
    await expect(escrow.connect(p1).createMatch(id, p2.address, 25_000_000n, deadline, sig))
      .to.be.revertedWithCustomError(escrow, "StakeExceedsMax");
    expect(await usdc.balanceOf(p1.address)).to.equal(before);
    // Raised back: the same permit (still within its deadline) works, cap is inclusive.
    await escrow.connect(owner).setMaxStake(25_000_000n);
    await escrow.connect(p1).createMatch(id, p2.address, 25_000_000n, deadline, sig);
    expect(await escrow.getMatchStatus(id)).to.equal(OPEN);
  });

  it("D-A3 only the owner sets the cap, within [MIN_STAKE, MAX_STAKE], with an event; the resolver cannot", async function () {
    await expect(escrow.connect(resolver).setMaxStake(5_000_000n)).to.be.revertedWithCustomError(escrow, "OwnableUnauthorizedAccount");
    await expect(escrow.connect(mallory).setMaxStake(5_000_000n)).to.be.revertedWithCustomError(escrow, "OwnableUnauthorizedAccount");
    await expect(escrow.connect(owner).setMaxStake(0n)).to.be.revertedWithCustomError(escrow, "InvalidStakeCap");
    await expect(escrow.connect(owner).setMaxStake(2_000_000n)).to.emit(escrow, "MaxStakeUpdated").withArgs(10_000_000_000n, 2_000_000n);
    await expect(escrow.connect(owner).setMaxStake(10_000_000_000n)).to.emit(escrow, "MaxStakeUpdated").withArgs(2_000_000n, 10_000_000_000n);
    // Fees are unaffected: the stake cap and the fee tiers are independent.
    expect(await escrow.quotePlatformFee(25_000_000n)).to.equal(3_500_000n);
  });
});

describe("Audit 2026-10 delta: check_v2_roles (D-03)", function () {
  let usdc, escrow, owner, resolver, treasury, safe;

  async function state() {
    return {
      version: Number(await escrow.ESCROW_VERSION()),
      owner: await escrow.owner(),
      pendingOwner: await escrow.pendingOwner(),
      resolver: await escrow.resolver(),
      feeRecipient: await escrow.feeRecipient(),
      usdc: await escrow.usdc(),
      maxStakeUsdc: ethers.formatUnits(await escrow.maxStakePerPlayer(), 6),
      paused: await escrow.paused(),
    };
  }

  beforeEach(async function () {
    [owner, resolver, treasury, safe] = await ethers.getSigners();
    usdc = await (await ethers.getContractFactory("MockUSDC")).deploy();
    escrow = await deployEscrow(usdc, treasury, resolver);
    await escrow.setMaxStake(25_000_000n);
    await escrow.transferOwnership(safe.address);
  });

  const full = () => ({
    EXPECT_OWNER: safe.address,
    EXPECT_RESOLVER: resolver.address,
    EXPECT_TREASURY: treasury.address,
    EXPECT_USDC: usdc.target,
    EXPECT_MAX_STAKE_USDC: "25",
  });

  it("D-03 a mainnet run with no expectations fails instead of printing OK", async function () {
    const { problems } = checkRoles(await state(), "arcMainnet", {});
    expect(problems.join(" | ")).to.match(/EXPECT_OWNER is required/);
    expect(problems.join(" | ")).to.match(/usdc .* != 0x3600/); // mock token is not Arc USDC
  });

  it("D-03 EXPECT_ACCEPTED=1 fails while the deployer is still owner, passes after acceptOwnership", async function () {
    const before = checkRoles(await state(), "hardhat", { ...full(), EXPECT_ACCEPTED: "1" });
    expect(before.problems.join(" | ")).to.match(/has not called acceptOwnership/);
    // Without EXPECT_ACCEPTED the post-deploy run passes with a note.
    const postDeploy = checkRoles(await state(), "hardhat", full());
    expect(postDeploy.problems).to.deep.equal([]);
    expect(postDeploy.notes.join(" ")).to.match(/EXPECT_ACCEPTED=1/);
    await escrow.connect(safe).acceptOwnership();
    expect(checkRoles(await state(), "hardhat", { ...full(), EXPECT_ACCEPTED: "1" }).problems).to.deep.equal([]);
  });

  it("D-03 flags a wrong resolver, treasury, cap, token or a paused escrow", async function () {
    await escrow.connect(owner).pause();
    const { problems } = checkRoles(await state(), "hardhat", {
      ...full(),
      EXPECT_RESOLVER: treasury.address,
      EXPECT_TREASURY: resolver.address,
      EXPECT_MAX_STAKE_USDC: "100",
      EXPECT_USDC: resolver.address,
    });
    const all = problems.join(" | ");
    for (const re of [/resolver mismatch/, /feeRecipient mismatch/, /maxStakePerPlayer 25.0 != 100/, /usdc/, /paused/]) {
      expect(all).to.match(re);
    }
  });
});
