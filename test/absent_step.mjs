// Rerun of lifecycle's last step on its own. The first attempt failed to
// SUBMIT (Studio RPC 30 req/min limit); the retry judged DuckDuckGo x
// AUTO_RENEWAL, which is SPARSE (one "subscription" clause), not ABSENT - the
// expectation was wrong, not the contract. DuckDuckGo x MANDATORY_ARBITRATION
// is ABSENT on the captured render, and lifecycle.mjs now uses it.
import { readFileSync, appendFileSync } from "node:fs";
import { connect, returnedJson, estimateFees, sleep } from "./harness.mjs";
const dep = JSON.parse(readFileSync(new URL("../deployments.json", import.meta.url))).deployments.studiodev;
const plain = (x) => JSON.parse(JSON.stringify(x, (k, v) => (typeof v === "bigint" ? v.toString() : v instanceof Map ? Object.fromEntries(v) : v)));
const out = connect({ address: dep.TOSGuard.address, role: "outsider" });
const c = connect({ address: dep.TOSGuard.address, role: "trigger" });
let r = await out.send("check_tos", ["https://duckduckgo.com/terms", "MANDATORY_ARBITRATION", ""]);
const id = returnedJson(r)?.check_id;
const lines = [`  ✔ check_tos accepted  #${id} tx ${r.hash}`];
await sleep(20_000);
r = await c.send("judge_check", [id], 0n, { fees: await estimateFees(c.wallet, "judge_check fee") });
const j = plain(await c.view("get_check", [id]));
const ok = j.outcome === "CLEAN" && j.case === "ABSENT" && j.findings.model_called === false;
lines.push(`  ${ok ? "✔" : "✘"} ABSENT on a full-length TOS is pinned CLEAN with no model call  #${id} ${j.url} ${j.flag_type} → ${j.outcome} ${j.case} model_called=${j.findings.model_called} tx ${r.hash}`);
console.log(lines.join("\n"));
appendFileSync(new URL("../docs/lifecycle-run.log", import.meta.url),
  "\nRerun of the last step (test/absent_step.mjs). Its first attempt failed to SUBMIT (Studio RPC: \"Rate limit exceeded: 30 requests per minute\").\n" +
  "A retry judged #8 (DuckDuckGo x AUTO_RENEWAL): INCONCLUSIVE, case SPARSE - the terms mention \"duckduckgo subscription\" once, so the ABSENT expectation was wrong, not the contract.\n" +
  "DuckDuckGo x MANDATORY_ARBITRATION is ABSENT on the captured render:\n" + lines.join("\n") + "\n");
