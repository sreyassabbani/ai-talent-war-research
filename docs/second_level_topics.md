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
| `topic_1` | 1442 | shares, amount, purchase, stock, employee, common, consideration, cash | 0.098 | 77.0% | **no** |
| `topic_2` | 1975 | stock, restricted, restricted stock, plan, units, stock units, incentive, awards | 0.178 | 82.8% | yes |
| `topic_3` | 1159 | effective time, effective, time, prior effective, immediately prior, immediately, prior, rsu | 0.469 | 98.3% | yes |

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

In the parent model this theme covers **5741 passages** (35.7% of the modelled corpus), and Dr. Singh read it as the language aimed at **C-suite**.

Modelling those passages alone produced **3 sub-themes**:

| Sub-theme | Passages | Defining terms | Coherence | Stability | Survives? |
| --- | ---: | --- | ---: | ---: | --- |
| `topic_1` | 2068 | expenses, costs, tax, taxes, related, fees, payroll, transaction | 0.256 | 79.7% | **no** |
| `topic_2` | 3159 | executive, officer, directors, board, chief, executive officer, officers, chief executive | 0.316 | 93.8% | yes |
| `topic_3` | 514 | labor, union, bargaining, collective bargaining, collective, employees, council, works | 0.628 | 56.4% | **no** |

**`topic_1` — Tax definitions and cost accounting.** Tax definition clauses and cost-of-sales discussion. It is drawn in by words like payroll, severance and withholding, but most of it is not employee-terms language at all. It fails the stability bar, and it is the clearest sign that parent Theme 1 was carrying material that does not belong to it.

