/**
 * Creates test/.accounts.json — a stable, reusable pool of signing keys.
 *
 * A POOL because TOSGuard rate-limits requests to one per wallet per 120s,
 * and because "judge_check is permissionless" and "only the owner can pause"
 * cannot be stated with one address.
 *
 * Keys are generated here rather than read off `createAccount()`, which does
 * not expose a `privateKey` field. Existing roles are PRESERVED unless --force.
 *
 * Usage: node accounts.mjs [--force]
 */
import { createAccount } from "genlayer-js";
import { randomBytes } from "node:crypto";
import { existsSync, readFileSync, writeFileSync } from "node:fs";

const target = new URL("./.accounts.json", import.meta.url);
const force = process.argv.includes("--force");

// `client` deploys and owns. `consumer1..6` each submit checks (the cooldown
// is per wallet). `trigger` calls judge_check / settle_stalled to prove they
// are permissionless. `outsider` only probes access control.
const ROLES = [
  "client",
  "consumer1", "consumer2", "consumer3", "consumer4", "consumer5", "consumer6",
  "trigger", "outsider",
];

const existing = existsSync(target) && !force ? JSON.parse(readFileSync(target, "utf8")) : {};
const out = {};
let created = 0;
for (const role of ROLES) {
  if (existing[role]?.key) {
    out[role] = existing[role];
    continue;
  }
  const key = `0x${randomBytes(32).toString("hex")}`;
  const account = createAccount(key);
  if (createAccount(key).address !== account.address) throw new Error(`key for ${role} is unstable`);
  out[role] = { key, address: account.address };
  created++;
}
writeFileSync(target, JSON.stringify(out, null, 2) + "\n");
console.log(`wrote .accounts.json — ${created} new, ${ROLES.length - created} preserved`);
for (const role of ROLES) console.log(`  ${role.padEnd(10)} ${out[role].address}`);
