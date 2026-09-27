/**
 * Reads the deployed source of BOTH instances back from the chain
 * (gen_getContractCode) and compares it byte-for-byte with
 * contracts/TOSGuard.py and with the sha256 recorded in deployments.json.
 * Exit 1 on any mismatch.
 *
 *   node verify_source.mjs
 *   node verify_source.mjs --github=<raw URL of contracts/TOSGuard.py>   # also compare GitHub's copy
 */
import { readFileSync } from "node:fs";
import { createHash } from "node:crypto";
import { createClient } from "genlayer-js";
import { CHAINS, argOf, retry } from "./harness.mjs";

const sha256 = (buf) => createHash("sha256").update(buf).digest("hex");
const dep = JSON.parse(readFileSync(new URL("../deployments.json", import.meta.url))).deployments.studiodev;
const local = readFileSync(new URL("../contracts/TOSGuard.py", import.meta.url));
const rubric = String(local).match(/^RUBRIC_VERSION\s*=\s*"([^"]+)"/m)[1];
const read = createClient({ chain: CHAINS.studiodev });

let bad = 0;
const line = (ok, text) => { if (!ok) bad++; console.log(`  ${ok ? "✔" : "✘"} ${text}`); };
console.log(`contracts/TOSGuard.py  ${local.length} bytes  sha256 ${sha256(local)}  rubric ${rubric}`);

const github = argOf("github");
if (github) {
  const res = await fetch(github, { cache: "no-store" });
  const remote = Buffer.from(await res.arrayBuffer());
  line(res.ok && Buffer.compare(remote, local) === 0, `GitHub ${github}: ${remote.length} bytes sha256 ${sha256(remote)}`);
}

for (const name of ["TOSGuard", "TOSGuardDemo"]) {
  const rec = dep[name];
  const code = Buffer.from(await retry(() => read.getContractCode(rec.address), { label: `${name} code` }), "utf8");
  const onChainRubric = String(code).match(/^RUBRIC_VERSION\s*=\s*"([^"]+)"/m)?.[1];
  console.log(`\n${name} ${rec.address}`);
  line(Buffer.compare(code, local) === 0, `on-chain source == contracts/TOSGuard.py (${code.length} bytes, sha256 ${sha256(code)})`);
  line(rec.source_sha256 === sha256(code), `deployments.json sha256 == on-chain`);
  line(onChainRubric === rubric && rec.rubric_version === rubric, `rubric on chain ${onChainRubric}, recorded ${rec.rubric_version}`);
}
console.log(bad ? `\n${bad} MISMATCH(ES)` : "\nall byte-for-byte identical");
process.exit(bad ? 1 : 0);
