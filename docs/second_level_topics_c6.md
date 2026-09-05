# Inside the three themes: second-level topics

Generated 2026-09-04 by `scripts/build_second_level_report.py`.

Dr. Singh, 2026-09-03:

> This is the broad 3 themes ... now we need to go deeper into each of those discussions and ask, how we can differentiate within those discussions. ... Especially the Theme 3, and see what we get.

Each first-level theme was cut out of the corpus and modelled again on its own, using the same fitting pipeline and the same settings as the parent run. So every diagnostic below means what the parent model's diagnostic of the same name means.

Each sub-theme carries a plain-English **reading**, written after reading its passages rather than inferred from its term list. A reading is our interpretation. The quote beneath it is the filing's own words, pulled from the corpus at render time.

**Read the stability column before the terms.** A sub-theme whose recovery rate is below 80% did not survive the leave-one-deal-out test, and its terms are a description of this particular corpus rather than a finding that would reappear.

## Stock and equity awards (`topic_3`)

In the parent model this theme covers **4384 passages** (27.1% of the modelled corpus), and Dr. Singh read it as the language aimed at **high-skilled workers**.

Modelling those passages alone produced **3 sub-themes**:

| Sub-theme | Passages | Defining terms | Coherence | Stability | Survives? |
| --- | ---: | --- | ---: | ---: | --- |
| `topic_1` | 2174 | shares, stock, common, common stock, units, restricted, vesting, amount | 0.125 | 81.4% | yes |
| `topic_2` | 1154 | effective time, effective, time, prior effective, immediately prior, prior, immediately, rsu | 0.464 | 97.1% | yes |
| `topic_3` | 1056 | plan, option, incentive, stock, stock option, options, incentive plan, stock options | 0.194 | 67.4% | **no** |

No plain-English reading is carried for `topic_1`, `topic_3`: these sub-themes do not match a component any earlier reading was written about, so anything said about them here would be a description of a term list rather than of passages somebody read.

**`topic_2` — Award treatment at the effective time.** What happens to each option and RSU at closing: assumed, converted into an acquirer award, accelerated, or cancelled for no consideration. This is the sub-theme closest to the research question, and it is both the most coherent and the most stable of the three. It is also the most durable result in the study: its ten defining terms are identical in cycle 5 and cycle 6, across a corpus rebuild that moved 2,359 passages between parent themes.

> At the effective time, each ironSource RSU that is outstanding and unvested immediately prior to the effective time and each ironSource RSU that is outstanding and vested immediately prior to the effective time (taking into account any acceleration of vesting as a result of the consummation of the merger) but has not…

> — 424B3, filed text

Across the 134 deals this theme reaches, the largest sub-theme share in a deal is **52% at the median**, and **74 of 134 deals** have one sub-theme above half their weight within the theme.

**1 of 3 sub-themes fail the 80% stability bar** (`topic_3`). They are reported because suppressing them would make the split look cleaner than it is, not because they are ready to carry an argument.

## Executive and officer language (`topic_1`)

In the parent model this theme covers **4100 passages** (25.4% of the modelled corpus), and Dr. Singh read it as the language aimed at **C-suite**.

Modelling those passages alone produced **3 sub-themes**:

| Sub-theme | Passages | Defining terms | Coherence | Stability | Survives? |
| --- | ---: | --- | ---: | ---: | --- |
| `topic_1` | 1466 | costs, customers, employees, acquisition, services, continue, management, growth | 0.116 | 95.9% | yes |
| `topic_2` | 1944 | executive, officer, board, employment, chief, executive officer, mr, chief executive | 0.231 | 88.0% | yes |
| `topic_3` | 690 | proxy, officers, executive officers, statement, proxy statement, directors executive, directors, information | 0.351 | 81.6% | yes |

No plain-English reading is carried for `topic_1`, `topic_3`: these sub-themes do not match a component any earlier reading was written about, so anything said about them here would be a description of a term list rather than of passages somebody read.

**`topic_2` — Executive roles and board governance.** Who holds which office and how the board is composed: chief executive succession, chairman restrictions, voting agreements over board seats. This is corporate governance around named executives rather than the terms of their employment, and it is the largest part of the theme. In cycle 5 it was also the most stable part; in cycle 6 it is not, recovering 88.0% against 95.9% for the cost-and-services sub-theme beside it.

> The agreement will provide Mr. Resnik with an annual base salary of $400,000 and a discretionary annual bonus based on Executive’s achievement of performance objectives established by the Compensation Committee of the Board of Directors, with such bonus targeted at 50% of Mr. Resnik’s annual base salary.

> — S-4/A, filed text

Across the 134 deals this theme reaches, the largest sub-theme share in a deal is **59% at the median**, and **102 of 134 deals** have one sub-theme above half their weight within the theme.

## Benefit plans and retirement (`topic_2`)

In the parent model this theme covers **7689 passages** (47.5% of the modelled corpus), and Dr. Singh read it as the language aimed at **rank-and-file workers**.

Modelling those passages alone produced **3 sub-themes**:

