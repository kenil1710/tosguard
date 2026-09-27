#!/usr/bin/env python3
"""The rejection ledger, made mechanical.

Every pattern that has cost a previous project a rejection is a check here,
walked over the SOURCE AS SYNTAX (never grepped: the contract's own comments
mention `str.replace()` and `raise` in order to warn about them), plus a few
checks that EXECUTE the pure half of the contract, and the one check that ties
the repository to the chain: the sha256 of the contract file must equal what
deployments.json recorded at deploy time.

    python3 tools/audit.py          # exit 1 on any failure
"""

import ast
import hashlib
import json
import re
import sys
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SOURCE = ROOT / "contracts" / "TOSGuard.py"
SRC = SOURCE.read_text(encoding="utf8")
TREE = ast.parse(SRC)
DEP = json.loads((ROOT / "deployments.json").read_text())["deployments"]["studiodev"]

results = []


def check(n, name, ok, detail=""):
    results.append((n, name, bool(ok), detail))


def cls(name):
    return [n for n in TREE.body if isinstance(n, ast.ClassDef) and n.name == name][0]


def methods(name):
    return {f.name: f for f in cls(name).body if isinstance(f, ast.FunctionDef)}


def fn(name):
    return [n for n in TREE.body if isinstance(n, ast.FunctionDef) and n.name == name][0]


def decos(f):
    return [ast.unparse(d) for d in f.decorator_list]


def text(f):
    return ast.unparse(f)


def const(name):
    node = [n for n in TREE.body if isinstance(n, ast.Assign)
            and getattr(n.targets[0], "id", "") == name][0]
    return ast.literal_eval(node.value)


# The pure half of the contract (everything before the first class), executed
# against an inert `genlayer` module. Nothing in that half touches storage.
_stub = types.ModuleType("genlayer")
_stub.gl = types.SimpleNamespace()
# Python 3.12 evaluates annotations eagerly (3.14 defers them), so the names
# the pure half annotates with must exist.
_names = ["Address", "u8", "u16", "u32", "u64", "u128", "u256", "i32", "i64", "bigint"]
for _n in _names:
    setattr(_stub, _n, str if _n == "Address" else int)
_stub.__all__ = _names
sys.modules.setdefault("genlayer", _stub)
_pure_tree = ast.parse(SRC)
_cut = next(i for i, n in enumerate(_pure_tree.body) if isinstance(n, ast.ClassDef))
_pure_tree.body = _pure_tree.body[:_cut]
P = types.ModuleType("tosguard_pure")
exec(compile(_pure_tree, str(SOURCE), "exec"), P.__dict__)

M = methods("TOSGuard")
W = {k: f for k, f in M.items() if any(d.startswith("gl.public.write") for d in decos(f))}
V = {k: f for k, f in M.items() if "gl.public.view" in decos(f)}

# 1 consensus binds every stored value
jw = text(M["_write_judgment"])
check(1, "consensus binds every stored judgment field (written only from re-derived d[...])",
      "out.get(" not in jw and all("d['" + f + "']" in jw for f in (
          "outcome", "severity_bucket", "clarity_bucket", "scope_bucket", "evidence_present",
          "content_hash", "page_length_bucket", "excerpt", "quote", "reason", "findings_key")))
# 2 leader can't forge
coh = text(fn("_coherent"))
check(2, "leader cannot forge: _coherent re-derives from evidence and compares every field",
      "_derive(" in coh and "VECTOR_STRS" in coh and "VECTOR_INTS" in coh
      and "VECTOR_BOOLS" in coh and "VECTOR_TOLERATED" in coh and "'excerpt'" in coh)
# 3 full findings vector compared
agr = text(fn("_agrees"))
vec = list(const("VECTOR_STRS")) + list(const("VECTOR_INTS")) + list(const("VECTOR_BOOLS"))
check(3, "validators compare the full findings vector, not just the verdict",
      len(vec) >= 15 and "outcome" in vec and "content_hash" in vec
      and all(k in agr for k in ("VECTOR_STRS", "VECTOR_INTS", "VECTOR_BOOLS", "VECTOR_TOLERATED")),
      str(len(vec)) + " exact fields")
# 4 the brief's consensus fields
brief = ("outcome", "severity_bucket", "clarity_bucket", "scope_bucket", "evidence_present",
         "content_hash", "page_length_bucket")
