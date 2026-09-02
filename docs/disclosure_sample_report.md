# Employee-treatment language across 133 technology acquisitions

Prepared 2026-09-02 for Dr. Manpreet Singh. Georgia Tech TAG Internship, Aarav Nagar.

## 1. What this is

133 completed technology acquisitions whose SEC filings actually contain
employee-related language, 13,817 passages drawn from those filings, and an
unsupervised model run over that text to find the themes that recur across deals.

The question behind it: when companies buy other companies, what do they put in
writing about the people they are acquiring? Not what they say publicly, and not what
happened afterwards, but what the binding documents disclose.

Two things are worth saying at the start. Finding these deals was most of the work,
because the public record is far thinner than the deal record, and the reasons are
documented in section 2. And the model's output is a description of recurring
contract language, not a finding about employees; section 11 is the boundary and it
is not decoration.

## 2. How these deals were found

Most acquisitions leave no usable employee record in EDGAR. The buyer may be private,
foreign, or a fund that never files, or the filing may exist without an employee-matters
article. Selecting deals by what the target does finds companies; selecting them by what
the buyer filed finds evidence. This sample is built the second way, and every deal that
fell out is counted below rather than quietly dropped.

| Step | Deals | What happened |
| --- | ---: | --- |
| Thomson/SDC deal catalog | 26,369 | Every transaction in the linked export |
| Acquirer not resolvable on EDGAR | −21,651 | Private, private-equity, or foreign buyers that do not file |
| Target outside the technology screen | −3,658 | Target SIC not in the 24-code digital-technology list |
| **Candidate pool** | **1,060** | SEC-registrant buyer with a technology target |
| Probed against EDGAR | 1,060 | Submissions index read for each buyer |
|   filed a transaction agreement (EX-2) | 89 | The merger or purchase agreement itself |
|   filed a merger proxy or tender offer | 81 | Employee and director interest sections |
|   filed only an announcement | 724 | Press release in the window |
|   filed nothing in the window | 166 | Dropped |
| **Queued for retrieval** | **133** | Ranked by disclosure richness |
| Retrieved and screened | 400 | Documents parsed, employee screen applied |
|   met the yield gate | 133 | ≥ 10 passages from ≥ 2 documents |
|   below the yield gate | 102 | Too little text to contribute |
|   retrieved but no employee passage | 165 | Reported, not modelled |
| **Deals in the model** | **133** | Carrying 13,817 employee passages |

Machine corroboration: for 112 deals the buyer's own
filing names the target, which confirms both the transaction and the company match from the
filer's document rather than from name similarity. That is a machine check, not human review.

## 3. The deals

133 transactions cleared the yield gate. The table lists the 40
largest by employee-passage count; the complete list is in `frozen_sample.csv`.

