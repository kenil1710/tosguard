# TOSGuard — Terms of Service red flag detector

**GenLayer reads 10,000 words of legal text and judges whether a specific
clause exists. All flag types, severity levels and storage are deterministic.**

An Intelligent Contract on GenLayer Studio Dev (chain 61997). No frontend.

- **A consumer** is about to sign up for a service and wants to know one thing:
  do these terms let them sell my data? Do I waive my right to a class action?
  Does my subscription renew unless I cancel? They submit the TOS URL and pick
  the flag from a closed list of seven. It is free — a public good, not a
  dispute.
- **A service provider** is the other party in every record. Its own published
  words are the only evidence: quoted back verbatim, pinned by a content hash,
  and re-checkable whenever it rewrites them.

Anyone can then trigger the judgment. Every validator independently renders
the page, scans it, reads the relevant clauses and decides. The outcome is
stored only if the validators agree on the whole findings vector.

## Where the line is

| GenLayer (the model) decides | Deterministic code decides |
|---|---|
| whether the clauses in front of it impose the flag: RED_FLAG / CLEAN / INCONCLUSIVE | the 7-flag vocabulary and every word list |
| clarity (0–7) and scope (0–7), inside ranges at most two wide set by code | URL validation and normalisation |
| | rendering, sentence splitting, normalisation, the clause scan |
| | the content hash, the page-length bucket, evidence_present |
| | **the confidence gate**: whether a model is asked at all |
| | **the bracket**: which outcomes are even allowed |
| | **severity**: the flag's base, +1 for broad wording, 0 unless RED_FLAG |
| | the quote, the reason, the per-flag statistics, all storage |

The model is never asked for severity and never sees an outcome the bracket
does not allow.

## The seven red flags

| key | what it means | base severity |
|---|---|---|
| `DATA_SALE` | may sell or share your personal data with third parties | 6 |
| `CONTENT_OWNERSHIP` | perpetual / irrevocable / sublicensable license to your content | 5 |
| `AUTO_RENEWAL` | subscription renews and charges unless cancelled in time | 3 |
| `MANDATORY_ARBITRATION` | binding arbitration, class-action or jury waiver | 6 |
| `UNILATERAL_CHANGE` | terms may change at any time / without notice | 3 |
| `ACCOUNT_TERMINATION` | account may be terminated for any reason | 4 |
| `LIABILITY_WAIVER` | no liability for damages, "as is", capped liability | 4 |

No free text: `check_tos(url, "they sell my data")` is refused. A closed
vocabulary is what makes five validators answer the same question.
`get_vocabulary()` returns every topic word, explicit phrase and denial phrase
the scan uses.

## Flow

```
consumer ── check_tos(url, flag, concern?) ──▶ PENDING          (free; 1 per wallet per 120s)
         └─ batch_check(url, [flags])     ──▶ PENDING × n      (one round per flag later)

anyone  ── judge_check(id) ──▶ each validator:
             render(url, mode="text")            JavaScript-loaded terms included
             split → normalise → scan clauses    lower-case, collapsed, quotes unified
             excerpt = sorted matched clauses    ≤ 24 clauses / 6,000 chars
             bracket(case) → allowed outcomes, clarity/scope ranges
             confidence gate: keyword strength < 3 → answer without a model
             model (only at strength ≥ 3, inside the bracket)
           ── consensus on the findings vector ──▶ JUDGED (frozen)

anyone  ── settle_stalled(id) after the stall window ──▶ STALLED   (works while paused)
```

## The confidence gate and the bracket

Computed from the page before any model runs.

