// Shared helpers for the v2 BoardmanEscrow / SpectatorPool tests.
import hre from "hardhat";
const { ethers } = hre;
import { time } from "@nomicfoundation/hardhat-network-helpers";

export const HOUR = 3600n;
export const DAY = 24n * HOUR;
export const OPEN_TIMEOUT = 24n * HOUR;
export const LOCK_TIMEOUT = 7n * DAY;
export const REFUND_GRACE = 7n * DAY;
export const CLAIM_WINDOW = 180n * DAY;

export const CREATE_MATCH_TYPES = {
  CreateMatch: [
    { name: "matchId", type: "bytes32" },
    { name: "player1", type: "address" },
    { name: "player2", type: "address" },
    { name: "stake", type: "uint256" },
    { name: "deadline", type: "uint256" },
  ],
};

export async function escrowDomain(escrow) {
  const { chainId } = await ethers.provider.getNetwork();
  return {
    name: "BoardmanEscrow",
    version: "2",
    chainId,
    verifyingContract: await escrow.getAddress(),
  };
}

/** Resolver EIP-712 permit over (matchId, player1, player2, stake, deadline). */
export async function signCreate(escrow, signer, { matchId, player1, player2, stake, deadline }) {
  return signer.signTypedData(await escrowDomain(escrow), CREATE_MATCH_TYPES, {
    matchId,
    player1,
    player2,
    stake,
    deadline,
  });
}

export async function deadlineIn(seconds = HOUR) {
  return BigInt(await time.latest()) + seconds;
}

/** Player1 creates a match bound to player2 using a fresh resolver permit. */
export async function createMatch(escrow, resolver, matchId, stake, p1, p2) {
  const deadline = await deadlineIn();
  const sig = await signCreate(escrow, resolver, {
    matchId,
    player1: p1.address,
    player2: p2.address,
    stake,
    deadline,
  });
  return escrow.connect(p1).createMatch(matchId, p2.address, stake, deadline, sig);
}

export async function deployEscrow(usdc, feeRecipient, resolver, openTimeout = OPEN_TIMEOUT, lockTimeout = LOCK_TIMEOUT) {
  const Escrow = await ethers.getContractFactory("BoardmanEscrow");
  const escrow = await Escrow.deploy(
    await usdc.getAddress(),
    feeRecipient.address,
    resolver.address,
    openTimeout,
    lockTimeout
  );
  await escrow.waitForDeployment();
  return escrow;
}

export async function deployPool(usdc, feeRecipient, resolver, refundGrace = REFUND_GRACE, claimWindow = CLAIM_WINDOW) {
  const Pool = await ethers.getContractFactory("SpectatorPool");
  const pool = await Pool.deploy(
    await usdc.getAddress(),
    feeRecipient.address,
    resolver.address,
    refundGrace,
    claimWindow
  );
  await pool.waitForDeployment();
  return pool;
}

/** Deterministic PRNG (mulberry32) so property tests are reproducible. */
export function prng(seed) {
  let a = seed >>> 0;
  return function next() {
    a = (a + 0x6d2b79f5) >>> 0;
    let t = a;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

export function randBig(rand, min, max) {
  const span = max - min + 1n;
  // two 32-bit draws are plenty for USDC-sized ranges
  const r = BigInt(Math.floor(rand() * 2 ** 32)) * 2n ** 32n + BigInt(Math.floor(rand() * 2 ** 32));
  return min + (r % span);
}
