# Employee-treatment language in technology acquisitions

## A disclosure-first study of 133 transactions, with an unsupervised model of what their filings say about people

Georgia Tech TAG Internship. Student researcher: Aarav Nagar. Research supervisor: Dr. Manpreet Singh.
Prepared 2026-09-02. Branch `aarav/aug21-pilot-completion`.

**Status: provisional.** One human quality check was not run for this cycle. Section 9 says exactly
what that means. Nothing in this report is presented as a validated finding.

---

# 1. What this study asks

- When one company buys another, **what does it put in writing about the people it is acquiring?**
- Not what it says in interviews. Not what happened afterwards. **What the binding documents disclose.**
- This is empirical corporate-finance and human-capital research. It is not stock prediction and not legal advice.

## 1.1 Why the question is answerable at all

- United States securities law forces buyers and targets to file certain documents publicly.
- Merger agreements routinely contain an **employee-matters article**: promises about pay, benefits, equity and severance after closing.
- Merger proxies contain sections on **what executives and directors receive** because of the deal.
- So there is a real, large, free corpus of text about how transactions treat employees.

## 1.2 What the question is not

- We are **not** measuring whether employees stayed. That requires employment data we do not have.
- We are **not** measuring whether employees were treated well. A promise in a contract is a promise.
- We are **not** claiming these deals represent all acquisitions. Section 9 explains why they cannot.

---

# 2. The prior approach, and exactly how it failed

The earlier version of this project selected deals by asking **"is the target an AI company?"** and then
went looking for filings. This is the natural order and it does not work.

| Step in the old approach | Result |
| --- | ---: |
| AI keyword screen over company names and descriptions | 119 candidate deals |
| Acquirer could not be found on the SEC system | **57 of 119 dropped** |
| Machine-qualified, pending human review | 35 |
| Deals that produced any employee text at all | **13** |
| Unique employee passages | **72** |
| Share of that text from a single deal | **44%** |

## 2.1 The diagnosis

- The acquirers that buy AI startups are disproportionately **private companies, private-equity funds, and foreign corporations**.
- Examples that could not be resolved: Progressive AE, Tie Industrial, LFM Capital, Siemens AG, AXA SA, BAE.
- **Entities like these do not file with the SEC.** There is no document to read, so there is no evidence, no matter how interesting the deal is.
- The screen also produced false positives, pulling in robotics and lawn-mower manufacturers on the strength of the word "autonomous".

## 2.2 The insight that changed the design

- Whether employee text exists is **almost entirely a property of the buyer, not the target.**
- The predictor is: **is the acquirer an SEC registrant that filed the transaction agreement?**
- Evidence from our own pilot, holding the target type constant:

| Deal | Target | Employee passages |
| --- | --- | ---: |
| Intuit / Mailchimp | private | **84** |
| Fastly / Glitch | private | **0** |
| Oracle / Cerner | public | **541** |
| Take-Two / Zynga | public | **607** |

- Both Mailchimp and Glitch were private targets. The difference is entirely on the buyer's side.
- **72 passages cannot support a topic model.** A half-sample stability test on the old corpus scored **0.246**. The result was not weak, it was absent.

---

# 3. The new methodology

## 3.1 The principle

- **Select on disclosure, not on subject matter.**
- Find transactions whose filings provably exist, retrieve them, and only then ask which ones are about AI.
- "AI" becomes a **label applied after selection**, which converts an unanswerable question into an answerable one: *among deals whose employee terms are public, how many are described in AI terms?*

## 3.2 Stage 1 — Build a candidate pool (offline, deterministic)

Rule frozen in `config/disclosure_pool.toml`, version `disclosure-first-v1`:

- The acquirer must resolve to an SEC filer identifier at **high or medium** confidence.
- The target's industry code must appear in a **24-code digital-technology list** taken from the SEC's own classification.
- The deal must have an announcement date.
- **No minimum deal size.** Deal value is missing for about 70% of the database, so a size filter would silently discard cases on a data-quality accident rather than on substance.