**Keyword strength** = the clauses that *explicitly state* the practice
("royalty-free license", "binding arbitration", "sell your personal
information") plus the clauses that *explicitly deny* it ("we do not sell").
Passing topical mentions — "our partners", "third-party software" — are not
signal.

| keyword evidence | case | outcome | model? |
|---|---|---|---|
| page would not render, or < 500 chars | UNREADABLE | INCONCLUSIVE | no |
| not a legal document (< 4 of 16 legal markers: login wall, block page, home page) | NOT_TOS | INCONCLUSIVE | no |
| **zero** topical clauses | ABSENT | **CLEAN** | no |
| topical clauses, keyword strength **0–2** | WEAK | **INCONCLUSIVE** | no |
| keyword strength **≥ 3**, all denials | DENIED | CLEAN / INCONCLUSIVE | yes, inside the bracket |
| keyword strength **≥ 3**, at least one explicit clause | EXPLICIT | RED_FLAG / CLEAN / INCONCLUSIVE | yes, inside the bracket |

**Why the gate counts signal clauses, not raw keyword matches.** In the first
two seed runs, three checks got the same content hash both times but a
different outcome. Those pages had **33, 7 and 5** keyword matches, so a gate
on raw matches ("1–2 → INCONCLUSIVE, 3+ → model") would have sent all three to
the model again. What they had in common was **0 or 1 signal clauses**. The two
checks that never moved had 5 and 9. So borderline evidence now always gets
the same answer, because no model is asked. RED_FLAG is reachable only when
three or more clauses take a position and at least one states the practice
outright.

A denial cuts its whole clause before explicit phrases are looked for, so
"does not share personal information with advertisers" is a denial, not a
sale. Reasoning for each choice: [`contracts/NOTES.md`](contracts/NOTES.md).

## Consensus: the full findings vector

Validators do not compare a verdict. They compare:

| compared exactly | compared within one bucket |
|---|---|
| outcome · severity_bucket · evidence_present · **content_hash** · page_length_bucket · **keyword_strength** · page_state · case · allowed set · ranges · legal-marker / conspicuous / matched / explicit / denied / broad counts · facts hash · model_called | clarity_bucket · scope_bucket |

Every clarity/scope range is at most two wide, so the tolerance can never
split two validators who agree on the outcome — and never let two outcomes
through.

**The leader cannot forge.** Before comparing, each validator runs
`_coherent`: it re-derives every field from the only things the leader chose
(the evidence and three values) and refuses any payload where anything else
differs — a severity, a case, a hash, a quote, a reason. After consensus,
`judge_check` rebuilds the record again from the agreed evidence; the leader's
derived fields are discarded. `verify_check(id)` does the same from storage,
for anyone, forever.

**The content hash pins what was read.**
`content_hash = fnv(url | flag_type | normalised excerpt | rubric)`. Clauses are
lower-cased, whitespace-collapsed, quote- and dash-unified, de-duplicated and
**sorted** before hashing — the Google Play shuffle lesson: a page that renders
its blocks in a different order still yields one hash; a page whose relevant
words change never does.

## Contract methods

**Write** (none payable; none raises — every refusal returns
`{"status": "REJECTED", "reason": …}`)

| method | who | notes |
|---|---|---|
| `check_tos(url, flag_type, concern="")` | anyone | https only; flag from the vocabulary; optional concern 20–200 chars; 1 request per wallet per 120s; one pending check per URL+flag |
| `batch_check(url, flag_types)` | anyone | up to 7 flags, all-or-nothing; counts as one request |
| `judge_check(check_id)` | **anyone** | one consensus round; unsettled rounds store nothing and can be retried; works while paused |
| `settle_stalled(check_id)` | **anyone** | closes a check nobody could judge within its stall window; **works while paused** |
| `claim_refund()` | anyone | returns any value ever sent (nothing costs anything) |
| `set_paused(bool)`, `transfer_ownership(addr)` | owner | pause stops **new checks only** |

**View**: `get_check(id)` · `get_url_report(url)` · `get_flag_stats(flag)` ·
`get_recent_checks(n)` · `get_vocabulary()` · `get_config()` ·
`verify_check(id)` · `preview_bracket(flag, text)` (the deterministic half on
any text, no model) · `get_checks_by_requester(addr)` · `get_stats()` ·
`get_refund(addr)`

## Deployed — Studio Dev (chain 61997)

| instance | address | settings |
|---|---|---|
| **TOSGuard** (canonical) | `0xeCF29bd912f571900D432164C3d4B4798B7a53B0` | 120s per-wallet cooldown, 1h stall window |
| TOSGuardDemo | `0x1AB66BBfEa8eB06fdfFDBD86571b62572C3Bb0A4` | **same bytes**; no cooldown, 60s stall — so `settle_stalled` can be watched |

`deployments.json` records each deploy's sha256; `tools/audit.py` check 32
fails if `contracts/TOSGuard.py` differs from it by one byte.

## Seeded results — run twice, identical

The nine checks were seeded **twice** on the same deployment, as 18 separate
checks, each judged by real consensus. `test/compare_runs.mjs` re-reads both
runs from the chain and compares every exact field:
**9 pairs, 0 outcome flips, 0 differences** (outcome, severity, evidence,
length bucket, case, keyword strength, model called, content hash). Clarity
and scope also matched.

| page · flag | brief expected | both runs | case | strength | model | why |
|---|---|---|---|---|---|---|
| twitter.com/en/tos · DATA_SALE | RED_FLAG | **INCONCLUSIVE** | WEAK | 1 | no | 33 topical clauses; the only one that takes a position is "we do not disclose personally-identifying information to third parties except in accordance with our privacy policy" |
| reddit.com/policies/user-agreement · CONTENT_OWNERSHIP | RED_FLAG | **INCONCLUSIVE** | UNREADABLE | 0 | no | Reddit refuses the validators' headless browser |
| duckduckgo.com/terms · DATA_SALE | CLEAN | **INCONCLUSIVE** | WEAK | 0 | no | only incidental third-party mentions; the no-sale promise is in DuckDuckGo's privacy policy, not its terms |
| wikipedia.org/wiki/Terms_of_Use · ACCOUNT_TERMINATION | either | **INCONCLUSIVE** | WEAK | 1 | no | redirects to the encyclopedia article *about* ToS, which has one quoted "can suspend or stop at any time" |
| example.com · DATA_SALE | INCONCLUSIVE | **INCONCLUSIVE** | UNREADABLE | 0 | no | 129 characters |
| twitter.com/en/tos · CONTENT_OWNERSHIP | — | **RED_FLAG** sev 6 | EXPLICIT | 5 | yes | "you grant us a worldwide, non-exclusive, royalty-free license (with the right to sublicense)…" |
| twitter.com/en/tos · MANDATORY_ARBITRATION | — | **RED_FLAG** sev 7 | EXPLICIT | 9 | yes | binding arbitration, class-action and jury-trial waiver |
| duckduckgo.com/terms · AUTO_RENEWAL | — | **INCONCLUSIVE** | WEAK | 0 | no | one passing "subscription" mention |
| duckduckgo.com/terms · MANDATORY_ARBITRATION | — | **CLEAN** | ABSENT | 0 | no | no arbitration language at all |

**Three brief expectations do not hold, and the record says so.** Reddit could
not be read. X's and DuckDuckGo's *terms* don't take a position on data sale
(both defer to a separate privacy policy), so the gate makes them
INCONCLUSIVE instead of letting a model guess. Before the gate, those two
flipped between runs (CLEAN ↔ INCONCLUSIVE); now they give the same answer
every time.

Every judged check re-derives cleanly with `verify_check`. Full read-back,
both runs' logs and transaction hashes: [`docs/EVIDENCE.md`](docs/EVIDENCE.md);
the pre-gate runs are in [`docs/superseded/`](docs/superseded/).

## Tests and audit

```bash
python3 test/test_logic.py        # offline suite, stdlib only
python3 tools/audit.py            # 33 rejection-pattern checks + source == deployed
genvm-lint lint contracts/TOSGuard.py

cd test && npm install
node accounts.mjs && node deploy.mjs --both
node seed.mjs --run=1 && node seed.mjs --run=2      # the nine checks, twice
node compare_runs.mjs                                # exit 1 on any outcome flip
node lifecycle.mjs && node collect.mjs               # refusals, pause, stall; docs/EVIDENCE.md
```

The offline suite (400 tests) runs the real contract against a
runtime stub whose TreeMap/DynArray reproduce the runner's semantics. It builds
all three gate tiers for every flag (and that the weak tier never reaches a
model), **one forgery per field** of the findings vector and requires `_coherent` to
refuse each; moves each compared field in a validator's reading and requires
disagreement; proves shuffled, re-cased and re-spaced renders hash identically;
brackets the real renders captured on Studio Dev (`test/fixtures/`); and walks
the source as an AST (zero `raise`, no `str.replace()`, no `self` in a nondet
closure, no counter before a refusal).

`test/lifecycle.mjs` drives on chain what the seed does not: six refusals that
return without reverting, a duplicate pending check, pause (and an outsider
failing to pause), **settle_stalled while paused by a wallet that filed
nothing**, the 120s cooldown, and an ABSENT page pinned CLEAN with no model
call.

## Honest limitations

- **TOS pages are mutable.** A result describes the terms at the moment they
  were read, and the content hash and stored excerpt pin exactly what that was.
  If a provider edits its terms between two validators' fetches, the round does
  not settle and is retried. A later edit is not reflected in an old check;
  submit a new one.
- **Terms behind a login wall, bot wall or CAPTCHA are INCONCLUSIVE.** Reddit
  refused Studio's headless browser outright, so the Reddit seed check is
  INCONCLUSIVE — the honest answer, not a guess.
- **Legal interpretation is subjective.** Two things bound it. The confidence
  gate keeps the model away from pages with fewer than three signal clauses
  (they are INCONCLUSIVE, identically, every time), and the bracket limits the
  model to outcomes the evidence allows (severity is never its call). Above
  the gate, RED_FLAG versus INCONCLUSIVE is still a reading. The two
  model-judged seed checks gave the same answer in all four runs, but a page
  with exactly three weak signal clauses is where a re-run is most likely to
  differ.
- **The gate trades recall for stability.** A page that implies a practice in
  thirty clauses without stating it explicitly (X on data sharing) is
  INCONCLUSIVE, not RED_FLAG. That's deliberate: "the terms don't settle it"
  is better than a result that changes between runs.
- **Zero matches means CLEAN at any length.** If a render is cut short before
  the relevant section, a silent page reads as CLEAN. The 500-character floor
  and the legal-marker test catch error pages and login walls, but not a
  long page that stops partway.
- **A TOS is not the whole contract.** Several services put their data
  practices in a separate privacy policy. X's and DuckDuckGo's terms both defer
  to one, so a `DATA_SALE` check on the terms page alone answers "do the
  *terms* say so", not "does the company do it". Check the privacy-policy URL
  too.
- **The scan is a word list, not a lawyer.** A clause phrased without any topic
  word is invisible to it (and so can only ever be CLEAN or INCONCLUSIVE, never
  RED_FLAG). `get_vocabulary()` publishes every word so anyone can see the
  boundary.
- **Some TOS pages load via JavaScript** — `web.render(mode="text")` runs the
  page's scripts and waits 3s after load, which handled every page probed. A
  page that loads its terms later than that reads as short or not-legal, and is
  INCONCLUSIVE.
- **URLs redirect.** `www.wikipedia.org/wiki/Terms_of_Use` lands on the
  encyclopedia article *about* terms of service, not on the Wikimedia
  Foundation's terms. The contract judges the page it is given.
- **The excerpt is capped** at 24 clauses / 6,000 characters (explicit clauses
  first). The matched-clause count covers the whole page; the model reads the
  excerpt.
- **Page-length buckets have edges.** A page whose dynamic chrome pushes it
  across a bucket boundary between renders will not settle that round.
- **Studio Dev** is a development network; its render service has stalled
  under load in previous projects (appaudit docs/PROBE.md §5).

## Repository

```
contracts/TOSGuard.py        the Intelligent Contract
contracts/NOTES.md           design reasoning and inherited hazards
contracts/_render_probe.py   throwaway: what a validator's render returns
tools/audit.py               33 mechanical checks
test/test_logic.py           offline suite
test/fixtures/               real renders captured on Studio Dev
test/*.mjs                   deploy, seed, lifecycle, collect, probe
docs/PROBE.md                what the renders showed
docs/EVIDENCE.md             every check read back from the chain
deployments.json             addresses, deploy txs, source sha256
```
