# Inside the three themes: second-level topics

Generated 2026-09-03 by `scripts/build_second_level_report.py`.

Dr. Singh, 2026-09-03:

> This is the broad 3 themes ... now we need to go deeper into each of those discussions and ask, how we can differentiate within those discussions. ... Especially the Theme 3, and see what we get.

Each first-level theme was cut out of the corpus and modelled again on its own, using the same fitting pipeline and the same settings as the parent run. So every diagnostic below means what the parent model's diagnostic of the same name means.

Each sub-theme carries a plain-English **reading**, written after reading its passages rather than inferred from its term list. A reading is our interpretation. The quote beneath it is the filing's own words, pulled from the corpus at render time.

**Read the stability column before the terms.** A sub-theme whose recovery rate is below 80% did not survive the leave-one-deal-out test, and its terms are a description of this particular corpus rather than a finding that would reappear.

## Stock and equity awards (`topic_3`)

In the parent model this theme covers **4576 passages** (28.5% of the modelled corpus), and Dr. Singh read it as the language aimed at **high-skilled workers**.

Modelling those passages alone produced **3 sub-themes**:

| Sub-theme | Passages | Defining terms | Coherence | Stability | Survives? |
| --- | ---: | --- | ---: | ---: | --- |
| `topic_1` | 1442 | shares, amount, purchase, stock, employee, common, consideration, cash | 0.098 | 77% | **no** |
| `topic_2` | 1975 | stock, restricted, restricted stock, plan, units, stock units, incentive, awards | 0.178 | 83% | yes |
| `topic_3` | 1159 | effective time, effective, time, prior effective, immediately prior, immediately, prior, rsu | 0.469 | 98% | yes |

**`topic_1` — Closing payment mechanics.** Purchase-price definitions, escrow releases, flow-of-funds memoranda, and closing bonus and unit-appreciation payments routed through payroll. Much of this is transaction-consideration language that mentions employees rather than employee-terms language, which is why it is the least coherent of the three and the only one to fail the stability bar.

> (c) the amount of the Closing Bonus Payments and the UAR Payments (to be paid by the Company to the Closing Bonus Payments recipients and UAR Holders in the aggregate amounts set forth in the Flow of Funds Memorandum, no later than the first regularly scheduled payroll following the Closing);

> — EX-10.1, filed text

**`topic_2` — Standing equity plans and new grants.** The equity programme as it already exists: the incentive plan, grants made to named executives, unit counts and vesting schedules. It describes the plan rather than what the acquisition does to it.

> On January 7, 2022, the Compensation Committee (the “Committee”) of the Board of Directors (the “Board”) of Joby Aviation, Inc. (the “Company”) approved the grant of 265,604 restricted stock units (“RSUs”) under the Company’s 2021 Incentive Award Plan to Matthew Field, the Company’s Chief Financial Officer.

> — 424B3, filed text

**`topic_3` — Award treatment at the effective time.** What happens to each option and RSU at closing: assumed, converted into an acquirer award, accelerated, or cancelled for no consideration. This is the sub-theme closest to the research question, and it is both the most coherent and the most stable of the three.

> (d) Prior to the Effective Time, the Company shall take all corporate action necessary to provide that each Company Option that does not constitute an Assumed Company Option and each Company RSU that does not constitute an Assumed Company RSU Award, and in each case, which is not accelerated pursuant to Section 1.7(c)…

> — S-4, filed text

Across the 133 deals this theme reaches, the largest sub-theme share in a deal is **55% at the median**, and **84 of 133 deals** have one sub-theme above half their weight within the theme.

**1 of 3 sub-themes fail the 80% stability bar** (`topic_1`). They are reported because suppressing them would make the split look cleaner than it is, not because they are ready to carry an argument.

## Executive and officer language (`topic_1`)

Not yet fitted. Run `bash scripts/run_topic_subsets.sh`.

## Benefit plans and retirement (`topic_2`)

Not yet fitted. Run `bash scripts/run_topic_subsets.sh`.

## What this does not establish

- A sub-theme is a pattern in disclosed language. It is not a category of deal, a category of employee, or an outcome for anybody.
- Sub-themes inherit every selection property of the parent sample, including that a deal only appears when its buyer filed with the SEC.
- The 150-passage relevance audit is still unread. Nothing here is a validated finding, and a filter that keeps the wrong passages would produce clean sub-themes of the wrong text.
- Second-level topic numbers are local to their parent. `topic_1` inside Theme 3 has no relationship to `topic_1` of the parent model.
