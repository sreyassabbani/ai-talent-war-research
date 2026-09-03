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
| What kind of deal was each pilot deal? | [docs/deal_architecture_codebook.md](docs/deal_architecture_codebook.md) |

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
- The **150-passage relevance audit has not been read by a human**. The packet is prepared at
  `data/derived/corpus_relevance_audit_133/assessor_packet.csv`. Until two reviewers score it,
  nothing here is a validated finding.
- Second-level themes inherit every one of these limits from their parent.