| Pool construction | Deals |
| --- | ---: |
| Starting deal database (Thomson/SDC) | 26,369 |
| Removed: acquirer not resolvable on SEC | −21,651 |
| Removed: target outside the technology screen | −3,658 |
| **Candidate pool** | **1,060** |

## 3.3 Stage 2 — Probe the SEC before downloading anything

This is the step that makes the method affordable.

- For each of the 1,060 deals, read the acquirer's **filing index** and ask a narrow question: *did this company file anything about this transaction?*
- The search window is the same one the retrieval code uses: **30 days before announcement to 30 days after closing**, or a year if no closing date is recorded.
- Outcomes are ranked, best evidence first:

| Probe outcome | Meaning | Deals |
| --- | --- | ---: |
| `agreement_exhibit` | The merger or purchase agreement itself was filed | 89 |
| `merger_proxy` | A merger proxy or tender-offer statement was filed | 81 |
| `announcement_only` | Only a press release in the window | 724 |
| `no_transaction_filing` | Nothing filed in the window | 166 |

- **170 deals were probe-positive.** For **112** of them, the acquirer's own filing **names the target**, which corroborates both the transaction and the company match from the filer's own document rather than from name similarity.

### Two errors found and fixed at this stage

- **The window was initially too short.** A 60-day window classified Take-Two/Zynga and Intuit/Mailchimp as press-release-only, although both produced hundreds of passages in the pilot. Merger proxies and tender offers are filed **months** after announcement; Take-Two's landed at **day 133**. The probe now uses the retrieval window, so it predicts what retrieval will actually find.
- **Exhibit types were read from the wrong field.** The filing directory's JSON `type` field holds the **icon filename**, not the SEC exhibit type. Every agreement lookup silently failed. Exhibit types now come from the filing detail page.

## 3.4 Stage 3 — Retrieve

- We queued **400 deals**: all 170 probe-positive, plus the 230 press-release-only deals with the most filings in their window.
- **Why include the "weaker" group:** Microsoft/Nuance is press-release-only by this test and produced 231 passages in the pilot. Excluding them on principle would have discarded real evidence.
- That judgement was correct: **32 of the final 133 deals** came from the press-release-only group.
- Retrieval result: **35,296 documents, 96,936 pattern matches, zero failures.**

## 3.5 Stage 4 — Build the passage corpus

- A **passage** is one block of text from a transaction-linked filing that mentions employees, pay, benefits, equity, retention, severance, or employment terms.
- Documents unrelated to the deal are excluded even when the buyer filed them in the window. This matters: JPMorgan filed 2,379 documents in its window, of which almost none concerned the deal.
- Exact duplicates collapse to one row. Near-identical legal boilerplate is grouped into **provision families**, so one repeated clause cannot dominate the model.

| Corpus construction | Count |
| --- | ---: |
| Documents parsed | 6,156 |
| Documents kept as transaction-linked | 2,862 |
| Documents excluded as unrelated to the deal | 3,294 |
| Candidate passages screened | 42,235 |
| **Passages included** | **16,079** |
| Passages excluded | 26,156 |
| Provision families | 34,295 |

### What the screen throws away, and why

| Reason for exclusion | Passages |
| --- | ---: |
| Mentions a generic term with no people context | 8,774 |
| Navigation or index fragment | 6,855 |
| A bare heading such as "Employees" with no content | 4,386 |
| Accounting or financial context | 2,466 |
| Generic definition of "Representative" | 898 |
| Privacy or intellectual-property context, not employees | 865 |

- The screen rejects more than it keeps, deliberately. A table of contents listing the word "Employees" is not evidence about employees.

### Where the surviving text comes from

| Filing type | Passages |
| --- | ---: |
| EX-2.1 (the merger or purchase agreement) | 4,821 |
| 424B3 (prospectus) | 3,475 |
| EX-10.1 (compensation exhibits) | 1,944 |
| S-4 and S-4/A (registration statements) | 2,646 |
| EX-99.1 (press releases) | 678 |

## 3.6 Stage 5 — Freeze the sample with a yield gate

- A deal enters the model only with **at least 10 passages from at least 2 separate documents.**
- The threshold was set before the results were seen. Its purpose is to stop a deal contributing a single repeated clause.
- Deals that fail are **kept in the record**, not deleted.

