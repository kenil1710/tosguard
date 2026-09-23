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
             model (only if the bracket leaves a choice)
           ── consensus on the findings vector ──▶ JUDGED (frozen)

anyone  ── settle_stalled(id) after the stall window ──▶ STALLED   (works while paused)
```

## The bracket

Computed from the page before any model runs.

| case | when | allowed |
|---|---|---|
| UNREADABLE | render failed, or < 500 chars | INCONCLUSIVE — pinned, no model |
| NOT_TOS | < 4 of 16 legal markers (login wall, block page, home page) | INCONCLUSIVE — pinned |
| ABSENT | legal document, zero topical clauses | CLEAN if ≥ 6,000 chars, else INCONCLUSIVE — pinned |
| SPARSE | 1–2 topical clauses, nothing explicit | CLEAN / INCONCLUSIVE |
| DENIED | a denial ("we do not sell…") and < 3 other topical clauses | CLEAN / INCONCLUSIVE |
| MENTIONED | ≥ 3 topical clauses, none explicit | RED_FLAG / CLEAN / INCONCLUSIVE |
| EXPLICIT | ≥ 1 clause in explicit wording ("royalty-free license", "binding arbitration") | RED_FLAG / CLEAN / INCONCLUSIVE |

**Zero keyword matches can never produce RED_FLAG.** A denial cuts its whole
clause before explicit phrases are looked for, so "does not share personal
information with advertisers" is a denial, not a sale. Reasoning for each
choice: [`contracts/NOTES.md`](contracts/NOTES.md).

## Consensus: the full findings vector

Validators do not compare a verdict. They compare:

| compared exactly | compared within one bucket |
|---|---|
| outcome · severity_bucket · evidence_present · **content_hash** · page_length_bucket · page_state · case · allowed set · ranges · legal-marker / conspicuous / matched / explicit / denied / broad counts · facts hash · model_called | clarity_bucket · scope_bucket |

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

## Seeded results

All on the canonical instance, through real consensus rounds; every judgment
settled on its first round.

| # | page · flag | brief expected | on chain | case | sev | why |
|---|---|---|---|---|---|---|
| 1 | twitter.com/en/tos · DATA_SALE | RED_FLAG | **INCONCLUSIVE** | MENTIONED | 0 | X's terms say "we do not disclose personally-identifying information to third parties except in accordance with our privacy policy" — the answer lives in the privacy policy |
| 2 | reddit.com/policies/user-agreement · CONTENT_OWNERSHIP | RED_FLAG | **INCONCLUSIVE** | UNREADABLE | 0 | Reddit refuses the validators' headless browser; nothing was read, so nothing is claimed |
| 3 | duckduckgo.com/terms · DATA_SALE | CLEAN | **CLEAN** | MENTIONED | 0 | only incidental third-party mentions (software, websites, a liability list) |
| 4 | wikipedia.org/wiki/Terms_of_Use · ACCOUNT_TERMINATION | RED_FLAG or CLEAN | **RED_FLAG** | EXPLICIT | 5 | the URL redirects to the encyclopedia article *about* ToS, which quotes services that "can suspend or stop at any time" |
| 5 | example.com · DATA_SALE | INCONCLUSIVE | **INCONCLUSIVE** | UNREADABLE | 0 | 129 characters, not a terms document; no model call |
| 6 | twitter.com/en/tos · CONTENT_OWNERSHIP *(batch)* | — | **RED_FLAG** | EXPLICIT | 6 | "you grant us a worldwide, non-exclusive, royalty-free license (with the right to sublicense)…" |
| 7 | twitter.com/en/tos · MANDATORY_ARBITRATION *(batch)* | — | **RED_FLAG** | EXPLICIT | 7 | binding arbitration, class-action and jury-trial waiver |
| 8 | duckduckgo.com/terms · AUTO_RENEWAL | — | **INCONCLUSIVE** | SPARSE | 0 | one passing "subscription" mention |
| 9 | duckduckgo.com/terms · MANDATORY_ARBITRATION | — | **CLEAN** | ABSENT | 0 | no arbitration language at all; pinned by the bracket, no model call |

**Two brief expectations did not hold, and the record says so.** Reddit could
not be read at all. X's *terms* do not contain a data-sale clause; they defer
to a separate privacy policy. The contract judges the page it is given.

**Re-running shows where the subjectivity is.** The seed ran twice (the first
deployment is in `docs/superseded/`). Every page produced the **same content
hash** both times, and the pinned and explicit cases gave the same outcome. The
three borderline pages did not: X·DATA_SALE went CLEAN → INCONCLUSIVE,
DuckDuckGo·DATA_SALE INCONCLUSIVE → CLEAN, and the Wikipedia article
INCONCLUSIVE → RED_FLAG. Validators agreed within each round both times;
across rounds, a borderline page can land on either allowed side
([docs/PROBE.md §6](docs/PROBE.md)).

Every judged check re-derives cleanly with `verify_check`. Full read-back,
quotes, hashes and transaction hashes: [`docs/EVIDENCE.md`](docs/EVIDENCE.md).

## Tests and audit

```bash
python3 test/test_logic.py        # offline suite, stdlib only
python3 tools/audit.py            # 33 rejection-pattern checks + source == deployed
genvm-lint lint contracts/TOSGuard.py

cd test && npm install
node accounts.mjs && node deploy.mjs --both
node seed.mjs && node lifecycle.mjs && node collect.mjs   # real consensus on Studio Dev
```

The offline suite (387 tests) runs the real contract against a
runtime stub whose TreeMap/DynArray reproduce the runner's semantics. It builds
**one forgery per field** of the findings vector and requires `_coherent` to
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
- **Legal interpretation is subjective.** The bracket bounds it: the model can
  only choose among outcomes the evidence allows, and severity is not its to
  choose. But inside the bracket, "RED_FLAG" versus "INCONCLUSIVE" is still a
  reading. Validators must agree on it within a round, yet on borderline pages
  a re-run can land on the other allowed outcome — measured on three of seven
  seed pages (same content hash, different outcome). Explicit clauses did not
  move. Treat a MENTIONED-case result as a lead, not a verdict.
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