allvec = set(vec) | set(const("VECTOR_TOLERATED"))
check(4, "every consensus field the brief names is on the compared axis",
      all(b in allvec for b in brief), ", ".join(b for b in brief if b not in allvec))
# 5 zero raise
raises = [n.lineno for n in ast.walk(TREE) if isinstance(n, ast.Raise)]
check(5, "zero raise statements", not raises, str(raises))
# 6 payable surface
payable = sorted(k for k, f in W.items() if any(d.endswith("payable") for d in decos(f)))
check(6, "zero payable methods (no fee, no stake: a public good)", payable == [], ", ".join(payable))


# 7 refund-on-reject: every write books value to the sender first
def _first(f):
    body = f.body
    if isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant):
        body = body[1:]
    return ast.unparse(body[0])


check(7, "refund-on-reject on every path: each write's first statement books value to its sender (_bank)",
      all("self._bank()" in _first(f) for f in W.values()) and "refunds" not in text(M["_refuse"]))
# 8 no counter before refusal
bad = []
for name, f in W.items():
    ev = []
    for sub in ast.walk(f):
        if isinstance(sub, ast.Assign):
            for t in sub.targets:
                tx = ast.unparse(t)
                if tx.startswith(("self.total_", "self.last_request_at", "self.pending")):
                    ev.append((sub.lineno, "c"))
        if isinstance(sub, ast.Call) and ast.unparse(sub.func) == "self._new_check":
            ev.append((sub.lineno, "c"))
        if isinstance(sub, ast.Return) and sub.value is not None and "_refuse" in ast.unparse(sub.value):
            ev.append((sub.lineno, "r"))
    ev.sort()
    seen = False
    for _, k in ev:
        if k == "c":
            seen = True
        elif seen:
            bad.append(name)
            break
check(8, "no counter, rate-limit stamp or pending slot moves before a refusal", not bad, ", ".join(bad))
# 9 frozen after terminal
check(9, "a judged or stalled check never changes (judge_check and settle_stalled gated by _open)",
      "self._open(" in text(W["judge_check"]) and "self._open(" in text(W["settle_stalled"])
      and "TERMINAL" in text(M["_open"]))
# 10 pause gates only new checks
paused_readers = sorted({k for k, f in M.items() for s in ast.walk(f)
                         if isinstance(s, ast.Attribute) and s.attr == "paused"
                         and isinstance(s.ctx, ast.Load)} - {"get_stats", "get_config"})
check(10, "pause gates only new checks (_gate is the one reader)", paused_readers == ["_gate"],
      ", ".join(paused_readers))
check(11, "owner has no withdraw/sweep/rescue/edit method",
      not any(k in M for k in ("withdraw", "sweep", "rescue", "drain", "set_outcome", "edit_check",
                               "delete_check", "set_flags")))
# 12 content hash
chf = text(fn("_content_hash"))
check(12, "content hash = hash(url + flag_type + normalised excerpt)",
      all(s in chf for s in ("url", "flag_key", "excerpt")) and "_content_hash(url, flag_key, clean_ev['excerpt'])" in text(fn("_derive")))
# 13 settle_stalled
ss = text(W["settle_stalled"])
check(13, "settle_stalled exists, is permissionless and works while paused",
      "paused" not in ss and "sender_address" not in ss and "owner" not in ss)
# 14 no str.replace
reps = [n.lineno for n in ast.walk(TREE)
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) and n.func.attr == "replace"]
check(14, "no str.replace() calls", not reps, str(reps))
# 15 conservative
unread = P._bracket("DATA_SALE", P._read_page("", False, "DATA_SALE"))
nottos = P._bracket("DATA_SALE", P._read_page("Example Domain. " * 80, True, "DATA_SALE"))
check(15, "unreadable and non-legal pages are pinned INCONCLUSIVE with no model call",
      unread["allowed"] == ["INCONCLUSIVE"] and unread["pinned"]
      and nottos["allowed"] == ["INCONCLUSIVE"] and nottos["pinned"])
# 16 judge stores only re-derived
jd = text(W["judge_check"])
check(16, "judge_check stores only the record re-derived from agreed evidence + 3 chosen values",
      "_derive(task, _evidence_of(out), out.get('outcome'), out.get('clarity_bucket'), out.get('scope_bucket'))" in jd
      and "self._write_judgment(ck, d, now)" in jd and "_coherent(out, task)" in jd)