| Outcome for the 400 retrieved deals | Deals |
| --- | ---: |
| **Met the gate — the study sample** | **133** |
| Below the gate | 102 |
| Retrieved, but zero employee passages | 165 |

- **A zero-passage deal is a fact about disclosure practice, not about the company.** It does not mean the transaction had no employee arrangements. It means the public filings do not discuss them.

## 3.7 Stage 6 — The unsupervised model

The design question was: *what recurring themes exist in this text, without telling the model what to look for?*

| Setting | Value | Reason |
| --- | --- | --- |
| Features | Word and two-word phrase frequencies, weighted by rarity | Standard, interpretable, no black box |
| Method | Non-negative matrix factorisation | Produces additive, readable components |
| Number of themes tested | 3 to 7 | The stability tests choose, not the author |
| Random seed | 20260823 | Fixed, so the run is reproducible |
| Fit sample size | 1,500 passages | About 11 per deal at this sample size |
| Balancing | By source-document family | **Prespecified before the run** |

- The model is given **no category names**. It is never told that "equity" or "severance" exist.
- Theme descriptions in Section 5 were written **after** fitting, by reading each theme's top words and highest-weighted passages. They are the author's reading, not labels the model was taught.

### On the balancing choice

- The 10-deal pilot showed that balancing by document family scored better than balancing by deal.
- That setting was therefore **fixed in writing before this run**, precisely so it could not be chosen after seeing which option flattered the results.
- The other two settings were run afterwards as sensitivity checks only.

## 3.8 Stage 7 — How the model is tested

- **Leave-one-deal-out:** remove each deal, refit, and check whether the theme reappears. Threshold set in advance: **0.80**.
- **Bootstrap:** 100 fixed-seed resamples.
- **A rival method:** an entirely different clustering algorithm run on the same text, compared for agreement. Threshold: **0.20**.
- **Sensitivity:** the whole model refit under all three balancing settings.

---

# 4. The sample

- **133 completed technology acquisitions**, announced 2020 to 2022.
- **13,817 employee passages.**

| Property | Value |
| --- | --- |
| Announced 2020 / 2021 / 2022 | 35 / 66 / 32 |
| Largest single deal's share of the text | **5.8%** |
| Deal value disclosed | 107 of 133 |
| Median disclosed value | $312 million |
| Largest deal | $43.5 billion (S&P Global / IHS Markit) |
| Target status: private / subsidiary / public / not stated | 70 / 20 / 14 / 29 |
| Source: agreement / proxy / press release | 66 / 35 / 32 |

- The concentration figure is the important one. In the failed approach, one deal was **44%** of the text. Here the largest is **5.8%**, so **no single transaction drives the result.**

### The ten largest contributors

| Acquirer | Target | Passages |
| --- | --- | ---: |
| FiscalNote Holdings | Aicel Technologies | 797 |
| CF Acquisition Corp VI | Rumble | 708 |
| ADTRAN | ADVA Optical Networking | 534 |
| System1 | Protected.Net Group | 492 |
| Ginkgo Bioworks | Baktus (epidemiological unit) | 476 |
| Take-Two Interactive | Zynga | 418 |
| Advanced Micro Devices | Xilinx | 403 |
| Entegris | CMC Materials | 314 |
| Advent Technologies | UltraCell | 308 |
| Teledyne Technologies | FLIR Systems | 287 |

---

# 5. Results

The model selected **three themes**. Each is described below with the words that define it, how much text
it accounts for, and how well it survived testing.

## 5.1 Theme 1 — Executive and officer language

- **Defining words:** executive, officer, chief, employment, executive officer, chief executive, directors, employees, board, officers
- **Passages: 5,741.** Provision families: 4,947. Present in all 133 deals. Mean share of a deal's text: 35.5%.
- **Coherence: 0.258.** **Leave-one-deal-out recovery: 0.864.**

**Reading (provisional).** References to executives, officers, directors and the board. This theme
**mixes two different things**: contractual executive-employment and change-in-control terms, and the
officer or director language that appears in proxies and announcement press releases, including quoted
remarks by a chief executive. Its coherence is the lowest of the three, which is what a mixed component
looks like. It should not be read as a single kind of employee provision.

