/**
 * Deploys contracts/_render_probe.py and renders each store URL through a real
 * validator, then dumps the full rendered text to docs/probe/<slug>.txt.
 *
 *   node probe.mjs [--address=0x..] url1 url2 ...
 */
import { readFileSync, writeFileSync, mkdirSync } from "node:fs";
import { connect, deploy, fundOnStudio, argOf } from "./harness.mjs";
import { createClient, createAccount } from "genlayer-js";

let address = argOf("address");
const urls = process.argv.slice(2).filter((a) => !a.startsWith("--"));
const base = connect({ address: address ?? "0x0000000000000000000000000000000000000000" });
await fundOnStudio(base.chain, base.account.address, 1000n * 10n ** 18n);
if (!address) {
  const code = readFileSync(new URL("../contracts/_render_probe.py", import.meta.url));
  const res = await deploy({ chain: base.chain, wallet: base.wallet, read: base.read, code, args: [], label: "probe deploy" });
  if (!res.ok) { console.error("deploy failed", res.out?.status, res.out?.stderr?.slice(-2000)); process.exit(1); }
  address = res.address;
  console.log("probe at", address);
}
const c = connect({ address });
mkdirSync(new URL("../docs/probe/", import.meta.url), { recursive: true });
for (const url of urls) {
  const t0 = Date.now();
  const out = await c.send("probe", [url, "3s"], 0n);
  console.log(url, out.status, out.ok, ((Date.now() - t0) / 1000).toFixed(0) + "s", out.hash);
  let text = "";
  let meta = null;
  for (let start = 0; ; start += 20000) {
    const w = JSON.parse(await c.view("window", [url, start, 20000]));
    meta = w;
    text += w.text;
    if (start + 20000 >= w.len) break;
  }
  const slug = url.replace(/^https?:\/\//, "").replace(/[^a-z0-9]+/gi, "_").slice(0, 90);
  writeFileSync(new URL(`../docs/probe/${slug}.txt`, import.meta.url), text);
  console.log(`  len ${meta.len} err ${meta.err.slice(0, 200)} tx ${out.hash}`);
}
