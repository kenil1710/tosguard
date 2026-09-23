/**
 * Seeds the CANONICAL TOSGuard instance with nine checks through real
 * consensus rounds on Studio Dev, then reads every record back.
 *
 *   node seed.mjs --run=1     # nine fresh checks
 *   node seed.mjs --run=2     # the SAME nine again, as new checks
 *   node compare_runs.mjs     # run 1 vs run 2: outcomes must be identical
 *
 * The nine:
 *   twitter.com/en/tos                  DATA_SALE              (consumer1)
 *   reddit.com/policies/user-agreement  CONTENT_OWNERSHIP      (consumer2)
 *   duckduckgo.com/terms                DATA_SALE              (consumer3)
 *   wikipedia.org/wiki/Terms_of_Use     ACCOUNT_TERMINATION    (consumer4)
 *   example.com                         DATA_SALE              (consumer5)
 *   twitter.com/en/tos   batch [CONTENT_OWNERSHIP, MANDATORY_ARBITRATION]   (consumer6)
 *   duckduckgo.com/terms batch [AUTO_RENEWAL, MANDATORY_ARBITRATION]        (outsider)
 *
 * Every judge_check is sent by `trigger`, a wallet that filed nothing, because
 * judging is permissionless. An unsettled round stores nothing and is retried
 * up to --tries times.
 *
 * RESUMABLE: the ids a run filed are written to docs/seed-run<N>-ids.json as
 * soon as they are known, and a rerun of the same --run judges those instead
 * of filing again. Before judging, each id is read back from the chain.
 */
import { readFileSync, writeFileSync, existsSync } from "node:fs";
import { connect, fundOnStudio, returnedJson, argOf, sleep, estimateFees } from "./harness.mjs";

const dep = JSON.parse(readFileSync(new URL("../deployments.json", import.meta.url))).deployments.studiodev;
const address = argOf("address", dep.TOSGuard.address);
const run = Number(argOf("run", "1"));
const tries = Number(argOf("tries", "3"));
const plain = (x) => JSON.parse(JSON.stringify(x, (k, v) => (typeof v === "bigint" ? v.toString() : v instanceof Map ? Object.fromEntries(v) : v)));

const SINGLE = [
  { role: "consumer1", url: "https://twitter.com/en/tos", flag: "DATA_SALE" },
  { role: "consumer2", url: "https://www.reddit.com/policies/user-agreement", flag: "CONTENT_OWNERSHIP" },
  { role: "consumer3", url: "https://duckduckgo.com/terms", flag: "DATA_SALE" },
  { role: "consumer4", url: "https://www.wikipedia.org/wiki/Terms_of_Use", flag: "ACCOUNT_TERMINATION" },
  { role: "consumer5", url: "https://example.com/", flag: "DATA_SALE" },
];
const BATCHES = [
  { role: "consumer6", url: "https://twitter.com/en/tos", flags: ["CONTENT_OWNERSHIP", "MANDATORY_ARBITRATION"] },
  { role: "outsider", url: "https://duckduckgo.com/terms", flags: ["AUTO_RENEWAL", "MANDATORY_ARBITRATION"] },
];

const idsPath = new URL(`../docs/seed-run${run}-ids.json`, import.meta.url);
const trg = connect({ address, role: "trigger" });
await fundOnStudio(trg.chain, trg.account.address, 100n * 10n ** 18n);
const log = [];
const note = (line) => { console.log(line); log.push(line); };
note(`TOSGuard seed run ${run} → ${address}  (${new Date().toISOString()})`);

const ids = existsSync(idsPath) ? JSON.parse(readFileSync(idsPath, "utf8")) : {};
const save = () => writeFileSync(idsPath, JSON.stringify(ids, null, 2) + "\n");
const key = (url, flag) => `${url} ${flag}`;

/** The newest check for url+flag with an id above `floor`. */
async function newest(url, flag, floor) {
  const r = plain(await trg.view("get_url_report", [url]));
  const hit = (r.checks ?? []).filter((c) => c.flag_type === flag && c.check_id > floor);
  return hit.length ? Math.max(...hit.map((c) => c.check_id)) : null;
}

