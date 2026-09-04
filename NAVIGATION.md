# Where to look

In the 2026-09-03 advisor meeting, roughly six minutes went to hunting for files: "where should I
look at this?", "what document should I look at?", "I might not be able to find it right now."
This page exists so that never happens again. It is a map, not a summary.

**If you have five minutes and want the result:** read [docs/meeting_briefing_plain_english.md](docs/meeting_briefing_plain_english.md),
Part 7.

---

## By question

| The question | Open this |
| --- | --- |
| What did we find? | [docs/meeting_briefing_plain_english.md](docs/meeting_briefing_plain_english.md) § Part 7 |
| The full write-up, with every caveat | [docs/disclosure_sample_report.md](docs/disclosure_sample_report.md) |
| **Which filings were searched, and over what window?** | [docs/retrieval_window_memo.md](docs/retrieval_window_memo.md) |
| How was each deal categorised? | [data/published/disclosure_sample_133/09_deal_profiles.csv](data/published/disclosure_sample_133/09_deal_profiles.csv) |
| Show me the actual SEC text behind a claim | [data/published/disclosure_sample_133/08_passage_links_sample.csv](data/published/disclosure_sample_133/08_passage_links_sample.csv) — click `source_highlight_url` |
| What is inside each of the three themes? | [docs/second_level_topics.md](docs/second_level_topics.md) |
| Why 133 deals and not 100 AI deals? | [docs/meeting_briefing_plain_english.md](docs/meeting_briefing_plain_english.md) § Parts 2–4 |
| What can we *not* claim? | [docs/meeting_briefing_plain_english.md](docs/meeting_briefing_plain_english.md) § Part 10 |
| **Is anything counted twice?** | [docs/retrieval_window_memo.md](docs/retrieval_window_memo.md) §§ 5a–5b — yes, 7.0%, and why |
| What kind of deal was each pilot deal? | [docs/deal_architecture_codebook.md](docs/deal_architecture_codebook.md) |
| **Is the screen keeping the right passages?** | [data/published/corpus_relevance_audit_c6/](data/published/corpus_relevance_audit_c6/) — unanswered until two humans score it |

## The published tables

Everything in [data/published/disclosure_sample_133/](data/published/disclosure_sample_133/),
numbered in pipeline order. `data/derived/` is git-ignored, so these are the copies a reader can
actually check.

| File | One row is | Rows |
| --- | --- | ---: |
| `02_probe_results.csv` | a deal we asked SEC about | 1,060 |
| `04_frozen_sample.csv` | a deal we downloaded, with its outcome | 400 |
| `05_deal_ai_labels.csv` | a deal's AI and talent labels | 133 |
| `06_topic_summary.csv` | a theme, with its terms and diagnostics | 3 |
| `06_deal_topic_matrix.csv` | a deal × theme share | 399 |
| `08_passage_links_sample.csv` | a high-weight passage, with a deep link | 1,107 |
| `08_passage_links.csv.gz` | every modelled passage, with a deep link | 13,817 |
| `09_deal_profiles.csv` | **a deal, with its theme mix and dominant theme** | 133 |

`09_deal_profiles.csv` is the one to open when the question is about deals rather than passages.

## Rebuilding

Retrieval is the only step that touches the network, and it must run first. Everything after it
is offline and deterministic.

```bash
tag-edgar run-disclosure-sample        # live: fetch filings from SEC
bash scripts/run_disclosure_analysis.sh   # corpus, freeze, labels, topics, report
bash scripts/run_topic_subsets.sh         # second-level topics inside each theme
python scripts/publish_disclosure_snapshot.py
python scripts/publish_passage_links.py
python scripts/build_deal_profiles.py
```

## Two numbers that look like a contradiction

They are not, and both are correct:

- **13,817 passages / 133 deals** — the frozen sample the report describes.
- **16,079 passages / 235 deals** — the wider retrieved corpus the model was fitted on.

`06_topic_summary.csv` counts over the second; the report headline quotes the first. See
[docs/retrieval_window_memo.md](docs/retrieval_window_memo.md) § 5.

## Standing limits

These hold for every file above and do not go away when a number looks strong.

- These are **disclosed contract terms and announcements, not outcomes**. Nothing here shows that
  any employee stayed, left, or was paid.
- The sample is selected on **whether a buyer filed with the SEC**. Private, PE, and foreign
  buyers cannot appear. That is a property of the public record, not a bug to fix.
- The **150-passage relevance audit has not been read by a human**. Until two reviewers score it,
  nothing here is a validated finding. The packet is now published and readable at
  [data/published/corpus_relevance_audit_c6/](data/published/corpus_relevance_audit_c6/); it is
  built on the cycle-6 corpus, so it scores the text that will actually be reported rather than
  the superseded corpus these tables came from. Earlier packets were written only into the
  git-ignored `data/derived/`, which is why no second reader ever saw one.
- **Some passages are counted twice.** In the corpus these tables were built from, a clause filed
  as an exhibit and reprinted inside the S-4 or proxy that carries it was modelled once per
  rendition whenever the two disagreed about its heading — 968 rows, 7.0% of the sample. Three
  deals are affected badly enough that their rows in `09_deal_profiles.csv` should not be read at
  face value: Bally's / Bet.Works (32.0%), System1 / Protected.Net (30.3%), Ginkgo / Baktus
  (20.8%). Fixed in the code, not yet in these tables — see
  [docs/retrieval_window_memo.md](docs/retrieval_window_memo.md) §§ 5a–5b.
- **And 6,855 passages were wrongly thrown away.** The relevance screen discarded anything whose
  text contained "table of contents" — and the page's running header was part of that text, so
  real provisions printed beneath it were dropped as index entries. Rebuilding without the header
  readmits **1,266 passage texts**: indemnification survival, RSU award schedules, vesting terms,
  double-trigger benefit continuation. The published tables were built without them. This is the
  largest of the three defects and the one most likely to change a reading — see
  [docs/retrieval_window_memo.md](docs/retrieval_window_memo.md) § 5c.
- Second-level themes inherit every one of these limits from their parent.
