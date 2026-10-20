// Audit 2026-10 L-04: deploy_v2.js preflight checks.
import hre from "hardhat";
const { ethers } = hre;
import { expect } from "chai";
import { preflight } from "../scripts/lib/v2_preflight.js";
import { deployEscrow } from "./helpers/boardman.js";

describe("Audit 2026-10: deploy_v2 preflight (L-04)", function () {
  let usdc, safe, owner, resolver, treasury;

  beforeEach(async function () {
    [owner, resolver, treasury] = await ethers.getSigners();
    usdc = await (await ethers.getContractFactory("MockUSDC")).deploy();
    // Any contract stands in for a deployed Safe.
    safe = await (await ethers.getContractFactory("MockUSDC")).deploy();
  });

  const args = (over = {}) => ({
    networkName: "arcTestnet",
    local: false,
    usdc: usdc.target,
    multisig: safe.target,
    treasury: treasury.address,
    resolver: resolver.address,
    env: {},
    ...over,
  });

  it("L-04 accepts a sane config and warns about an EOA treasury", async function () {
    const out = await preflight(ethers, args());
    expect(out.deployPool).to.equal(true);
    expect(out.warnings.join(" ")).to.match(/treasury .* EOA/);
  });

  it("L-04 refuses arcMainnet when the RPC is not chain 5042", async function () {
    await expect(preflight(ethers, args({ networkName: "arcMainnet" }))).to.be.rejectedWith(/expected 5042/);
  });

  it("L-04 refuses a token that is not 6-decimal USDC", async function () {
    const escrow = await deployEscrow(usdc, treasury, resolver);
    await expect(preflight(ethers, args({ usdc: escrow.target }))).to.be.rejectedWith(/no decimals/);
    await expect(preflight(ethers, args({ usdc: owner.address }))).to.be.rejectedWith(/no code/);
  });

  it("L-04 refuses an owner multisig with no code on this chain unless the EOA fallback is declared", async function () {
    await expect(preflight(ethers, args({ multisig: owner.address }))).to.be.rejectedWith(/has no code/);
    const out = await preflight(ethers, args({ multisig: owner.address, env: { V2_OWNER_IS_EOA: "1" } }));
    expect(out.ownerKind).to.match(/EOA/);
    expect(out.warnings.join(" ")).to.match(/move ownership to a Safe/);
    expect((await preflight(ethers, args())).ownerKind).to.match(/Safe/);
  });

  it("L-04 refuses a contract resolver (permits are plain ECDSA)", async function () {
    await expect(preflight(ethers, args({ resolver: safe.target }))).to.be.rejectedWith(/must be an EOA/);
  });

  it("L-04 never deploys SpectatorPool on a mainnet (no override)", async function () {
    expect((await preflight(ethers, args({ networkName: "baseMainnet" }))).deployPool).to.equal(false);
    expect((await preflight(ethers, args({ networkName: "baseMainnet", env: { V2_DEPLOY_POOL: "1" } }))).deployPool)
      .to.equal(false);
    expect((await preflight(ethers, args({ mainnet: true }))).deployPool).to.equal(false); // V2_TREAT_AS_MAINNET
    expect((await preflight(ethers, args())).deployPool).to.equal(true);
  });
});