const floor = Number(plain(await trg.view("get_stats", [])).checks);
for (const s of SINGLE) {
  if (ids[key(s.url, s.flag)]) { note(`already filed ${key(s.url, s.flag)} as #${ids[key(s.url, s.flag)]}`); continue; }
  const c = connect({ address, role: s.role });
  await fundOnStudio(c.chain, c.account.address, 20n * 10n ** 18n);
  const out = await c.send("check_tos", [s.url, s.flag, ""]);
  const ret = returnedJson(out);
  const id = ret?.check_id ?? (await newest(s.url, s.flag, floor));
  note(`check_tos ${s.url} ${s.flag} by ${s.role}: ${out.status} tx ${out.hash} → #${id} ${ret?.status ?? ""} ${ret?.reason ?? ""}`);
  if (id) { ids[key(s.url, s.flag)] = id; save(); }
}
for (const b of BATCHES) {
  if (b.flags.every((f) => ids[key(b.url, f)])) { note(`already filed batch ${b.url}`); continue; }
  const c = connect({ address, role: b.role });
  await fundOnStudio(c.chain, c.account.address, 20n * 10n ** 18n);
  const out = await c.send("batch_check", [b.url, b.flags]);
  const ret = returnedJson(out);
  note(`batch_check ${b.url} [${b.flags.join(", ")}] by ${b.role}: ${out.status} tx ${out.hash} → ${ret ? JSON.stringify(ret) : "(return unreadable; ids read from get_url_report)"}`);
  for (const f of b.flags) {
    const id = await newest(b.url, f, floor);
    if (id) ids[key(b.url, f)] = id;
  }
  save();
}

async function judgeUntilDone(cid) {
  for (let i = 1; i <= tries; i++) {
    const ck = plain(await trg.view("get_check", [cid]));
    if (ck.status !== "PENDING") return ck;
    // The GENERIC fee estimate: simulating a judgment would render the page
    // again, and judge_check posts no transfer.
    const fees = await estimateFees(trg.wallet, "judge_check fee");
    const out = await trg.send("judge_check", [cid], 0n, { fees });
    const ret = returnedJson(out);
    note(`  judge_check(${cid}) try ${i}: ${out.status} ${out.seconds.toFixed(0)}s tx ${out.hash} → ${ret ? JSON.stringify(ret) : "(return unreadable)"}`);
    // Studio has been seen answering a read with the pre-write state just
    // after a write finalised (docs/PROBE.md §7): wait before deciding to retry.
    await sleep(15_000);
    const after = plain(await trg.view("get_check", [cid]));
    if (after.status !== "PENDING") return after;
  }
  return plain(await trg.view("get_check", [cid]));
}

const results = {};
for (const [k, cid] of Object.entries(ids)) {
  note(`\njudging #${cid}  ${k}`);
  const ck = await judgeUntilDone(cid);
  const v = plain(await trg.view("verify_check", [cid]));
  results[k] = { check: ck, verified: v.verified === true };
  note(`  #${cid}: ${ck.status} ${ck.outcome || "-"}  sev ${ck.severity_bucket} clr ${ck.clarity_bucket} scp ${ck.scope_bucket} ev ${ck.evidence_present} len ${ck.page_length_bucket} case ${ck.case} strength ${ck.findings?.keyword_strength} model ${ck.findings?.model_called} hash ${ck.content_hash} verify ${v.verified}`);
  if (ck.quote) note(`  quote: "${ck.quote.slice(0, 240)}"`);
  note(`  reason: ${ck.reason}`);
  await sleep(8_000);
}

writeFileSync(new URL(`../docs/seed-run${run}-evidence.json`, import.meta.url), JSON.stringify({ address, run, results }, null, 2) + "\n");
writeFileSync(new URL(`../docs/seed-run${run}.log`, import.meta.url), log.join("\n") + "\n");
note(`\nwrote docs/seed-run${run}.log and docs/seed-run${run}-evidence.json`);
