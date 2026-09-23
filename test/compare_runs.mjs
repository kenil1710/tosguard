/**
 * Seed run 1 against seed run 2, re-read from the CHAIN (not from either
 * run's log). Exit 1 if any outcome differs.
 *
 * Compared exactly: outcome, severity, evidence_present, page-length bucket,
 * case, keyword strength, whether the model was called, the content hash.
 * Clarity and scope are shown; the contract itself tolerates one bucket on
 * them, so a difference there is reported but is not a flip.
 */
import { readFileSync, writeFileSync } from "node:fs";
import { connect } from "./harness.mjs";

const dep = JSON.parse(readFileSync(new URL("../deployments.json", import.meta.url))).deployments.studiodev;
const c = connect({ address: dep.TOSGuard.address, role: "trigger" });
const plain = (x) => JSON.parse(JSON.stringify(x, (k, v) => (typeof v === "bigint" ? v.toString() : v instanceof Map ? Object.fromEntries(v) : v)));
const r1 = JSON.parse(readFileSync(new URL("../docs/seed-run1-ids.json", import.meta.url), "utf8"));
const r2 = JSON.parse(readFileSync(new URL("../docs/seed-run2-ids.json", import.meta.url), "utf8"));

const EXACT = [
  ["outcome", (x) => x.outcome], ["severity", (x) => x.severity_bucket], ["evidence", (x) => x.evidence_present],
  ["length", (x) => x.page_length_bucket], ["case", (x) => x.case], ["strength", (x) => x.findings.keyword_strength], ["indicators", (x) => x.findings.indicators],
  ["model", (x) => x.findings.model_called], ["content_hash", (x) => x.content_hash], ["status", (x) => x.status],
];
const lines = ["| page · flag | run 1 | run 2 | outcome | case | strength | model | content hash | sev | clr / scp | identical |", "|---|---|---|---|---|---|---|---|---|---|---|"];
let flips = 0;
let diffs = 0;
for (const k of Object.keys(r1)) {
  const a = plain(await c.view("get_check", [r1[k]]));
  const b = plain(await c.view("get_check", [r2[k]]));
  const bad = EXACT.filter(([, f]) => String(f(a)) !== String(f(b))).map(([n]) => n);
  if (a.outcome !== b.outcome || a.status !== b.status) flips++;
  if (bad.length) diffs++;
  const [url, flag] = k.split(" ");
  lines.push(`| ${url.replace("https://", "")} · ${flag} | #${a.check_id} | #${b.check_id} | ${a.outcome === b.outcome ? a.outcome : a.outcome + " → " + b.outcome} | ${a.case} | ${a.findings.keyword_strength} | ${a.findings.model_called} | \`${a.content_hash}\`${a.content_hash === b.content_hash ? "" : " ≠ `" + b.content_hash + "`"} | ${a.severity_bucket}${a.severity_bucket === b.severity_bucket ? "" : "→" + b.severity_bucket} | ${a.clarity_bucket}/${a.scope_bucket} · ${b.clarity_bucket}/${b.scope_bucket} | ${bad.length ? "✘ " + bad.join(", ") : "✔"} |`);
}
const summary = `${Object.keys(r1).length} pairs, ${flips} outcome flips, ${diffs} pairs with any exact-field difference`;
lines.push("", summary);
writeFileSync(new URL("../docs/seed-compare.md", import.meta.url), lines.join("\n") + "\n");
console.log(lines.join("\n"));
process.exit(flips ? 1 : 0);