# 17 no trapped funds
check(17, "no trapped funds: claim_refund pays every banked wei; balance == refundable published",
      "claim_refund" in W and "booked == refundable" in text(V["get_stats"])
      and "claim_refund" not in paused_readers)
# 18 transfers only in _pay
callers = sorted({f.name for f in ast.walk(TREE) if isinstance(f, ast.FunctionDef)
                  for s in ast.walk(f) if isinstance(s, ast.Call) and isinstance(s.func, ast.Attribute)
                  and s.func.attr == "emit_transfer"})
check(18, "value leaves only through _pay (emit_transfer on gl.chain.Account)", callers == ["_pay"])
# 19 fee-estimable
both = [k for k, f in W.items() if "self._now()" in text(f) and "_pay(" in text(f)]
check(19, "no write both reads the block clock and posts a transfer (stale fee-simulator clock)",
      not both, ", ".join(both))
# 20 closures
leaks = [inner.name for k, f in M.items() if k != "verify_check" for inner in ast.walk(f)
         if isinstance(inner, ast.FunctionDef) and inner is not f
         and "self" in {n.id for n in ast.walk(inner) if isinstance(n, ast.Name)}]
check(20, "nondet closures capture no storage (no `self`)", not leaks, ", ".join(leaks))
# 21 normalisation / shuffle lesson
a = P._read_page("TERMS OF SERVICE. You agree to these terms. This agreement. Governing law. Privacy policy.\n"
                 + "We   SELL your personal data.\nWe share your data with partners.\n" + "Filler text here. " * 400,
                 True, "DATA_SALE")
b = P._read_page("terms of service. you agree to these terms. this agreement. governing law. privacy policy.\n"
                 + "We share your data with partners.\nwe sell your personal data.\n" + "Filler text here. " * 400,
                 True, "DATA_SALE")
check(21, "Google Play shuffle lesson: lower-cased, collapsed, sorted clauses hash identically",
      a["excerpt"] == b["excerpt"] and a["excerpt"] != "" and "sorted(" in text(fn("_read_page")))
# 22 header
lines = SRC.split("\n")
check(22, "v0.6 header: '# v0.3.0' then the pinned Depends line, then imports",
      lines[0] == "# v0.3.0" and lines[1].startswith('# { "Depends": "py-genlayer:')
      and lines[2] == "import genlayer as gl" and lines[3] == "from genlayer import *")
check(23, "runner hash pinned (no :test / :latest)",
      "py-genlayer:test" not in SRC and "py-genlayer:latest" not in SRC)
check(24, "class TOSGuard(gl.contract.Contract) with gl.storage.TreeMap / DynArray / allow",
      "class TOSGuard(gl.contract.Contract)" in SRC and "gl.storage.TreeMap" in SRC
      and "gl.storage.DynArray" in SRC and "@gl.storage.allow" in SRC)
check(25, "time from gl.message.raw datetime (no block.timestamp)", 'gl.message.raw.get("datetime"' in SRC)
# 26 closed vocabulary
check(26, "closed vocabulary of 7 flags; check_tos and batch_check refuse anything else",
      P.FLAG_KEYS == ("DATA_SALE", "CONTENT_OWNERSHIP", "AUTO_RENEWAL", "MANDATORY_ARBITRATION",
                      "UNILATERAL_CHANGE", "ACCOUNT_TERMINATION", "LIABILITY_WAIVER")
      and "_flag(flag_type)" in text(W["check_tos"]) and "_flag_list(flag_types)" in text(W["batch_check"])
      and P._flag("they sell my data") is None)
# 27 rate limit
gate = text(M["_gate"])
check(27, "one request per wallet per cooldown, stamped only after the last refusal",
      "last_request_at" in gate and "cooldown_s" in gate
      and "last_request_at[" in text(W["check_tos"]) and "last_request_at[" in text(W["batch_check"]))
# 28 URL rule
check(28, "https-only public URLs: http, IP literals, ports, credentials, internal hosts refused",
      not P._parse_url("http://a.com/")["ok"] and not P._parse_url("https://10.0.0.1/")["ok"]
      and not P._parse_url("https://a.com:8080/")["ok"] and not P._parse_url("https://u@a.com/")["ok"]
      and not P._parse_url("https://studio-webdriver:4444/")["ok"]
      and not P._parse_url("https://svc.internal/")["ok"] and P._parse_url("https://duckduckgo.com/terms")["ok"])