## 5.2 Theme 2 — Benefit plans and retirement law

- **Defining words:** plan, benefit, ERISA, employee, benefit plan, code, pension, employee benefit, plans, benefit plans
- **Passages: 5,762.** Provision families: 5,016. Mean share of a deal's text: 42.7%.
- **Coherence: 0.351.** **Leave-one-deal-out recovery: 0.889.**

**Reading (provisional).** Definitions and covenants about employee benefit plans: plan schedules,
retirement-law representations, pension and welfare arrangements, and undertakings about what benefits
continue after closing. This is the most self-consistent contractual theme, and the largest by share of
the average deal's text.

## 5.3 Theme 3 — Equity awards at the closing moment

- **Defining words:** stock, shares, common, common stock, restricted, restricted stock, units, options, merger, outstanding
- **Passages: 4,576.** Provision families: 3,725. Mean share of a deal's text: 21.9%.
- **Coherence: 0.432.** **Leave-one-deal-out recovery: 0.983.**

**Reading (provisional).** What happens to employees' stock, options, restricted stock and restricted
stock units at the moment the transaction closes: conversion, assumption, vesting treatment, and cash-out
of outstanding awards. It is the most internally coherent and the most stable theme of the three.

## 5.4 How well the themes held up

| Theme | Passages | Coherence | Leave-one-deal-out recovery | Passes the 0.80 bar? |
| --- | ---: | ---: | ---: | --- |
| Executive and officer language | 5,741 | 0.258 | 0.864 | Yes |
| Benefit plans and retirement law | 5,762 | 0.351 | 0.889 | Yes |
| Equity awards at closing | 4,576 | 0.432 | 0.983 | Yes |

- **71 automated checks passed. 0 failed. 1 warning.**

### The comparison that matters most

| Model | Deals | Overall recovery | Verdict |
| --- | ---: | ---: | --- |
| The 10-deal pilot | 10 | **0.630** | **Failed** the 0.80 bar |
| This study | 133 | **0.864–0.983** | **Passed** on every theme |

- Same method, same thresholds, more deals. **The pilot's failure was a sample-size problem, not a method problem.** This is the single most useful methodological result of the project.

## 5.5 Sensitivity: does the answer depend on how we built it?

| Balancing setting | Themes found | Recovery per theme | Leading words |
| --- | ---: | --- | --- |
| Source-family (**primary, prespecified**) | 3 | 0.86, 0.89, 0.98 | executive; plan; stock |
| By deal | 3 | 0.95, 0.95, 0.95 | employment; stock; plan |
| Unbalanced | 3 | 0.90, 0.94, 0.98 | executive; plan; stock |

- **All three settings return the same three themes**, in different proportions, and every component clears the 0.80 bar.
- The themes are a property of the text, **not an artefact of the analyst's configuration.**

## 5.6 The one warning, stated plainly

- A **completely different clustering algorithm** was run over the same passages and its grouping was compared with the model's.
- Agreement score: **0.034**, against a threshold of **0.20**.
- **What this means:** the three themes are each individually stable — they reappear when any single deal is removed — but **a different algorithm would divide the same text differently.**
- **How to read the themes because of it:** as *recurring patterns of language*, not as *the one correct taxonomy* of employee provisions.

## 5.7 The AI subgroup

- Applied **after** selection, to deals already known to have employee disclosure.

| Label | Deals |
| --- | ---: |
| Filings describe the target in explicit AI terms | **17** |
| Weaker or adjacent AI language | 0 |
| No AI language near the target's name | 116 |
| Deals using language about a team "joining" the buyer | 45 |
| Deals with explicit acqui-hire language | 3 |

- Named examples with the wording their own filings use: Microsoft / Nuance, Hewlett Packard Enterprise / Silver Peak, DocuSign / Seal Software ("artificial intelligence", "natural language"), Intercontinental Exchange / Ellie Mae, Progress Software / Chef, Take-Two / Zynga ("machine learning"), SentinelOne / Attivo Networks ("AI-powered").
- **17 of 133 is itself a result.** Among transactions whose employee terms are public, only a minority are described in AI language at all.
- This is **technology M&A with an AI subgroup inside it**, not an AI-deal sample. Every label is machine-derived and pending human review.

