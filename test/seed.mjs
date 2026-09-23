/**
 * Seeds the CANONICAL TOSGuard instance with the brief's checks, through real
 * consensus rounds on Studio Dev, then reads every record back.
 *
 *   1  twitter.com/en/tos                     DATA_SALE              (consumer1)
 *   2  reddit.com/policies/user-agreement     CONTENT_OWNERSHIP      (consumer2)
 *   3  duckduckgo.com/terms                   DATA_SALE              (consumer3)
 *   4  wikipedia.org/wiki/Terms_of_Use        ACCOUNT_TERMINATION    (consumer4)
 *   5  example.com                            DATA_SALE              (consumer5)  → INCONCLUSIVE (not a TOS)
 *   6+ twitter.com/en/tos  batch_check [CONTENT_OWNERSHIP, MANDATORY_ARBITRATION] (consumer6)
 *
 * Every judge_check is sent by `trigger`, a wallet that filed nothing, because
 * judging is permissionless. An unsettled round is retried (nothing is stored
 * by one), up to --tries times.
 *
 * RESUMABLE: each step asks the chain whether it already happened (by URL and
 * flag, via get_url_report) instead of trusting this script's memory.
 *
 *   node seed.mjs [--tries=3]
 */
import { readFileSync, writeFileSync } from "node:fs";
import { connect, fundOnStudio, returnedJson, argOf, sleep, estimateFees } from "./harness.mjs";

const dep = JSON.parse(readFileSync(new URL("../deployments.json", import.meta.url))).deployments.studiodev;
const address = argOf("address", dep.TOSGuard.address);
const tries = Number(argOf("tries", "3"));
const plain = (x) => JSON.parse(JSON.stringify(x, (k, v) => (typeof v === "bigint" ? v.toString() : v instanceof Map ? Object.fromEntries(v) : v)));

const SEED = [
  { role: "consumer1", url: "https://twitter.com/en/tos", flag: "DATA_SALE", expect: "RED_FLAG (brief)" },
  { role: "consumer2", url: "https://www.reddit.com/policies/user-agreement", flag: "CONTENT_OWNERSHIP", expect: "RED_FLAG (brief); INCONCLUSIVE if Reddit refuses the render, as it did the probe" },
  { role: "consumer3", url: "https://duckduckgo.com/terms", flag: "DATA_SALE", expect: "CLEAN (brief)" },
  { role: "consumer4", url: "https://www.wikipedia.org/wiki/Terms_of_Use", flag: "ACCOUNT_TERMINATION", expect: "RED_FLAG or CLEAN (brief)" },
  { role: "consumer5", url: "https://example.com/", flag: "DATA_SALE", expect: "INCONCLUSIVE (not a TOS)" },
];
const BATCH = { role: "consumer6", url: "https://twitter.com/en/tos", flags: ["CONTENT_OWNERSHIP", "MANDATORY_ARBITRATION"] };

const trg = connect({ address, role: "trigger" });
await fundOnStudio(trg.chain, trg.account.address, 100n * 10n ** 18n);
const log = [];
const note = (line) => { console.log(line); log.push(line); };
note(`TOSGuard seed → ${address}  (${new Date().toISOString()})`);

async function report(url) {
  return plain(await trg.view("get_url_report", [url]));
}
async function findCheck(url, flag) {
  const r = await report(url);
  if (!r.found) return null;
  return r.checks.find((c) => c.flag_type === flag) ?? null;
}

async function judgeUntilDone(cid) {
  for (let i = 1; i <= tries; i++) {
    const ck = plain(await trg.view("get_check", [cid]));
    if (ck.status !== "PENDING") return ck;
    // The GENERIC fee estimate, not a simulated one: simulating a judgment
    // renders the page a sixth time (appaudit docs/PROBE.md §5), and
    // judge_check posts no transfer that would need a message allocation.
    const fees = await estimateFees(trg.wallet, "judge_check fee");
    const out = await trg.send("judge_check", [cid], 0n, { fees });
    const ret = returnedJson(out);
    note(`  judge_check(${cid}) try ${i}: ${out.status} ${out.seconds.toFixed(0)}s tx ${out.hash} → ${ret ? JSON.stringify(ret) : "(return unreadable)"}`);
    const after = plain(await trg.view("get_check", [cid]));
    if (after.status !== "PENDING") return after;
    await sleep(15_000);
  }
  return plain(await trg.view("get_check", [cid]));
}

