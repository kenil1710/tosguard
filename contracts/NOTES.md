# TOSGuard — design notes

The contract documents its rules where they live. This file is for the
reasoning: choices made against an alternative, and the hazards a reader will
otherwise rediscover.

## 1. What the model decides, and what it never does

GenLayer reads 10,000 words of legal text and judges whether a specific
clause exists. All flag types, severity levels and storage are deterministic.

| value | who decides | compared |
|---|---|---|
| flag type | the consumer, from a closed list of 7 | on the facts hash |
| page state, length bucket, legal-marker count, conspicuous-clause count, matched-clause count | code, from the render | exactly |
| the clause excerpt and its content hash | code (normalised, sorted) | exactly (hash) |
| evidence case and allowed outcomes | code (the bracket) | exactly |
| **outcome** | **model, inside the bracket** | **exactly** |
| severity | code: the flag's base severity, +1 for broad wording ("at any time", "perpetual"…), 0 unless RED_FLAG | exactly |
| **clarity**, **scope** | **model, inside a range at most two wide set by code** | within one bucket |
| evidence_present | code (any matched clause) | exactly |
| quote, reason, findings key | code, from the agreed values | re-derived |

Severity is not asked of the model at all (`tools/audit.py` check 31). A
consumer comparing "RED_FLAG sev 7" across two services is comparing the same
arithmetic, not two moods.

## 2. The confidence gate (v1.2.0): distinct indicators

| evidence | case | allowed | model |
|---|---|---|---|
| render failed, or < 500 normalised chars | UNREADABLE | INCONCLUSIVE | no |
| fewer than 4 of 16 legal markers | NOT_TOS | INCONCLUSIVE | no |
| no clause hits any indicator or denial | ABSENT | CLEAN | no |
| 0–1 distinct indicators | WEAK | INCONCLUSIVE | no |
| 2–4 distinct indicators | MODERATE | the side the clauses lean, or INCONCLUSIVE | yes |
| 5+ distinct indicators | STRONG | RED_FLAG / CLEAN / INCONCLUSIVE (CLEAN / INCONCLUSIVE if denials outnumber) | yes |