## 5.8 Tone, as a secondary diagnostic only

- Counts protective and negative wording per hundred tokens, then subtracts the average for the same filing type, so deals are compared against **ordinary legal language** rather than against plain English.
- Highest protective-language residuals: Opendoor / Commeasure (+5.33), Vontier / DRB Systems (+1.83), KKR / Therapy Brands (+1.57).
- Recorded in the manifest as `secondary_diagnostic_corpus_not_validated`.
- **This measures drafting style. It is not evidence that any buyer treated people better.**

---

# 6. The separate deal-architecture layer

- A second, distinct layer codes **what kind of transaction** each of the ten original pilot deals was. This is **rule-based human coding, not unsupervised learning**, and the two are never mixed.
- Six attributes per deal: legal form, scope and control, IP treatment, business continuity, workforce movement, and explicit talent motive.
- A strict rule was introduced: **every asserted claim must quote the SEC document word for word.**

| Treatment of the 70 register rows | Rows |
| --- | ---: |
| Now quote the filing verbatim, each verified as an exact substring | **20** |
| **Withdrawn to "unknown"** because no sentence in the document states it | 23 |
| Already recorded as unknown | 27 |

- **Withdrawing is the safe direction.** A nearby but unsupporting quote looks like evidence while proving nothing, which is worse than an honest paraphrase.
- **Example of a withdrawal:** Microsoft / Nuance's only reviewed document is a press release saying "acquisition". That cannot support a claim of *statutory merger*, so the legal form is now unknown. Its leadership-continuity claim survives, because the release states that **"Mark Benjamin will remain CEO of Nuance, reporting to Scott Guthrie."**
- All nine IP-treatment rows were withdrawn; the register itself recorded that no reviewed passage addresses IP.
- Resulting archetype suggestions: full acquisition 4, asset acquisition 1, asset acquisition with talent salience 1, unknown 5. All are **machine suggestions pending human review**, and the three human-decision columns remain blank.

---

# 7. What the results mean

## 7.1 The substantive reading

- **Employee terms in technology acquisitions cluster into a small number of recurring instruments.** Across 133 deals and 13,817 passages, three themes account for the text: benefit-plan continuity, equity-award treatment at closing, and executive-level employment and officer language.
- **Benefit continuity is the largest single category** by share of the average deal's text (42.7%). The most common thing a merger agreement says about ordinary employees concerns their health and retirement plans.
- **Equity treatment is the most standardised.** Its recovery of 0.983 and its high coherence say that acquirers describe option and share conversion in strikingly consistent language across very different deals.
- **Executive language is the least standardised.** It mixes contract terms with announcement rhetoric, which is a finding about *where* companies talk about people: senior individuals appear in press releases and proxies, ordinary employees appear in the agreement's covenants.
- **Explicit talent framing is rare in the legal record.** Only 3 of 133 deals use explicit acqui-hire language, and 45 use "joining" language. The talent story that dominates press coverage is largely absent from binding documents.

## 7.2 The methodological reading

- **Selecting research samples by subject matter fails when the evidence is disclosure-dependent.** This is the transferable lesson. The AI-first screen was not badly implemented; it was asking for evidence that structurally does not exist.
- **Sample size, not method, was the binding constraint.** The identical pipeline scored 0.630 on 10 deals and 0.864–0.983 on 133.
- **Cheap existence checks before expensive retrieval change what is feasible.** Probing 1,060 deals took about 40 minutes and turned a blind crawl into a targeted one.

## 7.3 What this does not mean

- It does **not** mean employees at these companies were retained, paid as promised, or satisfied.
- It does **not** mean a buyer with more protective language treated people better.
- It does **not** establish cause and effect in any direction.
- It does **not** describe acquisitions in general. See Section 9.

---

# 8. Reproducibility

