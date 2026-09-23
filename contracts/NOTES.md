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

## 2. The bracket and the confidence gate

| case | meaning | allowed |
|---|---|---|
| UNREADABLE | render failed, or < 500 normalised chars | INCONCLUSIVE (pinned, no model) |
| NOT_TOS | fewer than 4 of 16 legal markers (login wall, block page, home page) | INCONCLUSIVE (pinned) |
| ABSENT | a legal document with zero topical clauses | CLEAN (pinned) |
| WEAK | topical clauses, but keyword strength 0–2 | INCONCLUSIVE (pinned) |
| DENIED | keyword strength ≥ 3, all of it denials | CLEAN / INCONCLUSIVE |
| EXPLICIT | keyword strength ≥ 3, at least one explicit clause | RED_FLAG / CLEAN / INCONCLUSIVE |

**Keyword strength** is the number of clauses that explicitly state the
practice ("royalty-free license", "binding arbitration", "sell your personal
information") plus the number that explicitly deny it ("we do not sell").
Passing topical mentions — "our partners", "third-party software", an
article's summary of other companies' terms — are not signal.

### Why the gate exists (v1.1.0)

The first two seed runs judged the same pages twice. Every content hash
matched, and three outcomes did not (docs/PROBE.md §6):

| page · flag | matched clauses | keyword strength | run 1 | run 2 |
|---|---|---|---|---|
| X · DATA_SALE | 33 | 1 (one qualified denial) | CLEAN | INCONCLUSIVE |
| DuckDuckGo · DATA_SALE | 7 | 0 | INCONCLUSIVE | CLEAN |
| wikipedia.org article · ACCOUNT_TERMINATION | 5 | 1 | INCONCLUSIVE | RED_FLAG |
| X · CONTENT_OWNERSHIP | 34 | 5 | RED_FLAG | RED_FLAG |
| X · MANDATORY_ARBITRATION | 20 | 9 | RED_FLAG | RED_FLAG |

A gate on RAW matches (1–2 → INCONCLUSIVE, 3+ → model) would not have touched
any of the three flips: they had 33, 7 and 5 matches. What separates them from
the stable pages is how many clauses actually *say* something — 0 or 1 against
5 and 9. So the gate counts signal clauses, and below 3 the answer is
INCONCLUSIVE with no model call: the same bytes always give the same answer,
because no reader is consulted. Above it, the model reads a page that states
its position several times over.

The cost is deliberate. X's terms touch data sharing thirty times without
saying "we sell your data"; DuckDuckGo's terms never state their no-sale
promise (it is in the privacy policy). Both are now INCONCLUSIVE on every run,
instead of CLEAN on some and INCONCLUSIVE on others. For a consumer, a stable
"the terms don't settle it" is worth more than a coin flip.

An ABSENT page (no topical clause at all) is CLEAN at any length. v1.0 made a
short silent page INCONCLUSIVE in case the render was truncated; the brief for
1.1.0 sets zero matches to CLEAN, and the 500-character floor and the
legal-marker test still route error pages and login walls to INCONCLUSIVE.

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