**Indicator families.** Each flag has the families from the v1.2.0 brief —
DATA_SALE: sell, share, third party, partner, advertiser, marketing, monetize,
personalized ads, data broker, affiliate; and so on for the other six
(`get_vocabulary()` lists them all with their phrases). Each family is spelled
as the multi-word phrases terms really use ("with third parties", "advertising
partners", "binding arbitration"). **Keyword strength is the number of
distinct families hit**: thirty clauses that each say "with third parties" are
one indicator. That is what separates a page that addresses a practice from
many angles from a page that repeats one boilerplate phrase.

**Anchor groups and exclusions.** A clause only counts for a flag if it is
*about* that flag: it must contain a word from every anchor group, and none of
the flag's exclusions.

| flag | anchor groups | exclusions |
|---|---|---|
| CONTENT_OWNERSHIP | license / licence / grant / rights to / right to use | feedback, suggestion, licences granted *to you* ("we give you", "grants you", "license to you", "you may use"…) |
| UNILATERAL_CHANGE | terms / agreement **and** modif / change / amend / revis / update | — |
| ACCOUNT_TERMINATION | account / access / service | — |

So "our perpetual calendar is available worldwide" is not a content licence,
"by sending us feedback, you grant us a perpetual, irrevocable license" is a
licence over *ideas you send*, not over what you post, and "Zoom may delete any
customer content at any time without notice if it violates this agreement" is
not a change to the terms (`TestClassify`, `TestRealRenders`).

**One-sided MODERATE bracket.** With 2–4 indicators the model may only choose
between the side the clauses lean (RED_FLAG if clauses stating the practice
are at least as many as denial clauses, else CLEAN) and INCONCLUSIVE. Moderate
evidence can never be read the opposite way round, which removes the
CLEAN ↔ RED flip entirely from that tier.

**Excerpt coverage.** The excerpt is capped (24 clauses, 6,000 chars). It is
filled with one clause per family hit *first*, so the cap can never hide an
indicator and silently change the strength the validators compare.

### What the probe changed

Before any URL was seeded, a throwaway probe rendered each candidate through a
real validator and the scanner was run over those exact bytes
(`docs/probe-report.md`). Two false positives turned up and were fixed before
deploying:

- Zoom: "used in connection **with third party** offerings" counted as data
  sharing. The singular "with third party …" forms are gone; "with third
  parties", "to third parties", "third-party advertis…/partners/data" remain.
- Zoom: "you may **not share** an account" counted as a denial of data
  sharing. Denial clauses decide the MODERATE lean, so a false denial could tip
  a page towards CLEAN. DATA_SALE denials now need the service as subject ("we
  do not share", "does not share").

The first v1.2.0 seed run (kept in `docs/superseded/v1.2.0/`) then showed two
more, by reading the *quotes* rather than the outcomes — all RED_FLAG, all
consensus-agreed, and two of them resting on the wrong clause:

- GitHub and Discord CONTENT_OWNERSHIP quoted their **feedback** clauses
  ("if you give us ideas … you grant us a perpetual, irrevocable license"),
  which also supplied the "perpetual" and "irrevocable" indicators. X's
  "**we give you** a … royalty-free license to use the software" counted too.
- Zoom UNILATERAL_CHANGE quoted "Zoom may delete any customer content, at any
  time without notice … this agreement" — content removal, not a change of
  terms.

v1.2.1 added the exclusions and the second UNILATERAL_CHANGE anchor group
above. GitHub (8 → 4 indicators) and Zoom (6 → 4) moved from STRONG to
MODERATE, where the model may only answer RED_FLAG or INCONCLUSIVE, and every
quote now comes from a clause about the flag. A RED_FLAG resting on the wrong
clause is a wrong RED_FLAG even when the page deserves one.

Zoom × DATA_SALE then has no indicator at all — Zoom's terms do not discuss
selling data (its privacy statement does) — so it failed the "clear keyword
presence" test and was replaced by Zoom × UNILATERAL_CHANGE (6 indicators).

### History

- v1.0 let the model judge any page with an explicit phrase or three topical
  clauses. Re-running the seed flipped three borderline outcomes with
  identical content hashes (docs/PROBE.md §6).
- v1.1 gated on clauses that explicitly state or deny the practice (≥ 3). It
  was stable, but so narrow that "we may share information with advertising
  partners" was not evidence, and most seed checks were INCONCLUSIVE.
- v1.2.0 counts distinct indicator families and adds the one-sided MODERATE
  tier.
- v1.2.1 adds anchor groups and exclusions after the first v1.2.0 run quoted
  feedback and content-deletion clauses as evidence.

## 3. Denials are cut clause-wide

"DuckDuckGo does not share personal information with advertisers" contains the
explicit phrase "with advertisers". Cutting only the denial words ("does not
share") would leave that phrase behind to read as an explicit sale, which is
what the first draft did (caught by `TestClassify`). A denial now removes the
rest of its clause, up to the next comma, semicolon, colon or contrast word
("but", "however", "except", "although", "unless"), so "We do not sell your
data, but we share it with third parties" still reads as explicit.

## 4. Canonical text, not raw text (the Google Play shuffle lesson)

AppAudit's first live judgment went UNDETERMINED because Google Play renders
its entries in a different order every time (appaudit docs/PROBE.md §3). No raw
text is hashed here. Each sentence is normalised (unified quotes, dashes and
spaces, lower case, collapsed whitespace), only the sentences that match the
flag are kept, and the set is de-duplicated and SORTED before it is hashed.

This also absorbs the noise on real TOS pages: the Wikipedia render carries a
date-specific donation banner, and X's page carries the current and the
upcoming version of its terms side by side. Neither changes the hash unless a
relevant clause changes.

## 5. The content hash pins what was read

TOS pages are mutable. `content_hash = fnv(url | flag | excerpt | rubric)` is
compared exactly, so five validators agreeing on it is what "they read the
same terms" means. If a provider edits its terms between two validators'
fetches, the hashes differ, nothing is stored, and `judge_check` runs again.
A provider that rewrites its terms later is not "corrected" in place: a
finished check is frozen, and a new check records a new hash beside the old.

The excerpt itself (≤ 24 clauses, ≤ 6,000 chars) is stored, so
`verify_check` can rebuild every derived field — and the hash — from storage
alone, years later.

## 6. Why clarity and scope are tolerated but outcome is not

Two honest readers of one clause can differ by one on "how clearly written".
They cannot differ on whether it is there. Every clarity/scope range is at
most two wide, so a one-bucket tolerance can never refuse two validators who
agree on the outcome (the AppAudit NOTES §2 argument). The leader's pick within
the range is what is stored; it cannot leave the range because `_coherent`
refuses the payload first.

## 7. No money, but a ledger anyway

There is no fee and no stake: this is a public good, not a dispute. No method
is payable. But a revert rolls back storage and not value, so if a runner ever
let value through to a write, it must still have an owner and a way out.
`_bank` (first statement of every write) books it to the sender, `_refuse`
credits nothing further, and `claim_refund` pays it back. `balance_wei ==
refundable_wei` is published by `get_stats`. GrantJudge's NOTES §6 is where
this was learned.

## 8. URLs validators will render

Validators render whatever URL is stored, through a render service that sits
next to the node (Studio's is `studio-webdriver:4444`). So only `https://`
URLs on public domain names are accepted: no IP literals, ports, credentials,
single-label or internal hosts (`.local`, `.internal`, …). The fragment is
dropped and the host lower-cased so two spellings of one page share a record.

## 9. What was measured (docs/PROBE.md)

- X (`twitter.com/en/tos`) renders ~120k chars of text, both versions of its
  terms.
- **Reddit refuses the render** (`WEBPAGE_LOAD_FAILED`). A Reddit check is
  UNREADABLE → INCONCLUSIVE. That is the conservative rule working, not a bug.
- `www.wikipedia.org/wiki/Terms_of_Use` redirects to the **encyclopedia
  article "Terms of service"**, not the Wikimedia Foundation's terms. The
  scan finds clauses in it (the article quotes studies of real TOS), and the
  model is told only what it reads.
- `example.com` renders 129 characters → UNREADABLE.

## 10. Hazards inherited

- The runner header is exactly two comment lines; nothing may sit between
  line 1 and the imports.
- A nondet closure that captures `self` pickles storage; `_facts` is the one
  boundary where plain values are copied out.
- `str.replace()` is rejected by the runner; `_cut` and `_norm_chars` rebuild
  strings by hand.
- `TreeMap[key]` on a missing key raises; `get_or_insert_default` inserts.
- Studio's fee simulator re-runs the renders of a judgment; the seed uses the
  generic fee estimate for `judge_check`, which posts no transfer.