| # | Acquirer | Target | Announced | Value ($M) | Filing found | Passages |
| ---: | --- | --- | --- | ---: | --- | ---: |
| 1 | FiscalNote Holdings Inc | Aicel Technologies Inc | 2021-12-29 | not disclosed | proxy / tender offer | 797 |
| 2 | CF Acquisition Corp VI | Rumble Inc | 2021-12-02 | 3,150.00 | proxy / tender offer | 708 |
| 3 | ADTRAN Inc | ADVA Optical Networking SE | 2021-08-30 | 1,026.046 | agreement (EX-2) | 534 |
| 4 | System1 LLC | Protected.Net Grp Ltd | 2021-06-29 | not disclosed | proxy / tender offer | 492 |
| 5 | Ginkgo Bioworks Holdings Inc | Baktus Inc-Epidemiological | 2022-08-19 | not disclosed | proxy / tender offer | 476 |
| 6 | Take-Two Interactive Software | Zynga Inc | 2022-01-10 | 12,382.165 | agreement (EX-2) | 418 |
| 7 | Advanced Micro Devices Inc | Xilinx Inc | 2020-10-27 | 35,728.81 | proxy / tender offer | 403 |
| 8 | Entegris Inc | CMC Materials Inc | 2021-12-15 | 5,729.282 | proxy / tender offer | 314 |
| 9 | Advent Technologies Holdings | Ultracell LLC | 2021-02-18 | not disclosed | proxy / tender offer | 308 |
| 10 | Teledyne Technologies Inc | FLIR Systems Inc | 2021-01-04 | 7,500.665 | proxy / tender offer | 287 |
| 11 | Unity Software Inc | Ironsource Ltd | 2022-07-13 | 4,422.114 | proxy / tender offer | 277 |
| 12 | S&P Global Inc | IHS Markit Ltd | 2020-11-30 | 43,478.099 | proxy / tender offer | 259 |
| 13 | Analog Devices Inc | Maxim Integrated Products Inc | 2020-07-13 | 21,290.859 | proxy / tender offer | 227 |
| 14 | Teladoc Health Inc | Livongo Health Inc | 2020-08-05 | 17,539.058 | proxy / tender offer | 218 |
| 15 | EVgo Inc | Recargo Inc | 2021-07-09 | 25.00 | proxy / tender offer | 217 |
| 16 | Uber Technologies Inc | Postmates Inc | 2020-07-06 | 2,650.00 | proxy / tender offer | 214 |
| 17 | Rocket Lab USA Inc | Advanced Solutions Inc | 2021-10-12 | 45.50 | proxy / tender offer | 213 |
| 18 | ViaSat Inc | Euro Broadband Infrastructure | 2020-11-19 | not disclosed | proxy / tender offer | 208 |
| 19 | Skillsoft Corp | Ryzac Inc | 2021-12-22 | 525.00 | proxy / tender offer | 193 |
| 20 | Intuit Inc | Credit Karma Inc | 2020-02-24 | 7,100.00 | proxy / tender offer | 187 |
| 21 | Opendoor Technologies Inc | Pro.com Home Services LLC | 2021-09-07 | not disclosed | proxy / tender offer | 159 |
| 22 | Bally's Corp | Bet.Works Corp | 2020-11-18 | 139.382 | agreement (EX-2) | 147 |
| 23 | Intercontinental Exchange Inc | Engaged Trckng (Et) Index Ltd | 2022-07-21 | not disclosed | proxy / tender offer | 135 |
| 24 | Rekor System Inc | Waycare Technologies Ltd | 2021-08-19 | 60.121 | announcement | 131 |
| 25 | Lumentum Holdings Inc | NeoPhotonics Corp | 2021-11-04 | 863.571 | agreement (EX-2) | 130 |
| 26 | Emerson Electric Co | Aspen Technology Inc | 2021-10-11 | 10,864.939 | agreement (EX-2) | 121 |
| 27 | Rocket Lab USA Inc | SolAero Technologies Corp | 2021-12-13 | 80.00 | proxy / tender offer | 121 |
| 28 | Hewlett Packard Enterprise Co | Silver Peak Systems Inc | 2020-07-13 | 925.00 | agreement (EX-2) | 118 |
| 29 | Marvell Technology Inc | Innovium Inc | 2021-08-03 | 1,153.859 | proxy / tender offer | 113 |
| 30 | 8x8 Inc | Fuze Inc | 2021-12-01 | 250.00 | agreement (EX-2) | 113 |
| 31 | Clarivate PLC | ProQuest LLC | 2021-05-17 | 6,336.023 | agreement (EX-2) | 111 |
| 32 | Goldman Sachs Group Inc | Greensky Inc | 2021-09-15 | 2,239.124 | proxy / tender offer | 107 |
| 33 | MKS Instruments Inc | Photon Control Inc | 2021-05-10 | 311.903 | announcement | 102 |
| 34 | Omnicell Inc | Pharm Strategies Grp-Business | 2020-08-12 | 225.00 | agreement (EX-2) | 100 |
| 35 | Flotek Industries Inc | JP3 Measurement LLC | 2020-05-18 | 42.80 | agreement (EX-2) | 95 |
| 36 | Ouster Inc | Sense Photonics Inc | 2021-10-05 | 68.02 | proxy / tender offer | 94 |
| 37 | DocuSign Inc | Seal Software Ltd | 2020-02-27 | 188.00 | agreement (EX-2) | 93 |
| 38 | Advent Technologies Holdings | Fischer Eco Solutions GmbH | 2021-06-25 | not disclosed | proxy / tender offer | 90 |
| 39 | Stryker Corp | Vocera Communications Inc | 2022-01-06 | 2,970.467 | agreement (EX-2) | 88 |
| 40 | Moody's Corp | Risk Management Solutions Inc | 2021-08-05 | 1,978.613 | agreement (EX-2) | 86 |