# 29 the confidence gate over DISTINCT indicator families, for all 7 flags:
#    0 matches -> CLEAN, 1 indicator -> INCONCLUSIVE (both no model),
#    2-4 -> one-sided (lean or INCONCLUSIVE), 5+ -> full bracket.
legal = ("Terms of Service. You agree to these terms. This agreement. Governing law applies. "
         "See our privacy policy. Jurisdiction lies with the courts.\n")
pad = "Filler text here.\n" * 600
gate_ok = const("WEAK_MAX_STRENGTH") == 1 and const("STRONG_MIN_STRENGTH") == 5
for k in P.FLAG_KEYS:
    flag = P._flag(k)
    anchor = "".join(g[0] + " " for g in flag[4])
    fams = flag[5]
    for n in (0, 1, 2, 4, 5):
        if n > len(fams):
            continue
        # one clause per family, each spelled with that family's first phrase
        clauses = "".join("Clause %d: %s%s here.\n" % (i, anchor, fams[i][1][0])
                          for i in range(n))
        br = P._bracket(k, P._read_page(legal + clauses + pad, True, k))
        want = ("ABSENT" if n == 0 else "WEAK" if n <= 1 else
                "MODERATE" if n < 5 else "STRONG")
        if br["case"] != want or br["strength"] != n:
            gate_ok = False
        if n <= 1 and not br["pinned"]:
            gate_ok = False
        if want == "MODERATE" and br["allowed"] != ["RED_FLAG", "INCONCLUSIVE"]:
            gate_ok = False
        if want == "STRONG" and br["allowed"] != ["RED_FLAG", "CLEAN", "INCONCLUSIVE"]:
            gate_ok = False
check(29, "confidence gate on distinct indicators, all 7 flags: 0 CLEAN, 1 INCONCLUSIVE (no model), 2-4 one-sided, 5+ full",
      gate_ok)
# 30 two-wide ranges
widths_ok = True
for k in P.FLAG_KEYS:
    for extra in ("", "We may sell your personal data at any time.\n",
                  "IN NO EVENT SHALL WE BE LIABLE FOR ANY DAMAGES WHATSOEVER.\n"):
        br = P._bracket(k, P._read_page(legal + extra * 3 + "Filler text here.\n" * 600, True, k))
        for o in br["allowed"]:
            for r in (br["clarity"][o], br["scope"][o]):
                if r[1] - r[0] not in (0, 1):
                    widths_ok = False
check(30, "every clarity/scope range is at most two wide (tolerance 1 can't split an honest round)",
      widths_ok and const("BUCKET_TOLERANCE") == 1)
# 31 severity deterministic
fj = text(fn("_from_json"))
check(31, "severity is deterministic: the model is never asked for it",
      "severity" not in fj and "severity" not in text(fn("_prompt"))
      and "severity_red" in text(fn("_derive")))
# 32 source == deployed, and the README publishes THOSE addresses. v1.2.1 was
# once rejected because the README still named the v1.0.0 instances.
sha = hashlib.sha256(SOURCE.read_bytes()).hexdigest()
readme = (ROOT / "README.md").read_text(encoding="utf8")
published = {a.lower() for a in re.findall(r"`(0x[0-9a-fA-F]{40})`", readme.split("## Deployed", 1)[-1].split("\n## ", 1)[0])}
deployed = {DEP.get(k, {}).get("address", "").lower() for k in ("TOSGuard", "TOSGuardDemo")}
check(32, "source == deployed byte-for-byte (sha256, canonical + demo); README names those addresses",
      DEP.get("TOSGuard", {}).get("source_sha256") == sha
      and DEP.get("TOSGuardDemo", {}).get("source_sha256") == sha
      and published == deployed, sha[:16] + " readme " + ",".join(sorted(published)))
check(33, "canonical instance enforces the brief (120s per wallet); demo is the same bytes",
      DEP.get("TOSGuard", {}).get("cooldown_s") == 120
      and DEP.get("TOSGuard", {}).get("payable_methods") == 0
      and DEP.get("TOSGuardDemo", {}).get("source_bytes") == len(SOURCE.read_bytes()))

width = max(len(r[1]) for r in results)
for n, name, ok, detail in results:
    print(("  ✔ " if ok else "  ✘ ") + str(n).rjust(2) + "  " + name.ljust(width)
          + ("   " + detail if detail and not ok else ""))
failed = [r for r in results if not r[2]]
print("\n" + str(len(results) - len(failed)) + "/" + str(len(results)) + " checks pass")
sys.exit(1 if failed else 0)
