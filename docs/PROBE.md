# PROBE — what a validator actually sees

Measured on GenLayer Studio Dev (chain 61997) with a throwaway contract,
`contracts/_render_probe.py`, which renders a URL through a real validator
(`gl.nondet.web.render(mode="text", wait_after_loaded="3s")`) and stores the
text so it can be read back (`test/probe.mjs`). The scanner in
`contracts/TOSGuard.py` was tuned against these bytes, and four of them are the
real-render fixtures in `test/fixtures/`.

Probe contract: `0xe59Dc79D302Ecc2Ff0097bD0C0319cbcE020022C` (shared with AppAudit).

| URL | rendered | tx |
|---|---|---|
| `https://twitter.com/en/tos` | 120,000 chars (probe cap; the page is longer) in 31s | `0x6054a3d0…` |
| `https://www.reddit.com/policies/user-agreement` | **WEBPAGE_LOAD_FAILED**, 0 chars, 11s | `0x25712aaa…` |
| `https://duckduckgo.com/terms` | 8,410 chars in 22s | `0x2cc5b3f3…` |
| `https://www.wikipedia.org/wiki/Terms_of_Use` | 18,642 chars in 21s | `0xbdc0b176…` |
| `https://example.com/` | 129 chars in 20s | `0x685da272…` |

## 1. X serves two versions of its terms on one page

`twitter.com/en/tos` redirects to X and renders the current terms AND the
version "that will go into effect on October 9, 2026" one after the other.
Many clauses therefore appear twice with small wording changes; the sorted,
de-duplicated excerpt keeps both variants, which is correct — both are on the
page a consumer is agreeing to.

X's terms say `you provide us with a broad, royalty-free license to make your
content available to the rest of the world` and contain a class-action and
jury-trial waiver. On data they say `we do not disclose personally-identifying
information to third parties except in accordance with our privacy policy` —
the terms defer to the privacy policy, which is a different URL.

## 2. Reddit refuses the headless render

Reddit answered the validator's browser with a load failure. There is nothing
to read, so a Reddit check is `UNREADABLE → INCONCLUSIVE` with no model call —
exactly the conservative rule, and the honest answer to "does this page say
X": we could not read it.

## 3. The Wikipedia URL is not Wikipedia's terms

`www.wikipedia.org/wiki/Terms_of_Use` redirects to the encyclopedia article
**"Terms of service"** (`(Redirected from Terms of Use)`), which describes TOS
in general and cites studies of them. The Wikimedia Foundation's actual terms
live at `foundation.wikimedia.org/wiki/Policy:Terms_of_Use`. The article
passes the legal-marker test (it is about legal terms), and the scan finds
clauses like "can suspend or stop at any time" quoted from research — so the
bracket allows every outcome and the model is left to notice it is reading
about terms, not terms.

It also carries a **date-specific donation banner** ("September 23: Wikipedia
still can't be sold"). The banner matches no flag's topic words, so it never
reaches the hash (rule 8).

## 4. DuckDuckGo's terms do not contain its no-sale promise

The 8,410 characters mention third parties seven times (third-party software,
third-party websites, advertisers in the liability clause) but never say "we
do not sell your data": that promise is in DuckDuckGo's privacy policy. The
scan finds no denial and no explicit clause, so the case is MENTIONED.

## 5. example.com

129 characters: `Example Domain … Learn more`. Below the 500-character floor →
UNREADABLE, pinned INCONCLUSIVE, no model call.

## Carried over (not re-measured)

- Studio's fee simulator re-runs a judgment's renders; `judge_check` is sent
  with the generic fee estimate (it posts no transfer).
- genlayer-js 2.0.0-rc.1 drops commas in its `readable` return rendering;
  `test/harness.mjs` repairs it and every assertion is also made on state.

## 6. Same bytes, different reading: the two seed runs

The seed ran twice, on two deployments (the first, superseded one is recorded
in `docs/superseded/`; its source differed only in the derived reason's grammar
and the choice of quote). Every page produced the **same content hash** both
times — the normalised, sorted excerpt was byte-identical across renders an
hour apart, which is rule 8 working. The outcomes were not all the same:

| page · flag | content hash | run 1 | run 2 (final) |
|---|---|---|---|
| X · DATA_SALE | `3f705e887417f1ad` | CLEAN | INCONCLUSIVE |
| DuckDuckGo · DATA_SALE | `12c08488aac7be35` | INCONCLUSIVE | CLEAN |
| wikipedia.org/wiki/Terms_of_Use · ACCOUNT_TERMINATION | `f7ae714494496803` | INCONCLUSIVE | RED_FLAG |
| X · CONTENT_OWNERSHIP | `186994a5cfd7c727` | RED_FLAG | RED_FLAG |
| X · MANDATORY_ARBITRATION | `6c42985288a51105` | RED_FLAG | RED_FLAG |
| Reddit · CONTENT_OWNERSHIP | — (unreadable) | INCONCLUSIVE | INCONCLUSIVE |
| example.com · DATA_SALE | — (unreadable) | INCONCLUSIVE | INCONCLUSIVE |

Every one of those fourteen rounds settled on its first attempt, so in each
round the validators agreed with each other. The flips are all on pages the
bracket left open (MENTIONED, or EXPLICIT on an article *about* terms): the
evidence is genuinely borderline, and which borderline reading wins depends on
the leader's model run. Where the terms are explicit (X's license and
arbitration clauses) the reading did not move. The bracket held in every case:
no run produced an outcome outside the allowed set, and the pinned cases were
identical. This is the subjectivity the README's limitations describe,
measured.

## 7. A second judge_check ran on a state that did not include the first

In the final seed, `judge_check(6)` finalized (tx `0xb7c498b9…`), the seed's
next read of `get_check(6)` still showed PENDING, and it sent a second
`judge_check(6)` 74s later (tx `0x22812b88…`). That transaction also executed
the judgment and returned `judged: true`, with the identical findings key. A
judged check refuses `judge_check` (offline `test_judged_is_frozen`; on chain,
the lifecycle's "a stalled check cannot be judged"), so the second execution
saw a state without the first. The stored record is consistent — one judge
attempt, one judgment in `get_stats` — and `verify_check(6)` passes. This is
recorded as a Studio Dev state-visibility observation, not explained further.
