# The experiment behind the defaults

filegate came out of a weekend experiment: can a cheap, self-hosted classifier
decide which files an LLM security scanner needs to read? Everything here was
measured on **public data only**.

## Setup

- **Labels:** the 298 true-positive findings in [SastBench](https://arxiv.org/abs/2601.02941)
  (real CVEs, fix commits on GitHub), 148 repos, each scanned at its vulnerable
  commit: about 295k files.
- **Scale reference:** three large polyglot monorepos, grafana/grafana,
  getsentry/sentry and PostHog/posthog at their October 2026 HEADs, about 101k files.
  No labels; these measure the share of the bill each policy removes.
- **Cost:** one Opus 4.8 call per file ($5 / $25 per million input/output
  tokens), with 3k overhead tokens and 1k output tokens assumed. Absolute dollars
  depend on those assumptions; percentages are the result.
- **Metric:** findings caught. A finding counts as caught if any of its files is
  scanned in full.

## Where the money and the findings are

| file type | share of monorepo bill | flagged files in labelled set |
|---|---|---|
| JS/TS (frontend + Node) | 29.6% | 43 |
| backend code | 27.6% | 201 |
| tests | 23.5% | 42 |
| config/data | 8.1% | 7 |
| docs/license | 4.3% | 1 (label noise) |
| CI/infra | 1.0% | 6 |
| stylesheets | 0.4% | 0 |
| protobuf/schemas | ~0% | 0 |

- 289 of 298 findings are caught by production code, templates and CI alone.
- 8 findings depend on the test/config decision, and 24 on production JS/TS.
- Skipping file *types* (CSS, protobufs, docs) is safe but worth only a few
  percent. The money is in code, and only a per-file judgement can take it.

## Results ($ off the monorepo bill, on top of glob excludes)

**Tests + config/data** (8 dependent findings):

| approach | keep all 8 | allow 1 miss |
|---|---|---|
| content-signal regex | 1% | 8% |
| OpenDecider-Nano, generic "could this be vulnerable?" | 6% | 9% |
| **OpenDecider-Nano, narrow fact questions** | **10%** | 13% |
| **trained head** (out-of-fold, grouped by repo) | 8% | **27%** |

**Production JS/TS** (24 dependent findings):

| approach | keep all 24 | allow 1 miss | allow 4 |
|---|---|---|---|
| regex of the narrow facts | 0% | — | 16% |
| **Nano, narrow facts, UI-only discount** | **7%** | 12% | 18% |
| **trained head** | 0% | **16%** | 19% |

**Combined:** about **17%** of the bill at ~99.7% of findings (Nano facts);
about **43%** at ~99% (trained head); rules only, 1–4% at ~99%.

## What we learned

1. **Ask about facts, not risk.** Generic "is this risky?" questions to small
   Jev-style decision models score near chance on code (AUROC 0.45–0.63).
   Narrow facts about what's visible ("does it set innerHTML?", "does it define
   hooks that run?") did better in every group.
2. **Labels beat zero-shot once you tolerate a miss or two.** The trained head
   learns what your scanner actually flags.
3. **Per-file labels mislead.** CVE fixes touch tests that exercise the
   vulnerable code; counted per file, tests looked as risky as production code.
   Counted per finding, almost all of that disappears.
4. **Compute is not the constraint.** All arms run on CPU at about $0.0001 per
   file against about $0.04 per frontier-model call.

## How far to trust it

- The model decisions rest on **8 + 24 findings**. One finding is ±12 points
  (tests/config) or ±4 points (JS/TS) of that group's recall. The *ordering* of
  approaches was consistent; the exact percentages are not reliable.
- The labelled JS/TS is mostly library and server code; the savings come from
  monorepo frontend code. Risk and savings are measured on different
  populations.
- One regex variant was written after looking at the misses (in-sample). It's
  excluded from the tables above.
- **Not measured yet:** routing low-risk files to a cheaper model (`cheap`, the
  default) instead of skipping them. It should lower the cost of a miss sharply,
  but there are no numbers for it.

Run `filegate eval` on your own labels ([LABELS.md](LABELS.md)) before trusting
any threshold. [bench/](../bench/README.md) reproduces the public numbers.
