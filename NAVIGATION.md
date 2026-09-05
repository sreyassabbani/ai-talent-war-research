# Where to look

In the 2026-09-03 advisor meeting, roughly six minutes went to hunting for files: "where should I
look at this?", "what document should I look at?", "I might not be able to find it right now."
This page exists so that never happens again. It is a map, not a summary.

**Current result: cycle 6, published 2026-09-04 as
[data/published/disclosure_sample_134/](data/published/disclosure_sample_134/).** The earlier
cycle-5 tables in [data/published/disclosure_sample_133/](data/published/disclosure_sample_133/)
are superseded — kept as the record of what was published, not as a second opinion. Where the two
disagree, cycle 6 is the corrected one.

**If you have five minutes and want the result:** read [docs/meeting_briefing_plain_english.md](docs/meeting_briefing_plain_english.md),
Part 7.

---

## By question

| The question | Open this |
| --- | --- |
| What did we find? | [docs/meeting_briefing_plain_english.md](docs/meeting_briefing_plain_english.md) § Part 7 |
| The full write-up, with every caveat | [docs/disclosure_sample_report_c6.md](docs/disclosure_sample_report_c6.md) |
| **Which filings were searched, and over what window?** | [docs/retrieval_window_memo.md](docs/retrieval_window_memo.md) |
| How was each deal categorised? | [data/published/disclosure_sample_134/09_deal_profiles.csv](data/published/disclosure_sample_134/09_deal_profiles.csv) |
| Show me the actual SEC text behind a claim | [data/published/disclosure_sample_134/08_passage_links_sample.csv](data/published/disclosure_sample_134/08_passage_links_sample.csv) — click `source_highlight_url` |
| What is inside each of the three themes? | [docs/second_level_topics_c6.md](docs/second_level_topics_c6.md) |
| Why 134 deals and not 100 AI deals? | [docs/meeting_briefing_plain_english.md](docs/meeting_briefing_plain_english.md) § Parts 2–4 |
| What can we *not* claim? | [docs/meeting_briefing_plain_english.md](docs/meeting_briefing_plain_english.md) § Part 10 |
| **What changed between cycle 5 and cycle 6, and why?** | [docs/retrieval_window_memo.md](docs/retrieval_window_memo.md) §§ 5a–5d |
| What kind of deal was each pilot deal? | [docs/deal_architecture_codebook.md](docs/deal_architecture_codebook.md) |
| **Is the screen keeping the right passages?** | [data/published/corpus_relevance_audit_c6/](data/published/corpus_relevance_audit_c6/) — unanswered until two humans score it |

The cycle-5 write-ups, [docs/disclosure_sample_report.md](docs/disclosure_sample_report.md) and
[docs/second_level_topics.md](docs/second_level_topics.md), are kept for comparison only. Read them
next to the memo's § 5d, not on their own.

## The published tables

Everything in [data/published/disclosure_sample_134/](data/published/disclosure_sample_134/),
numbered in pipeline order. `data/derived/` is git-ignored, so these are the copies a reader can
actually check.

| File | One row is | Rows |
| --- | --- | ---: |
| `02_probe_results.csv` | a deal we asked SEC about | 1,060 |
| `04_frozen_sample.csv` | a deal we downloaded, with its outcome | 400 |
| `05_deal_ai_labels.csv` | a deal's AI and talent labels | 134 |
| `06_topic_summary.csv` | a theme, with its terms and diagnostics | 3 |
| `06_deal_topic_matrix.csv` | a deal × theme share | 402 |
| `08_passage_links_sample.csv` | a high-weight passage, with a deep link | 1,074 |
| `08_passage_links.csv.gz` | every modelled passage, with a deep link | 13,954 |
| `09_deal_profiles.csv` | **a deal, with its theme mix and dominant theme** | 134 |

`09_deal_profiles.csv` is the one to open when the question is about deals rather than passages.

## Rebuilding

Retrieval is the only step that touches the network, and it must run first. Everything after it
is offline and deterministic.

```bash
tag-edgar run-disclosure-sample        # live: fetch filings from SEC
bash scripts/run_disclosure_analysis.sh   # corpus, freeze, labels, topics, report
bash scripts/run_topic_subsets.sh         # second-level topics inside each theme
bash scripts/publish_cycle6.sh            # all three publish steps, paths set in one place
```

Publish through `scripts/publish_cycle6.sh`, not by calling the three publish scripts by hand.
Every one of them defaults to cycle-5 paths, and a caller who passes some paths and lets the rest
default gets no error — just a report carrying the previous cycle's numbers under this cycle's
heading. That happened twice on 2026-09-04. See § 5d of the memo.

