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

## 2. The bracket, and why silence is CLEAN only for a long document

| case | meaning | allowed |
|---|---|---|
| UNREADABLE | render failed, or < 500 normalised chars | INCONCLUSIVE (pinned, no model) |
| NOT_TOS | fewer than 4 of 16 legal markers (login wall, block page, home page) | INCONCLUSIVE (pinned) |
| ABSENT | a legal document with zero topical clauses | CLEAN if ≥ 6,000 chars, else INCONCLUSIVE (pinned) |
| SPARSE | one or two topical clauses, nothing explicit | CLEAN / INCONCLUSIVE |
| DENIED | a denial, and fewer than three other topical clauses | CLEAN / INCONCLUSIVE |
| MENTIONED | three or more topical clauses, none explicit | RED_FLAG / CLEAN / INCONCLUSIVE |
| EXPLICIT | at least one clause states the practice | RED_FLAG / CLEAN / INCONCLUSIVE |

A terms document that never uses any of a flag's topic words does not contain
that clause, which is a finding; but a short page may be a truncated render of
a longer document, so below the 6,000-character bucket silence is only
INCONCLUSIVE.

MENTIONED outranks DENIED on purpose. Twitter/X's terms contain "we do not
disclose personally-identifying information to third parties except in
accordance with our privacy policy" beside thirty clauses about partners and
advertising. The first version let that one qualified denial pin the outcome to
CLEAN/INCONCLUSIVE — the scan deciding a legal question, which is exactly what
the scan must not do. With three or more other topical clauses the model sees
everything and weighs the denial itself.

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