const ids = [];
for (const s of SEED) {
  note(`\n${s.url}  ${s.flag}   expected: ${s.expect}`);
  let ck = await findCheck(s.url, s.flag);
  if (!ck) {
    const c = connect({ address, role: s.role });
    await fundOnStudio(c.chain, c.account.address, 20n * 10n ** 18n);
    const out = await c.send("check_tos", [s.url, s.flag, ""]);
    note(`  check_tos by ${s.role}: ${out.status} tx ${out.hash} → ${JSON.stringify(returnedJson(out))}`);
    ck = await findCheck(s.url, s.flag);
  } else note(`  already filed as #${ck.check_id} (${ck.status})`);
  ids.push(ck.check_id);
}

note(`\nbatch ${BATCH.url} ${BATCH.flags.join(",")}`);
let batchIds = [];
{
  const have = [];
  for (const f of BATCH.flags) have.push(await findCheck(BATCH.url, f));
  if (have.every(Boolean)) {
    batchIds = have.map((c) => c.check_id);
    note(`  already filed as ${batchIds.join(", ")}`);
  } else {
    const c = connect({ address, role: BATCH.role });
    await fundOnStudio(c.chain, c.account.address, 20n * 10n ** 18n);
    const out = await c.send("batch_check", [BATCH.url, BATCH.flags]);
    const ret = returnedJson(out);
    note(`  batch_check by ${BATCH.role}: ${out.status} tx ${out.hash} → ${JSON.stringify(ret)}`);
    for (const f of BATCH.flags) batchIds.push((await findCheck(BATCH.url, f)).check_id);
  }
}

const all = [...ids, ...batchIds];
const results = {};
for (const cid of all) {
  note(`\njudging #${cid}`);
  const ck = await judgeUntilDone(cid);
  results[cid] = ck;
  note(`  #${cid} ${ck.url} ${ck.flag_type}: ${ck.status} ${ck.outcome || "-"}  sev ${ck.severity_bucket} clr ${ck.clarity_bucket} scp ${ck.scope_bucket} ev ${ck.evidence_present} len ${ck.page_length_bucket} case ${ck.case}`);
  if (ck.quote) note(`  quote: "${ck.quote.slice(0, 300)}"`);
  note(`  reason: ${ck.reason}`);
  await sleep(10_000);
}

note(`\nverify_check (recompute every stored field from the stored evidence)`);
const verified = {};
for (const cid of all) {
  const v = plain(await trg.view("verify_check", [cid]));
  verified[cid] = v;
  note(`  #${cid}: ${v.judged ? (v.verified ? "VERIFIED" : "MISMATCH") : "not judged"}`);
}
const stats = {};
for (const f of ["DATA_SALE", "CONTENT_OWNERSHIP", "ACCOUNT_TERMINATION", "MANDATORY_ARBITRATION"]) {
  stats[f] = plain(await trg.view("get_flag_stats", [f]));
  note(`  get_flag_stats(${f}): ${JSON.stringify(stats[f].by_outcome)} urls_flagged ${stats[f].urls_flagged}/${stats[f].urls_judged}`);
}
const contractStats = plain(await trg.view("get_stats", []));
note(`  get_stats: ${JSON.stringify(contractStats)}`);

const full = {};
for (const cid of all) full[cid] = plain(await trg.view("get_check", [cid]));
writeFileSync(new URL("../docs/seed-evidence.json", import.meta.url), JSON.stringify({ address, checks: full, verified, stats, contract: contractStats }, null, 2) + "\n");
writeFileSync(new URL("../docs/seed-run.log", import.meta.url), log.join("\n") + "\n");
note(`\nwrote docs/seed-evidence.json and docs/seed-run.log`);