A further 165 deals were retrieved and produced no employee passage at all.
They stay in the record. A filed agreement without employee language is a fact about
disclosure practice, not evidence that the transaction had no employee arrangements.

## 4. The corpus the model reads

A passage is one block of text from a transaction-linked SEC document that mentions
employees, compensation, benefits, equity, retention, severance, or employment terms.
Exact duplicates collapse to one row and near-identical legal boilerplate is grouped
into provision families, so one heavily repeated clause cannot dominate the model.

| Measure | Count |
| --- | ---: |
| Documents parsed | 6,156 |
| Transaction-linked documents kept | 2,862 |
| Documents excluded as unrelated to the deal | 3,294 |
| Candidate passages screened | 42,235 |
| Passages included | 16,079 |
| Passages excluded | 26,156 |
| Provision families | 34,295 |
| Largest single deal's share of modelled passages | 5.8% |

The screen rejects far more than it keeps, and deliberately so: navigation fragments,
accounting context, safe-harbour boilerplate, and bare captions all mention employees
without saying anything about how they are treated. Every rejection reason is counted
in `corpus_manifest.json`.

Where the text comes from:

| Filing type | Passages | Share |
| --- | ---: | ---: |
| EX-2.1 | 4,821 | 30.0% |
| 424B3 | 3,475 | 21.6% |
| EX-10.1 | 1,944 | 12.1% |
| S-4/A | 1,360 | 8.5% |
| S-4 | 1,286 | 8.0% |
| EX-99.1 | 678 | 4.2% |
| DEFM14A | 471 | 2.9% |
| 8-K | 360 | 2.2% |

## 5. What the unsupervised model found

The model is given no categories. It reads word and two-word patterns across the
passages, factorises them into a fixed number of components, and gives every passage a
weight on each. The names below were written after reading the top terms and the
highest-weighted passages of each component. They are descriptions of what the model
grouped, not labels it was taught, and they remain provisional until two reviewers score
them independently.

The model is fitted on the 133 deals of the frozen sample. Its assignments are
then projected onto every passage in the corpus, including deals that fell below the yield
gate, which is why a component's passage count spans more deals than the sample itself.
The deal counts below are for the frozen sample.

### Executive and officer language

**Defining words:** executive, officer, chief, employment, executive officer, chief executive, directors, employees, board, officers

**Reading (provisional):** References to executives, officers, directors and the board. This component mixes two things rather than one: contractual executive-employment and change-in-control terms, and the officer or director language that appears in proxies and announcement press releases, including quoted remarks by a chief executive. Its internal coherence is the lowest of the three, which is what a mixed component looks like. It should not be read as a single kind of employee provision.

| Measure | Value |
| --- | ---: |
| Passages where this is the strongest theme | 5,741 |
| Distinct provision families | 4,947 |
| Deals in the sample carrying it | 133 of 133 |
| Internal coherence | 0.258 |
| Leave-one-deal-out recovery | 0.864 |

Stability reading: this component reproduces when any single deal is removed.