## Two numbers that look like a contradiction

They are not, and both are correct:

- **13,954 passages / 134 deals** — the frozen sample the report describes.
- **16,173 passages / 238 deals** — the wider retrieved corpus the model was fitted on.

`06_topic_summary.csv` counts over the second; the report headline quotes the first. See
[docs/retrieval_window_memo.md](docs/retrieval_window_memo.md) § 5.

## Standing limits

These hold for every file above and do not go away when a number looks strong.

- These are **disclosed contract terms and announcements, not outcomes**. Nothing here shows that
  any employee stayed, left, or was paid.
- The sample is selected on **whether a buyer filed with the SEC**. Private, PE, and foreign
  buyers cannot appear. That is a property of the public record, not a bug to fix.
- The **150-passage relevance audit has not been read by a human**. Until two reviewers score it,
  nothing here is a validated finding. This is the single largest open item, and it is unchanged
  by the cycle-6 rebuild. The packet is published and readable at
  [data/published/corpus_relevance_audit_c6/](data/published/corpus_relevance_audit_c6/), built on
  the cycle-6 corpus, so it scores the text that is actually reported above. Aarav and Sreyas each
  need to fill in their **own complete copy** — not half each — so that inter-rater agreement can
  be measured. A cycle-4 audit scored 72% against a 90% bar.
- **Stability is not importance.** Theme 1's sub-split is reproducible (0.959 recovery) while
  carrying the lowest coherence anywhere in the study (0.116). A split that reproduces is telling
  you the language is templated, not that it is interesting. "3 of 3 pass" is a statement about
  reproducibility and nothing more.
- **Second-level themes inherit every limit above from their parent.**

### The three corpus defects: fixed in 134, still present in 133

The cycle-5 tables were built on a corpus with three defects. All three are **fixed** in
`disclosure_sample_134/` and all three are **still present** in `disclosure_sample_133/`, which is
why that directory is superseded rather than merely older.

| Defect | What it did | Cycle 5 | Cycle 6 |
| --- | --- | --- | --- |
| The page's running header counted as passage text | The relevance screen discarded any passage whose page printed "table of contents", dropping real provisions as index entries | 6,855 passages excluded as navigation fragments | **331** — 1,266 passage texts readmitted |
| Headings were fed to the model as features | "table", "contents" and "table contents" were top-ten distinguishing terms of Theme 1 | 9,717 structural-heading tokens in `model_text` | **9** |
| A clause was modelled once per rendition when the exhibit and the S-4 or proxy reprinting it disagreed about its heading | Double-counted rows, worst in Bally's / Bet.Works, System1 / Protected.Net, Ginkgo / Baktus | 1,017 within-deal duplicate rows, 968 affected rows (7.0%) | **0** |

**The themes survived the fix.** k=3 in both cycles, the same three identities by their terms, all
clearing the 0.80 stability bar, and the dominant theme unchanged for all 133 deals present in
both cycles. What moved is inside the themes: 1,955 passages migrated from Theme 1 to Theme 2 once
the header stopped misfiling benefit-plan text into the executive theme.

### One cycle-5 recommendation is withdrawn

The cycle-5 report recommended **excluding EX-99 press releases**, because dropping 622 of them
took Theme 1 from 1 of 3 sub-themes passing to 3 of 3. In cycle 6, Theme 1 passes **3 of 3 with
press releases and 2 of 3 without**. The header fix had been doing what the EX-99 exclusion
appeared to do. That recommendation is superseded; the question is genuinely open again.

### A fourth defect, in the reporting rather than the corpus

Three further defects were found on 2026-09-04 in the scripts that *write* the reports, not in the
corpus they describe — a report built from a cycle-6 corpus and a cycle-5 sample; descriptors
asserting two things cycle 6 measured to be false; and a second-level report that keyed its
readings by sub-topic **number**, which is not stable across fits, and so described the
67.4%-failing component as "the most coherent and the most stable of the three". All are fixed
(commits `d313aaf`, `721de70`, `47fb726`) and written up in § 5d.

All six defects shared one shape: **nothing failed, and wrong numbers printed under a
correct-looking heading.** None was caught by a test. Every one was caught by checking a number
against another number that should have agreed with it. When two numbers in one document disagree,
chase it.

One consequence: `docs/second_level_topics.md` (cycle 5) can no longer be regenerated
byte-identically, because deduplication renumbered the passage ids its exemplars referred to. It is
left as committed, as the superseded record.

Match themes and sub-themes **by their terms, never by their topic number**. `topic_N` is not a
stable identity across fits: the strongest result in the study kept all ten of its top terms across
the rebuild while its number changed from `topic_3` to `topic_2`.