- Every number in this report is read from a manifest or table produced by the pipeline. The report generator computes no statistics of its own, so the document cannot drift from what the code produced.
- The result tables are published in the repository at `data/published/disclosure_sample_133/` (410 KB, all 400 probed deals with the 133 modelled ones marked).
- Excluded from publication with the reason recorded: the 117 MB passage corpus, the 35,296 retrieved documents, the HTTP cache, and the licensed vendor archive.
- Selection rule `disclosure-first-v1`. Corpus hash `97ea426f6900a345…`.
- Software state: **269 tests passing**, lint and type checks clean.

```
tag-edgar screen-disclosure-pool data/derived/deal_catalog.csv
tag-edgar probe-disclosure data/derived/disclosure_pool/pool.csv
tag-edgar build-disclosure-queue data/derived/disclosure_probe/probe_results.csv
tag-edgar run-disclosure-sample data/derived/disclosure_review_queue.csv
bash scripts/run_disclosure_analysis.sh
```

---

# 9. Limitations

## 9.1 The sample is selected by disclosure

- It describes acquisitions whose **buyers file with the SEC and put the agreement on the record.**
- Deals by private, private-equity, and foreign buyers are largely absent — **21,651 of 26,369** were removed for exactly this reason.
- This is **a property of the public record, not a sampling error that weighting can repair.** No amount of statistical adjustment recovers documents that were never filed.

## 9.2 The corpus relevance audit was not run

- The intended check: a person reads **150 sampled passages** (75 kept, 75 rejected) blind, and confirms the screen kept the right ones. The bar is 90% relevance among kept passages and under 5% missed content among rejected ones.
- It was **skipped for time** in this cycle, by direction.
- **Why this matters concretely:** the same audit run on an earlier corpus scored **72% against a 90% threshold**, with 5.33% missed content. So the risk that a meaningful share of "employee" passages are not really about employee treatment is **real and already measured**, not hypothetical.
- Consequence, enforced by the software: every downstream artifact is labelled provisional and the report verdict is withheld. The blinded packet is prepared and can be labelled later, upgrading the results **without re-running any model**.

## 9.3 These are documents, not outcomes

- A retention bonus is a contractual design. It is not proof anyone stayed.
- A promise of benefit continuity is a promise, not an observation.

## 9.4 The theme descriptions are provisional

- They were written after seeing the model's output and have **not** been scored by two independent reviewers. The blinded review packet exists and is unlabelled.

## 9.5 Theme 1 is a mixed component

- Its low coherence and its mixture of contract text with press-release quotes mean it should not be treated as a single provision type.

## 9.6 Company matching is machine-confirmed

- For 112 deals the acquirer's own filing names the target, which is strong corroboration. **No person has checked each pairing.**

## 9.7 The architecture layer covers ten deals, not 133

- Only the ten original pilot deals have reviewed transaction-structure evidence, and even there the human review columns are blank.

---

# 10. What would strengthen this next

Ordered by value gained per hour spent.

1. **Label the 150-row relevance packet.** About one hour for two people. This single act moves every result from provisional to validated, or tells us honestly that the screen needs repair.
2. **Complete the two-reviewer theme review.** 30 items, roughly 20 minutes each. It converts the theme names from one person's reading into a measured agreement statistic.
3. **Separate announcements from agreements and refit.** Theme 1 mixes the two. Splitting them would test whether executive language is really one theme or two.
4. **Extend the years.** The database covers 1980–2022 and we used 2020–2022. Widening would enlarge the AI subgroup beyond 17 deals.
5. **Decide whether the architecture layer scales.** Either extend rule-based coding to all 133 deals with machine-only fields, or keep it as a deliberate ten-deal deep dive.

---

# 11. Questions for Dr. Singh

- Is a **disclosure-selected sample** acceptable for this research question, given that private and foreign buyers can never be included?
- Should the 150-passage human audit be completed before anything is presented as a finding?
- Theme 1 mixes contractual executive terms with press-release rhetoric. **Should announcements be excluded** from the corpus and the model refit?
- Is **17 AI-labelled deals** a usable subgroup, or should the year range widen first?
- Should the deal-architecture layer be **rebuilt at 133 deals**, or remain a ten-deal deep verification alongside the large-sample text analysis?