> "We had a strong start to the year as we continue to accelerate innovation on our A.I.-driven expert platform," said Sasan Goodarzi, Intuit’s chief executive officer. "We delivered double-digit revenue growth in the quarter and are excited by the velocity of our innovation." ([source](https://www.sec.gov/Archives/edgar/data/896878/000089687820000221/fy21q1earningspressrel.htm#:~:text=%22We%20had%20a%20strong%20start%20to%20the%20year%20as%20we%20continue%20to%20accelerate%20innovation%20on%20our%20A.I.%2Ddriven%20expert%20platform%2C%22%20said%20Sasan%20Goodarzi%2C%20Intuit%E2%80%99s%20chief%20executive%20officer.%20%22We%20delivered%20double%2Ddigit%20revenue%20growth%20in%20the%20quarter%20and%20are%20excited%20by%20the%20velocity%20of%20our%20innovation.%22))

> • Visionary, Founder-Led Management Team. Our co-founder and CEO, Henry Schuck, pioneered the category of go-to-market intelligence and is the driving force behind our vision, mission, and culture. Our highly talented, customer-centric senior leadership enables us to rapidly develop new products, move more quickly than our competition, and build our fast-paced, execution-oriented culture. ([source](https://www.sec.gov/Archives/edgar/data/1794515/000162828020016838/zoominfo424b3shelf.htm#:~:text=%E2%80%A2%20Visionary%2C%20Founder%2DLed%20Management%20Team.%20Our%20co%2Dfounder%20and%20CEO%2C%20Henry%20Schuck%2C%20pioneered%20the%20category%20of%20go%2Dto%2Dmarket%20intelligence%20and%20is%20the,leadership%20enables%20us%20to%20rapidly%20develop%20new%20products%2C%20move%20more%20quickly%20than%20our%20competition%2C%20and%20build%20our%20fast%2Dpaced%2C%20execution%2Doriented%20culture.))

> “We are delighted at the prospect of welcoming the Redflex team and their customers to the Verra Mobility family,” said David Roberts, Chief Executive Officer, Verra Mobility. “We are incredibly excited for this step forward in building the Verra Mobility of the future, expanding our portfolio of safe city solutions, and solidifying our position as a global leader in smart transportation.” ([source](https://www.sec.gov/Archives/edgar/data/1682745/000156459021001806/vrrm-ex991_133.htm#:~:text=%E2%80%9CWe%20are%20delighted%20at%20the%20prospect%20of%20welcoming%20the%20Redflex%20team%20and%20their%20customers%20to%20the%20Verra%20Mobility%20family%2C%E2%80%9D%20said%20David%20Roberts%2C%20Chief,Mobility%20of%20the%20future%2C%20expanding%20our%20portfolio%20of%20safe%20city%20solutions%2C%20and%20solidifying%20our%20position%20as%20a%20global%20leader%20in%20smart%20transportation.%E2%80%9D))

### Benefit plans and ERISA

**Defining words:** plan, benefit, erisa, employee, benefit plan, code, pension, employee benefit, plans, benefit plans

**Reading (provisional):** Definitions and covenants about employee benefit plans: plan schedules, ERISA representations, pension and welfare arrangements, and undertakings about benefits after closing. This is the most self-consistent contractual component.

| Measure | Value |
| --- | ---: |
| Passages where this is the strongest theme | 5,762 |
| Distinct provision families | 5,016 |
| Deals in the sample carrying it | 129 of 133 |
| Internal coherence | 0.351 |
| Leave-one-deal-out recovery | 0.889 |

Stability reading: this component reproduces when any single deal is removed.

> “ Benefit Plans ” means the Company Benefit Plans and the ADP Benefit Plans. ([source](https://www.sec.gov/Archives/edgar/data/854775/000110465921132717/tm2131473d1_ex2-1.htm#:~:text=%E2%80%9C%20Benefit%20Plans%20%E2%80%9D%20means%20the%20Company%20Benefit%20Plans%20and%20the%20ADP%20Benefit%20Plans.))

> (v) As of the Closing Date, there are no Canadian Pension Plans. ([source](https://www.sec.gov/Archives/edgar/data/1437226/000119312520264842/d90239dex102.htm#:~:text=%28v%29%20As%20of%20the%20Closing%20Date%2C%20there%20are%20no%20Canadian%20Pension%20Plans.))

> “ Plan ” means any employee benefit plan as defined in Section 3(3) of ERISA, including any employee welfare benefit plan (as defined in Section 3(1) of ERISA), any employee pension benefit plan (as defined in Section 3(2) of ERISA), and any plan which is both an employee welfare benefit plan and an employee pension benefit plan, and in respect of which the Borrower or any ERISA Affiliate is an “employer” as defined… ([source](https://www.sec.gov/Archives/edgar/data/64040/000119312522057865/d124158dex101.htm#:~:text=%E2%80%9C%20Plan%20%E2%80%9D%20means%20any%20employee%20benefit%20plan%20as%20defined%20in%20Section%203%283%29%20of%20ERISA%2C%20including%20any%20employee%20welfare%20benefit%20plan%20%28as%20defined%20in%20Section%203%281%29,an%20employee%20pension%20benefit%20plan%2C%20and%20in%20respect%20of%20which%20the%20Borrower%20or%20any%20ERISA%20Affiliate%20is%20an%20%E2%80%9Cemployer%E2%80%9D%20as%20defined%20in%20Section%203%285%29%20of%20ERISA.))

### Equity awards at the effective time

**Defining words:** stock, shares, common, common stock, restricted, restricted stock, units, options, merger, outstanding

**Reading (provisional):** Treatment of stock, options, restricted stock and restricted stock units when the transaction closes: conversion, assumption, vesting and cash-out of outstanding awards. It is the most stable component, recovering in nearly every leave-one-deal-out fold.

| Measure | Value |
| --- | ---: |
| Passages where this is the strongest theme | 4,576 |
| Distinct provision families | 3,725 |
| Deals in the sample carrying it | 118 of 133 |
| Internal coherence | 0.432 |
| Leave-one-deal-out recovery | 0.983 |

Stability reading: this component reproduces when any single deal is removed.

> Assumed Company RSU ([source](https://www.sec.gov/Archives/edgar/data/712515/000119312521032346/d125236dex21.htm#:~:text=Assumed%20Company%20RSU))

> Assumed RSU ([source](https://www.sec.gov/Archives/edgar/data/1633978/000119312521321796/d216381dex21.htm))

> Converted Parent RSU ([source](https://www.sec.gov/Archives/edgar/data/1810806/000119312522193960/d292378dex21.htm#:~:text=Converted%20Parent%20RSU))

## 6. The AI subgroup

The earlier version of this study screened for AI first and then looked for filings.
That produced thirteen usable deals, because the companies an AI keyword finds are mostly
bought by firms that never file with the SEC. Here the label is applied afterwards, to
deals already known to have employee disclosure, which turns it into a question that can
be answered: among transactions whose employee terms are public, how many describe the
target in AI terms?

| Label | Deals |
| --- | ---: |
| Filings describe the target in explicit AI terms | 17 |
| Weaker or adjacent AI language | 0 |
| No AI language near the target's name | 116 |
| **Total in the sample** | **133** |

Team-joining language appears in 45 deals and explicit acqui-hire language in 3.

The AI-labelled deals, with the wording their own filings use:

| Acquirer | Target | Wording found |
| --- | --- | --- |
| ADTRAN Inc | ADVA Optical Networking SE | machine learning |
| CF Acquisition Corp VI | Rumble Inc | artificial intelligence |
| Certara Inc | Pinnacle 21 LLC | machine learning |
| DLH Holdings Corp | Irving Burton Associates LLC | artificial intelligence |
| DocuSign Inc | Seal Software Ltd | ai, artificial intelligence, machine learning, natural lang… |
| Hewlett Packard Enterprise Co | Silver Peak Systems Inc | ai, self-driving |
| Intercontinental Exchange Inc | Ellie Mae Inc | artificial intelligence, machine learning |
| Mitek Systems Inc | HooYu Ltd | artificial intelligence, computer vision |
| Opendoor Technologies Inc | Pro.com Home Services LLC | machine learning |
| Progress Software Corp | Chef Software Inc | machine learning |
| Quantum Computing Inc | QPhoton Inc | computer vision |
| Quantum Corp | Sq Box Sys Ltd | artificial intelligence, machine learning |
| Rekor System Inc | Waycare Technologies Ltd | ai, artificial intelligence |
| SentinelOne Inc | Attivo Networks Inc | ai-powered |
| Smith Micro Software Inc | Avast Plc-Family Safety | artificial intelligence, machine learning |
| Take-Two Interactive Software | Zynga Inc | machine learning |
| ViaSat Inc | Euro Broadband Infrastructure | artificial intelligence, machine learning |

Every label here is machine-derived and pending human review. A deal marked with no AI
language is a deal whose retrieved filings do not describe it that way; it is not a
finding that the target does no AI work.

## 7. Does the result depend on how we built it?

The bounded fit sample can be spread evenly across deals, across document families, or
not balanced at all. The primary setting was fixed before this run. Re-fitting under the
other two is the check that the components are a property of the text rather than of that
choice.

| Fit balance | Components | Recovery per component | Leading terms |
| --- | ---: | --- | --- |
| source_family (primary) | 3 | 0.86, 0.89, 0.98 | executive; plan; stock |
| deal | 3 | 0.95, 0.95, 0.95 | employment; stock; plan |
| none | 3 | 0.90, 0.94, 0.98 | executive; plan; stock |

All three settings return the same three themes in different proportions, and every
component recovers well above the 0.80 floor. The themes are not an artefact of the
balancing choice.

## 8. Tone, as a secondary diagnostic only

This counts protective and negative wording per hundred tokens and subtracts the average
for the same filing type, so deals are compared against ordinary legal language rather
than against plain English. It measures how documents are written. It is not evidence
that any buyer treated people better.

Interpretation status recorded in the manifest: `secondary_diagnostic_corpus_not_validated`.

| Deal | Protective-language residual |
| --- | ---: |
| Opendoor Technologies Inc / Commeasure Pte Ltd | +5.330 |
| Vontier Corp / DRB Systems LLC | +1.826 |
| KKR & Co Inc / Therapy Brands Holdings LLC | +1.570 |
| HealthStream Inc / myClinicalExchange LLC | +1.374 |
| Mastech Digital Inc / AmberLeaf Partners Inc | +1.060 |
| … | |
| CleanSpark Inc / P2klabs Inc | -0.877 |
| Workiva Inc / Parseport ApS | -0.888 |
| Simulations Plus Inc / Lixoft SAS | -0.893 |

Only deals in the frozen sample are named. A high residual means the filing uses more
protective wording than is typical for that filing type, and nothing more.

## 9. Which checks the model passed and failed

The pipeline runs its own checks and reports them whatever they say. Reporting only the
checks that passed would make the weak parts of this result invisible.

Automated checks: 71 passed, 0 failed, 1 warning.

| Warning | Value | What it means |
| --- | --- | --- |
| agglomerative adjusted rand | 0.03419036008 | Identical fit universe; L2 word/bigram TF-IDF; sklearn cosine metric and average linkage; ARI is permutation-invariant, so label alignment is not req… |

The agglomerative comparison deserves plain words. A second, unrelated clustering
method was run over the same passages and its groups were compared with the model's.
The agreement is low. The three components are individually stable, reproducing when
any single deal is dropped, but a different algorithm would not carve the text the
same way. Read the components as recurring language, not as the only true division
of it.

Model status recorded in the manifest: `modeled`. That word means the model ran and its own checks are recorded. It does not mean the corpus was validated by a person; section 11 says what was not done.

## 10. Reproduction

Every table above is generated from committed code and frozen artifacts:

```
tag-edgar screen-disclosure-pool data/derived/deal_catalog.csv
tag-edgar probe-disclosure data/derived/disclosure_pool/pool.csv
tag-edgar build-disclosure-queue data/derived/disclosure_probe/probe_results.csv
tag-edgar run-disclosure-sample data/derived/disclosure_review_queue.csv
tag-edgar build-employee-corpus <queue> data/derived/disclosure_runs
tag-edgar freeze-disclosure-sample <queue> <passages> data/derived/disclosure_runs
tag-edgar analyze-employee-topics <queue> <corpus>
python scripts/build_disclosure_sample_report.py
```

Selection rule `disclosure-first-v1`; corpus hash `97ea426f6900a345...`.

## 11. What this cannot show

- **The sample is selected by disclosure.** It describes acquisitions whose buyers
  file with the SEC and put the agreement on the record. Deals by private,
  private-equity, and foreign buyers are largely absent. That is a property of the
  public record, not a sampling choice that can be corrected by weighting.
- **These are contracts and proxies, not outcomes.** A clause promising benefit
  continuity is a promise. Nothing here shows whether any employee stayed, was paid
  what was promised, or was satisfied.
- **Nothing here is causal.** The clusters describe how transaction documents are
  written. They cannot say that a drafting choice caused an employee result.
- **The cluster names are provisional.** They were written after seeing the model's
  output and have not been scored by two independent reviewers.
- **Corpus relevance audit: not run for this cycle.** The screen that decides which passages
  count as employee-related has not been validated by a human on this corpus, so the
  proportion of included passages that a person would call relevant is unmeasured.
  The earlier cycle-4 audit of a different corpus scored 72% against a 90% threshold,
  so this is a real and quantified risk, not a formality.
- **Company matching is machine-confirmed.** The buyer's filing naming the target is
  strong corroboration, but no person has checked each pairing.