| Sub-theme | Passages | Defining terms | Coherence | Stability | Survives? |
| --- | ---: | --- | ---: | ---: | --- |
| `topic_1` | 3495 | payment, taxes, severance, compensation, tax, expenses, payroll, payable | 0.209 | 83.2% | yes |
| `topic_2` | 2671 | employment, employees, labor, employee, bargaining, collective, collective bargaining, knowledge | 0.272 | 54.1% | **no** |
| `topic_3` | 1523 | plan, erisa, benefit, benefit plan, pension, code, pension plan, employee benefit | 0.287 | 100.0% | yes |

No plain-English reading is carried for `topic_1`, `topic_2`: these sub-themes do not match a component any earlier reading was written about, so anything said about them here would be a description of a term list rather than of passages somebody read.

**`topic_3` — ERISA and pension definitions.** Statutory definitions and the representations built on them: Title IV plans, multiemployer plans, ERISA affiliates, and whether the target has ever maintained or contributed to a pension plan. This is near-identical statutory language deal after deal, which is why it is the most stable sub-theme in the study, recovering in every leave-one-deal-out fold in cycle 6. Cycle 5 measured explicit negative representations at about 29% of it; that has not been re-measured on this corpus and the figure is not carried forward.

> (d) No Pension Plan . None of the Company nor any ERISA Affiliate has ever maintained, established, sponsored, participated in, or contributed to, any Pension Plan subject to Part 3 of Subtitle B of Title I of ERISA, Title IV of ERISA or Section 412 of the Code.

> — EX-2.1, filed text

Across the 134 deals this theme reaches, the largest sub-theme share in a deal is **46% at the median**, and **41 of 134 deals** have one sub-theme above half their weight within the theme.

**1 of 3 sub-themes fail the 80% stability bar** (`topic_2`). They are reported because suppressing them would make the split look cleaner than it is, not because they are ready to carry an argument.

## Sensitivity: Theme 1 without press releases

Theme 1 mixes merger-agreement text with 630 EX-99 press-release passages. Refitting it with those dropped tests whether it is one theme or two document registers sharing a bucket.

| | Sub-theme (top terms) | Passages | Coherence | Stability |
| --- | --- | ---: | ---: | ---: |
| with EX-99 | `topic_1` costs, customers, employees | 1466 | 0.116 | 95.9% |
| with EX-99 | `topic_2` executive, officer, board | 1944 | 0.231 | 88.0% |
| with EX-99 | `topic_3` proxy, officers, executive officers | 690 | 0.351 | 81.6% |
| without EX-99 | `topic_1` costs, employees, expenses | 1401 | 0.149 | 92.2% |
| without EX-99 | `topic_2` officer, chief, executive officer | 1174 | 0.303 | 79.2% |
| without EX-99 | `topic_3` executive officers, officers, compensation | 895 | 0.299 | 93.5% |

**On this corpus, fewer sub-themes clear the bar without press releases.** 3 of 3 sub-themes clear the 80% bar with press releases in; 2 of 3 clear it with them out. Mean recovery moves from 88.5% to 88.3%.

The two fits are separate models, so their sub-themes are not paired and a row here cannot be read across the table as the same group before and after. What the comparison supports is whether the split as a whole holds up, not what happened to any one sub-theme.

**This is a corpus decision and it is still open.** Whether EX-99 announcements belong in the modelled corpus, or should be modelled separately from contract text, is a question about what the study is measuring rather than a setting to be tuned to whichever value scores better on this page.

## What the splits have in common

Read the nine sub-themes together and one pattern runs through all three parents: **what survives the stability test is the language that is templated across deals, and what fails is the language that varies with the particular workforce.**

The three most stable sub-themes across all parents are ERISA and pension definitions (100.0%); Award treatment at the effective time (97.1%); costs, customers, employees (95.9%).

The three least stable are employment, employees, labor (54.1%); plan, option, incentive (67.4%); shares, stock, common (81.4%).

A sub-theme without a carried reading is named by its leading terms, because naming it anything else would be inventing an interpretation to fill a table.

**This matters for how the numbers are read.** A high recovery rate here means a phrase recurs across deals, not that the provision is important, common, or generous. Where a sub-theme about what happens to a particular workforce scores low, that is a fact about how much such terms vary between deals, not evidence that they matter less.

It also means leave-one-deal-out stability is the wrong instrument for finding the provisions that distinguish deals from one another. It rewards sameness by construction. A measure of *variation* across deals would be a better next step than a third level of clustering.

## What this does not establish

- A sub-theme is a pattern in disclosed language. It is not a category of deal, a category of employee, or an outcome for anybody.
- Sub-themes inherit every selection property of the parent sample, including that a deal only appears when its buyer filed with the SEC.
- The 150-passage relevance audit is still unread. Nothing here is a validated finding, and a filter that keeps the wrong passages would produce clean sub-themes of the wrong text.
- Second-level topic numbers are local to their parent. `topic_1` inside Theme 3 has no relationship to `topic_1` of the parent model.
