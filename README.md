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
             confidence gate: 0–1 distinct indicators → answer without a model
             model (2–4 indicators: one-sided bracket; 5+: full bracket)
           ── consensus on the findings vector ──▶ JUDGED (frozen)

anyone  ── settle_stalled(id) after the stall window ──▶ STALLED   (works while paused)
```

## The confidence gate and the bracket

Computed from the page before any model runs.

**Indicators.** Each flag has indicator families. For example, DATA_SALE has
sell · share · third party · partner · advertiser · marketing · monetize ·
personalized ads · data broker · affiliate. MANDATORY_ARBITRATION has
arbitration · waive · class action · individual basis · dispute resolution ·
binding arbitration. Each family is spelled as the multi-word phrases terms
really use ("with third parties", "advertising partners", "binding
arbitration"). **Keyword strength = the number of *distinct* families a page
hits**, so thirty clauses saying "with third parties" count as one indicator.
`get_vocabulary()` lists every family and phrase.

**Context rules.** A clause only counts if it is *about* the flag:
- **Denials are cut first:** "we do not sell your data" is never a sale.
- **CONTENT_OWNERSHIP:** the clause must mention a license or grant, and
  licences over *feedback* or granted *to you* are excluded.
- **UNILATERAL_CHANGE:** the clause must name the terms *and* a change verb.
- **ACCOUNT_TERMINATION:** the clause must mention the account, access or
  service.

| evidence | case | outcome | model? |
|---|---|---|---|
| page would not render, or < 500 chars | UNREADABLE | INCONCLUSIVE | no |
| not a legal document (< 4 of 16 legal markers) | NOT_TOS | INCONCLUSIVE | no |
| no clause hits any indicator | ABSENT | **CLEAN** | no |
| **0–1** distinct indicators | WEAK | **INCONCLUSIVE** | no |
| **2–4** distinct indicators | MODERATE | the side the clauses lean (RED_FLAG, or CLEAN if denials outnumber) **or** INCONCLUSIVE | yes, one-sided |
| **5+** distinct indicators | STRONG | RED_FLAG / CLEAN / INCONCLUSIVE | yes |

The one-sided MODERATE bracket means moderate evidence can never be read the
opposite way round: a page whose clauses state a practice can't come back
CLEAN, and a page of denials can't come back RED_FLAG. Why each rule exists,
including the two versions it replaced: [`contracts/NOTES.md`](contracts/NOTES.md) §2.

## Consensus: the full findings vector

Validators do not compare a verdict. They compare:

| compared exactly | compared within one bucket |
|---|---|
| outcome · severity_bucket · evidence_present · **content_hash** · page_length_bucket · **keyword_strength** · **indicators** · page_state · case · allowed set · ranges · legal-marker / conspicuous / matched / explicit / denied / broad counts · facts hash · model_called | clarity_bucket · scope_bucket |

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

## Seeded results: two runs, identical

Every URL was first rendered by a validator through a throwaway probe
contract. The scanner was run over those exact bytes
([`docs/probe-report.md`](docs/probe-report.md)), and a check was only seeded
where the terms clearly address the flag.

The nine checks were then seeded **twice** on the same deployment (18
separate checks, each judged by real consensus). `test/compare_runs.mjs`
re-read both runs from the chain: **9 pairs, 0 outcome flips, 0 differences**
in outcome, severity, evidence, length bucket, case, keyword strength,
indicators, model-called or content hash. Clarity and scope matched too.

**8 of 9 are decisive (7 RED_FLAG, 2 CLEAN). The one INCONCLUSIVE is a page
with nothing to read.**

| page · flag | both runs | case · strength | evidence (quoted from the stored excerpt) |
|---|---|---|---|
| x.com/en/tos · CONTENT_OWNERSHIP | **RED_FLAG** sev 6 | STRONG · 6 | "you grant us a worldwide, non-exclusive, royalty-free license (with the right to sublicense) to use, copy, reproduce, process, adapt…" |
| x.com/en/tos · MANDATORY_ARBITRATION | **RED_FLAG** sev 7 | STRONG · 5 | "any arbitration shall be conducted on an individual basis only, and not as a class, collective, or representative action" |
| discord.com/terms · CONTENT_OWNERSHIP | **RED_FLAG** sev 6 | STRONG · 7 | "this license is worldwide, non-exclusive…, royalty-free…, sublicensable, and transferable" |
| discord.com/terms · ACCOUNT_TERMINATION | **RED_FLAG** sev 5 | MODERATE · 4 | "we reserve the right to suspend or terminate your account… with or without notice, at our discretion for any reason" |
| github.com/site/terms · CONTENT_OWNERSHIP | **RED_FLAG** sev 6 | MODERATE · 4 | "by making a repository public, you grant other users a nonexclusive, worldwide license to use, display, perform and reproduce… your content" |
| zoom.us/en/terms · UNILATERAL_CHANGE | **RED_FLAG** sev 4 | MODERATE · 4 | "if you continue to use the services after the effective date of the changes, then you agree to the revised terms and conditions" |
| duckduckgo.com/terms · DATA_SALE | **CLEAN** | ABSENT · 0 | none of the ten data-sale indicators anywhere in the terms |
| duckduckgo.com/terms · MANDATORY_ARBITRATION | **CLEAN** | ABSENT · 0 | no arbitration, waiver or class-action language |
| example.com · DATA_SALE | **INCONCLUSIVE** | UNREADABLE | 129 characters, not a terms document; no model call |

**Changes from the brief's list:**
- **Zoom × DATA_SALE → Zoom × UNILATERAL_CHANGE.** Zoom's terms contain none
  of the data-sale indicators (that topic is in Zoom's separate privacy
  statement), so the check failed the "clear keyword presence" test. Seeded,
  it would have been a CLEAN from silence, not the RED_FLAG the brief expected.
- **GitHub is MODERATE, not STRONG.** GitHub's licence to *itself* is
  deliberately narrow. The strong-sounding "perpetual, irrevocable" wording is
  in its *feedback* clause, which the scanner now excludes. The RED_FLAG rests
  on the worldwide licence that a public repository grants to other users. The
  bracket allowed only RED_FLAG or INCONCLUSIVE, and both runs chose RED_FLAG.

Every judged check re-derives cleanly with `verify_check`. Full read-back,
logs and transaction hashes are in [`docs/EVIDENCE.md`](docs/EVIDENCE.md);
earlier versions are in [`docs/superseded/`](docs/superseded/).

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

The offline suite (417 tests) runs the real contract against a
runtime stub whose TreeMap/DynArray reproduce the runner's semantics. It builds
every gate tier for every flag (and that the weak tier never reaches a
model), the context rules on real renders (feedback clauses, content deletion,
"you may not share an account"), **one forgery per field** of the findings vector and requires `_coherent` to
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
  refused Studio's headless browser outright (docs/PROBE.md §2), so a Reddit
  check is INCONCLUSIVE — the honest answer, not a guess. It was dropped from
  the seed for that reason.
- **Legal interpretation is subjective.** Two things bound it. The confidence
  gate keeps the model away from pages with 0–1 indicators (they're
  INCONCLUSIVE, identically, every time). The bracket limits the model to
  outcomes the evidence allows: moderate evidence gets only its own side or
  INCONCLUSIVE, and severity is never the model's call. RED_FLAG versus
  INCONCLUSIVE on a MODERATE page is still a reading. All four MODERATE and
  STRONG seed checks gave the same answer in both runs, but two runs are not a
  proof.
- **Indicators are counted, not understood.** Strength measures how many
  *kinds* of relevant language a page uses, not what it means. The context
  rules (denial cuts, anchors, exclusions) came from reading real quotes, and
  a page phrased in a way they don't anticipate can still count the wrong
  clause. The stored quote is the first thing to check, and every clause is
  in the stored excerpt.
- **Silence is CLEAN.** A page with no indicator at all is CLEAN at any
  length. If a render is cut short before the relevant section, that silence
  is wrong. The 500-character floor and the legal-marker test catch error
  pages and login walls, but not a long page that stops partway.
- **A TOS is not the whole contract.** Several services put their data
  practices in a separate privacy policy. X's and Zoom's terms both do, so a
  `DATA_SALE` check on the terms page alone answers "do the *terms* say so",
  not "does the company do it". DuckDuckGo's CLEAN means its *terms* contain
  no data-sale language. Check the privacy-policy URL too.
- **The scan is a phrase list, not a lawyer.** A clause phrased without any
  indicator phrase is invisible to it (and so can only ever be CLEAN or
  INCONCLUSIVE, never RED_FLAG). `get_vocabulary()` publishes every word so anyone can see the
  boundary.
- **Some TOS pages load via JavaScript** — `web.render(mode="text")` runs the
  page's scripts and waits 3s after load, which handled every page probed. A
  page that loads its terms later than that reads as short or not-legal, and is
  INCONCLUSIVE.
- **URLs redirect.** `www.wikipedia.org/wiki/Terms_of_Use` lands on the
  encyclopedia article *about* terms of service, not on the Wikimedia
  Foundation's terms. The contract judges the page it is given.
- **The excerpt is capped** at 24 clauses / 6,000 characters. One clause per
  indicator is taken first, so the cap never hides an indicator. The matched-clause count covers the whole page; the model reads the
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
