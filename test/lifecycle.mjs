/**
 * The paths a seed of happy judgments never touches, on chain:
 *
 *   DEMO instance (same bytes, 60s stall, no cooldown)
 *     - refusals RETURN, never revert: http URL, private host, free-text flag,
 *       short concern, duplicate pending, bad batch - and the check count does
 *       not move for any of them
 *     - the owner pauses; a new check is refused; an outsider cannot pause
 *     - settle_stalled on a pending check WHILE PAUSED, by a wallet that filed
 *       nothing (permissionless)
 *     - unpause
 *   CANONICAL instance
 *     - the 120s per-wallet cooldown refuses a second request
 *     - a real TOS that never mentions the flag is pinned CLEAN, no model
 *
 *   node lifecycle.mjs
 */
import { readFileSync, writeFileSync } from "node:fs";
import { connect, fundOnStudio, returnedJson, sleep, estimateFees } from "./harness.mjs";

const dep = JSON.parse(readFileSync(new URL("../deployments.json", import.meta.url))).deployments.studiodev;
const plain = (x) => JSON.parse(JSON.stringify(x, (k, v) => (typeof v === "bigint" ? v.toString() : v instanceof Map ? Object.fromEntries(v) : v)));
const log = [];
const note = (l) => { console.log(l); log.push(l); };
let pass = 0, fail = 0;
const expect = (label, cond, detail = "") => { cond ? pass++ : fail++; note(`  ${cond ? "✔" : "✘"} ${label}${detail ? "  " + detail : ""}`); };

const demo = dep.TOSGuardDemo.address;
const owner = connect({ address: demo, role: "client" });
const alice = connect({ address: demo, role: "consumer1" });
const trg = connect({ address: demo, role: "trigger" });
const out_ = connect({ address: demo, role: "outsider" });
for (const c of [owner, alice, trg, out_]) await fundOnStudio(c.chain, c.account.address, 50n * 10n ** 18n);
const count = async (c) => Number(plain(await c.view("get_stats", [])).checks);

note(`lifecycle on DEMO ${demo}  (${new Date().toISOString()})`);
const refusals = [
  ["http URL", "check_tos", ["http://duckduckgo.com/terms", "DATA_SALE", ""]],
  ["private host", "check_tos", ["https://10.0.0.1/terms", "DATA_SALE", ""]],
  ["render-service host", "check_tos", ["https://studio-webdriver:4444/render", "DATA_SALE", ""]],
  ["free-text flag", "check_tos", ["https://duckduckgo.com/terms", "they sell my data", ""]],
  ["short concern", "check_tos", ["https://duckduckgo.com/terms", "DATA_SALE", "too short"]],
  ["batch with unknown flag", "batch_check", ["https://duckduckgo.com/terms", ["DATA_SALE", "SPYWARE"]]],
];
const before = await count(alice);
for (const [label, m, args] of refusals) {
  const r = await alice.send(m, args);
  const ret = returnedJson(r);
  expect(`${label} refused without reverting`, r.ok && ret?.status === "REJECTED", `${r.status} → ${ret?.reason ?? JSON.stringify(ret)} tx ${r.hash}`);
}
expect("no refusal created a check", (await count(alice)) === before);

let r = await alice.send("check_tos", ["https://duckduckgo.com/terms", "AUTO_RENEWAL", "Does anything I sign up for renew and charge me automatically?"]);
let ret = returnedJson(r);
const cid = ret?.check_id;
expect("check_tos accepted", r.ok && ret?.status === "OK", `check #${cid} tx ${r.hash}`);
r = await trg.send("check_tos", ["https://duckduckgo.com/terms", "AUTO_RENEWAL", ""]);
ret = returnedJson(r);
expect("duplicate pending check refused", ret?.status === "REJECTED" && ret?.pending_check_id === cid, ret?.reason);

r = await out_.send("set_paused", [true]);
expect("outsider cannot pause", returnedJson(r)?.status === "REJECTED", returnedJson(r)?.reason);
r = await owner.send("set_paused", [true]);
expect("owner pauses", returnedJson(r)?.paused === true, `tx ${r.hash}`);
r = await out_.send("check_tos", ["https://example.org/terms", "DATA_SALE", ""]);
expect("new check refused while paused", returnedJson(r)?.status === "REJECTED", returnedJson(r)?.reason);

const ck = plain(await trg.view("get_check", [cid]));
const wait = Math.max(0, ck.stalls_at - Math.floor(Date.now() / 1000)) + 5;
note(`  waiting for the 60s stall window (block clock; up to ${wait}s + retries)`);
await sleep(Math.min(wait, 70) * 1000);
let settled = null;
for (let i = 0; i < 6 && !settled; i++) {
  r = await trg.send("settle_stalled", [cid]);
  ret = returnedJson(r);
  if (ret?.status === "OK") settled = ret;
  else { note(`  settle_stalled not yet: ${ret?.reason}`); await sleep(20_000); }
}
expect("settle_stalled works WHILE PAUSED, sent by a wallet that filed nothing", Boolean(settled), `tx ${r.hash}`);
const after = plain(await trg.view("get_check", [cid]));
expect("stalled check is terminal with no outcome", after.status === "STALLED" && after.outcome === "", after.reason);
r = await trg.send("judge_check", [cid]);
expect("a stalled check cannot be judged", returnedJson(r)?.status === "REJECTED", returnedJson(r)?.reason);
r = await owner.send("set_paused", [false]);
expect("owner unpauses", returnedJson(r)?.paused === false);

note(`\ncooldown on CANONICAL ${dep.TOSGuard.address}`);
const canon = connect({ address: dep.TOSGuard.address, role: "outsider" });
r = await canon.send("check_tos", ["https://duckduckgo.com/terms", "MANDATORY_ARBITRATION", ""]);
ret = returnedJson(r);
expect("first request accepted", ret?.status === "OK", `check #${ret?.check_id} tx ${r.hash}`);
const firstId = ret?.check_id;
r = await canon.send("check_tos", ["https://duckduckgo.com/terms", "LIABILITY_WAIVER", ""]);
ret = returnedJson(r);
expect("second request inside 120s refused", ret?.status === "REJECTED" && /120s/.test(ret?.reason ?? ""), ret?.reason);
// Judge that first request: DuckDuckGo's terms never mention arbitration, a
// class action or a jury, so the scan pins it ABSENT -> CLEAN with no model
// call (the page is > 6,000 chars).
const canonTrg = connect({ address: dep.TOSGuard.address, role: "trigger" });
if (firstId) {
  await sleep(30_000); // Studio meters 30 requests a minute per client
  r = await canonTrg.send("judge_check", [firstId], 0n, { fees: await estimateFees(canonTrg.wallet, "judge_check fee") });
  ret = returnedJson(r);
  const j = plain(await canonTrg.view("get_check", [firstId]));
  expect("ABSENT on a full-length TOS is pinned CLEAN with no model call",
    j.outcome === "CLEAN" && j.case === "ABSENT" && j.findings.model_called === false,
    `#${firstId} ${j.outcome} ${j.case} tx ${r.hash}`);
}


const stats = plain(await trg.view("get_stats", []));
note(`\ndemo get_stats: ${JSON.stringify(stats)}`);
note(`\n${pass} passed, ${fail} failed`);
writeFileSync(new URL("../docs/lifecycle-run.log", import.meta.url), log.join("\n") + "\n");
process.exit(fail ? 1 : 0);