> “ Taxes ” means all federal, state, local or non-U.S. taxes, charges, fees, duties, levies, imposts, rates or other assessments, including income, gross receipts, net worth, excise, property, sales, use, license, capital stock, transfer, franchise, payroll, withholding, social security, value-added or other taxes (inc…

> — EX-2.1, filed text

**`topic_2` — Executive roles and board governance.** Who holds which office and how the board is composed: chief executive succession, chairman restrictions, voting agreements over board seats. This is corporate governance around named executives rather than the terms of their employment, and it is the largest and most stable part of the theme.

> If for any reason the chief executive officer serving as a director ceases to serve as the chief executive officer, the parties to the Postmates voting agreement will vote their shares to (i) remove the former chief executive officer from the Postmates board if such person has not resigned as a member and (ii) elect t…

> — S-4, filed text

**`topic_3` — Collective bargaining and works councils.** Labour-relations representations in merger agreements: whether the target is party to a collective bargaining agreement, whether a works council represents its employees, whether a representation campaign is under way. The most coherent sub-theme anywhere in this study, and conceptually nothing to do with executives. It fails the stability bar because it is small and concentrated in the deals that happen to have unionised or European workforces.

> (b) The Company is not a party to or otherwise bound by any collective bargaining agreement, Contract or other agreement or understanding with a labor union or labor organization, nor is any such Contract or agreement presently being negotiated, nor, to the knowledge of the Company, is there, a representation campaign…

> — EX-2.1, filed text

Across the 133 deals this theme reaches, the largest sub-theme share in a deal is **57% at the median**, and **100 of 133 deals** have one sub-theme above half their weight within the theme.

**2 of 3 sub-themes fail the 80% stability bar** (`topic_1`, `topic_3`). They are reported because suppressing them would make the split look cleaner than it is, not because they are ready to carry an argument.

## Benefit plans and retirement (`topic_2`)

In the parent model this theme covers **5762 passages** (35.8% of the modelled corpus), and Dr. Singh read it as the language aimed at **rank-and-file workers**.

Modelling those passages alone produced **3 sub-themes**:

| Sub-theme | Passages | Defining terms | Coherence | Stability | Survives? |
| --- | ---: | --- | ---: | ---: | --- |
| `topic_1` | 2852 | employment, payment, tax, forth, taxes, employee, except, act | 0.090 | 89.6% | yes |
| `topic_2` | 2013 | plan, employee, benefit, continuing, plans, benefits, continuing employee, time | 0.156 | 75.3% | **no** |
| `topic_3` | 897 | erisa, plan, pension, benefit, benefit plan, code, erisa affiliate, multiemployer | 0.344 | 99.5% | yes |

**`topic_1` — Employment-law representations and warranties.** What the target promises is true about its employment position: CARES Act payroll-tax relief, labour-law registrations and permits, absence of pending employment claims, strikes and unfair-labour-practice charges. These are compliance representations to the buyer, not commitments to employees.

> (i) CARES Act . Other than as set forth in Section 2.16(i) of the Company Disclosure Letter, the Company has not sought any relief under, or taken any action in respect of, any provision of the CARES Act related to Taxes (including, but not limited to, the delaying of any payments in respect of payroll Taxes under Sec…

> — EX-2.1, filed text

**`topic_2` — Continuing-employee benefit continuity.** The actual post-closing promise to employees: waiving pre-existing condition exclusions, waiting periods and evidence-of-good-health requirements when continuing employees move onto the buyer's health and welfare plans. This is the sub-theme that answers the question Dr. Singh raised about what happens to benefits after an acquisition, and it is the one that fails the stability bar.

> (a) waive all limitations as to pre-existing conditions, exclusions, active employment requirements, waiting periods and requirements to show evidence of good health with respect to participation and coverage requirements applicable to the Continuing Employees (and their eligible dependents) under any health and welfa…

> — EX-2.1, filed text

**`topic_3` — ERISA and pension definitions.** Statutory definitions and the representations built on them: Title IV plans, multiemployer plans, ERISA affiliates, and whether the target has ever maintained or contributed to a pension plan. This is near-identical statutory language deal after deal, which is why it is the most stable sub-theme in the study at 99.5%. Explicit negative representations make up about 29% of it, close enough to its sibling sub-themes that it is not distinctively a set of denials.

> (d) No Pension Plan . None of the Company nor any ERISA Affiliate has ever maintained, established, sponsored, participated in, or contributed to, any Pension Plan subject to Part 3 of Subtitle B of Title I of ERISA, Title IV of ERISA or Section 412 of the Code.

> — EX-2.1, filed text

Across the 133 deals this theme reaches, the largest sub-theme share in a deal is **53% at the median**, and **77 of 133 deals** have one sub-theme above half their weight within the theme.

**1 of 3 sub-themes fail the 80% stability bar** (`topic_2`). They are reported because suppressing them would make the split look cleaner than it is, not because they are ready to carry an argument.

## What the three splits have in common

Read the nine sub-themes together and one pattern runs through all three parents: **what survives the stability test is the language that is templated across deals, and what fails is the language that varies with the particular workforce.**

The three most stable sub-themes are ERISA and pension definitions (99.5%), award treatment at the effective time (98.3%), and executive roles and board governance (93.8%). All three are near-boilerplate: the same statutory definitions, the same "immediately prior to the Effective Time" construction, the same governance clauses, deal after deal.

The three least stable are collective bargaining and works councils (56.4%), continuing-employee benefit continuity (75.3%), and closing payment mechanics (77.0%). These are the passages whose content depends on who the workforce actually is -- whether it is unionised, what plans it moves onto, what it gets paid at closing.

**This matters for how the numbers are read.** A high recovery rate here means a phrase recurs across deals, not that the provision is important, common, or generous. The sub-theme that speaks most directly to the question Dr. Singh raised about benefits after an acquisition -- continuing-employee benefit continuity -- is one of the least stable, and that is a fact about how much benefit terms vary between deals, not evidence that they matter less.

It also means leave-one-deal-out stability is the wrong instrument for finding the provisions that distinguish deals from one another. It rewards sameness by construction. A measure of *variation* across deals would be a better next step than a third level of clustering.

## What this does not establish

- A sub-theme is a pattern in disclosed language. It is not a category of deal, a category of employee, or an outcome for anybody.
- Sub-themes inherit every selection property of the parent sample, including that a deal only appears when its buyer filed with the SEC.
- The 150-passage relevance audit is still unread. Nothing here is a validated finding, and a filter that keeps the wrong passages would produce clean sub-themes of the wrong text.
- Second-level topic numbers are local to their parent. `topic_1` inside Theme 3 has no relationship to `topic_1` of the parent model.
