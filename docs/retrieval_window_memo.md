# What counts as a filing for a deal: the retrieval window and the eligibility rules

Prepared 2026-09-03, after the advisor meeting the same day.

Dr. Singh asked one question five separate times in that meeting and did not get a complete
answer: **where does each passage come from, and what window around the deal was searched?** His
concern was specific and correct:

> "If it is all the filings, then the problem is that maybe the acquirer is talking a lot more
> about AI in its own 10-Ks ... before even the acquisition."

The answer given live was "there wasn't a window ... it was just all documents." **That answer was
wrong.** There is an explicit window, it is enforced in code, and a second relevance filter runs
after it. This memo states both rules and then shows what they actually admitted.

---

## 1. The window rule

Implemented in [`src/tag_edgar/windows.py`](../src/tag_edgar/windows.py), one function, no
alternate paths:

| Case | Window start | Window end | Status recorded |
| --- | --- | --- | --- |
| Closing date known | announcement − 30 days | closing + 30 days | `closing_observed` |
| Closing date missing | announcement − 30 days | announcement + 365 days | `closing_missing` |
| Closing date before announcement (bad data) | announcement − 30 days | announcement + 365 days | `invalid_effective_date` |

Three things follow, and all three are checkable against the tables below.

- **Nothing older than 30 days before announcement can enter the corpus.** This is the direct
  answer to the 10-K worry. A routine annual report filed months before the deal is outside the
  window by construction.
- **The 30-day pre-announcement lookback is deliberate, not slack.** Deals leak, and the 8-K or
  agreement that carries the employee terms is sometimes filed days before the announcement date
  the vendor database records. Thirty days is short enough that no annual reporting cycle fits
  inside it.
- **The 365-day fallback applies only when closing is unobserved.** It is a bound on ignorance,
  not the normal case. Where closing is known, the window ends 30 days after it.

## 2. The second filter, which is not a date filter

Passing the date window is necessary, not sufficient. Every document inside the window is then
tested for whether it is about *this transaction*, using target-name proximity and transaction
language. For the 133 modelled deals:

| Eligibility decision | Documents |
| --- | ---: |
| Included | 1,965 |
| Excluded — unrelated document inside the event window | 911 |
| Excluded — non-transaction exhibit on a transaction 8-K | 135 |
| **Total assessed** | **3,011** |

**35% of documents that passed the date window were still rejected.** A filing being made during
the deal window does not make it a deal document, and the pipeline already acts on that.

## 3. What the rules actually admitted

464 filings across the 133 deals contributed at least one included passage. Their filing dates,
relative to the announcement date:

| Position relative to announcement | Filings | Share |
| --- | ---: | ---: |
| Before the window start (< −30 days) | **0** | **0.0%** |
| Pre-announcement lookback (−30 to −1 days) | 33 | 7.1% |
| Announcement month (0 to +30 days) | 210 | 45.3% |
| +31 to +180 days | 174 | 37.5% |
| +181 to +365 days | 37 | 8.0% |
| Beyond +365 days (closing observed, window ran to closing + 30) | 10 | 2.2% |
| Filing date unknown | **0** | **0.0%** |

Distribution: minimum **−30 days**, 5th percentile −10, **median +28 days**, 95th percentile +258,
maximum +475.

**The minimum is exactly −30.** The window bound is binding, not decorative. And 93% of
contributing filings are dated on or after the announcement.

## 4. Which forms the passages came from

13,817 included passages in the modelled sample, by the SEC form they were filed under:

| Filing form | Passages | Share |
| --- | ---: | ---: |
| 8-K (and 8-K/A) | 7,650 | 55.4% |
| 424B3 prospectus | 2,403 | 17.4% |
| S-4 / S-4/A registration | 3,104 | 22.5% |
| DEFM14A / PREM14A merger proxy | 592 | 4.3% |
| SC TO-T / SC TO-I tender offer | 68 | 0.5% |
| **10-K** | **0** | **0.0%** |
| **10-Q** | **0** | **0.0%** |

**No annual or quarterly report contributed a single passage.** Every form in the corpus is a
transaction filing — the deal announcement, its exhibits, the registration statement for the
shares issued, or the proxy soliciting the vote. The scenario Dr. Singh raised is not merely
unlikely in this corpus; it does not occur.

By exhibit, the largest sources are the merger agreement itself (EX-2.1, 4,298 passages, 31.1%)
and employment or plan exhibits (EX-10.x, roughly 2,000). Press releases (EX-99.1) are 420
passages, 3.0%.

## 5. Two things the report should say more carefully

Writing this memo surfaced two places where our own numbers are easy to misread. Neither is an
error in the model; both are reporting ambiguities that should be fixed before the next meeting.

**The passage counts and the deal counts come from different populations.** The model is fitted on
every included passage in the retrieved corpus — 16,079 passages across 235 deals. The *sample* is
the 133 frozen deals, holding 13,817 of those passages. So `topic_summary.csv` reporting "topic_1:
5,741 passages, 227 deals" is counting across the wider retrieved corpus, while the report's
headline "133 deals" is the frozen sample. In the meeting Dr. Singh asked "these are 5,741
passages across 100 deals, right?" and the answer given was yes. The accurate answer is that the
5,741 figure spans 227 retrieved deals, of which 133 are in the modelled sample.

**"13,817 passages" and "16,079 passages" both appear in our materials** and mean different things:
the first is the frozen sample, the second is the fit universe. They should be labelled wherever
they appear.

## 5a. A duplication the deduplicator does not catch

Checking the corpus while writing this memo turned up a real defect, small in aggregate and
concentrated in a few deals.

> **Revised 2026-09-03, later the same day.** The first version of this section named the wrong
> mechanism, reported the wrong count, and proposed a fix that would not have worked. It is
> corrected below, and the corrected diagnosis is what cycle 6 acts on. The original text is in
> the commit history. Everything in this section describes the **pre-fix** corpus that
> `data/published/disclosure_sample_133/` was built from; the code no longer behaves this way.

**What the deduplicator actually does.** The key is a SHA-256 of the passage's heading and text
together, normalised for whitespace and Unicode form, and it is applied across every document in
the corpus at once — not within a document family, and not within a deal. Under that key there
are **zero** within-deal repeats. The deduplicator does exactly what it was written to do. The
earlier claim that the key "does not span a deal's preliminary and definitive filings" was wrong.

**The heading is what leaks.** A clause filed as a standalone exhibit carries its real section
heading. The same clause reprinted inside the S-4, S-4/A, 424B3 or proxy that incorporates it
frequently sits under a running-header artefact instead — `Table of Contents`, a page number, an
annex letter. Same paragraph, two headings, two hashes, two modelled rows. Of the 968 excess rows
in the 133-deal sample, **968 differ only in their heading**. There is not one case of the same
heading appearing in two filings, which is the case the original diagnosis described.

| | |
| --- | ---: |
| Excess rows, 133 modelled deals | **968** of 13,817 (7.0%) |
| Excess rows, 235 retrieved deals | 1,017 of 16,079 (6.3%) |
| Excess rows where only the heading differs | 968 of 968 (100%) |
| Deals with no duplicated text | 97 of 133 |
| Median per-deal duplication rate | 0.0% |
| Mean per-deal duplication rate | 2.5% |
| Deals above 20% | 3 |
| Worst deal (Bally's / Bet.Works, PREM14A + DEFM14A) | 32.0% |

The count previously given here, 1,166, does not reproduce under any duplicate definition
tested. **968** is the figure consistent with every per-deal statistic in the table, all of which
were correct as published.

Why it matters and how much: a deal whose agreement is reprinted inside its own proxy contributes
that employee language twice, which inflates that deal's weight in its own topic shares. It
affects the fitted model far less, because the fit universe is a bounded, balanced sample rather
than the raw passage pool. **The three worst-affected deals should not be read at face value in
`09_deal_profiles.csv`** — Bally's / Bet.Works (32.0%, PREM14A reprinted as DEFM14A), System1 /
Protected.Net (30.3%, mostly S-4/A), Ginkgo / Baktus (20.8%, 424B3 reprinting the S-4).

**The fix originally proposed would not have fixed it.** "Hash on normalised text within a deal"
leaves the heading inside the string being normalised, so the two renditions still hash apart. It
removes 238 rows, 1.7%, and leaves 730 of the 968 in place. The fix that works is to drop the
heading from the key and hash the passage text alone. Numbers are *not* normalised away in that
key: two retention clauses differing only in a dollar amount are different provisions and must
stay separate rows.

## 5b. A second defect, found in the same check: headings are model features

The heading does not only enter the deduplication key. It is prepended to the passage before
`model_text` is built, so every heading is fed to the topic model as text. In the 133-deal
sample:

| | |
| --- | ---: |
| Passages whose heading is `Table of Contents` | 2,254 of 13,817 (16.3%) |
| Passages with a structural heading of any kind | 2,831 (20.5%) |
| Passages with no heading at all | 439 (3.2%) |
| Heading tokens fed to the model | 54,584 of 1,626,898 (3.4%) |
| Of those, structural furniture | 7,827 |

This was not noticed before because a heading looks like content. It is a smaller distortion than
the duplication — 0.5% of the modelled token stream is furniture — but it is the same root cause,
and repairing one without the other would have meant refitting twice.

Both are fixed together in cycle 6: structural headings are suppressed before the text reaches
the model, real section headings are kept as features, and the surviving row of a duplicate group
is chosen to be the one carrying a real heading rather than the artefact, so it can still be
found in its filing.

## 6. What this memo does not establish

- That the window is the *right* window. It is a defensible and now fully documented choice; a
  six-month symmetric window is equally defensible and would produce a different corpus. Nothing
  here tests sensitivity to that choice.
- That the relevance filter is accurate. It rejected 35% of in-window documents, and no human has
  checked a sample of those rejections. That is the audit still outstanding.
- Anything about employee outcomes. Every table above describes which documents were read, not
  what happened to anybody.
