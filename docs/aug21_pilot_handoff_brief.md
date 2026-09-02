# August 21 ten-deal pilot: methods and results brief

Prepared 2026-09-01 for Dr. Manpreet Singh. Branch `aarav/aug21-pilot-completion`.

## Bottom line in three sentences

The pilot now has two cleanly separated analytical layers with working, tested code: a
rule-coded **deal-architecture** layer (what kind of transaction each deal was) and an
unsupervised **employee-language** layer (what themes recur in employee-related passages). The
employee-language layer's repaired cycle-5 corpus is **not present in this checkout** and its
150-row human audit is **unlabelled**, so every model, tone, and cross-table output is
`pending_human_corpus_validation` and no result below may be read as a finding. The
deal-architecture layer shows the ten pilot deals are all conventional control-transferring
acquisitions with no explicit talent motive, which means the pilot cannot, by itself, contrast
acquihire-type structures against ordinary acquisitions.

## 1. What exactly does the unsupervised model classify?

**Passages, not deals.** The unit is one employee-related passage from a transaction-linked SEC
document. Passages pass a rule-based eligibility screen, exact duplicates collapse to one canonical
row, near-duplicate legal boilerplate is grouped into provision families, and a bounded fit sample
is drawn with one representative per deal/provision family. Word and bigram TF-IDF features are
factorised with a fixed-seed NMF at K = 3, 4, 5. Each passage receives soft topic weights; deal
scores are the aggregate of its passages' weights. Topic descriptors are written **after** fitting
from top terms and representative passages and stay provisional until two blinded reviewers score
them.

The model is given no category names. It is not told that "equity" or "severance" exist. It also
does not know the legal meaning of a clause, whether anyone stayed, or whether a theme is
discovery or boilerplate.

## 2. How were deal structures coded separately?

By explicit rules over a version-controlled evidence register, then handed to a human. Six
attributes are coded per deal — legal transaction form; scope and whether control moved; IP
treatment; business/product continuity; workforce, founder, or core-team movement; explicit
talent motive — each pinned to a document ID, canonical SEC URL, section locator, excerpt, and a
stated limitation. A small rule table maps attributes to one or more archetype suggestions with
an ambiguity grade and a competing interpretation. Output rows are labelled
`machine_suggested_pending_human_review`; the three human columns are blank.

This is manual/rule-based coding. It is not unsupervised learning and is never described as such.
See `docs/deal_architecture_codebook.md`.

## 3. Which gates passed, failed, or remain pending?

| Gate | Status | Evidence |
| --- | --- | --- |
| Cycle-4 corpus relevance audit (historical) | **failed** | 72.0% relevance (≥90% needed); 5.33% missed content (<5% needed); 150/150 human rows, 2026-08-26 |
| Cycle-5 screen repair | implemented | `51281a4`; 2,331 included / 3,219 excluded in the originating checkout |
| Cycle-5 corpus relevance audit | **pending** — 75 + 75 rows, no labels | packet built only in the originating checkout; not present here |
| Cycle-5 corpus in this checkout | **absent** | `data/derived/` is git-ignored; pilot queue, runs, and document cache absent |
| Topic model on cycle 5 | **not run** | blocked on the corpus |
| Earlier topic model (cycle-4 corpus) | **rejected** | corpus gate failed; component 2 recovered in 6/9 folds and 21/100 bootstraps; human review blank |
| Human topic-fit review | pending | packet infrastructure ready; no reviewer labels |
| Deal-architecture register validation | pass (machine) | 60 evidence rows, 10 deals, schema-validated; human review pending |
| Offline regression suite | pass | 233 tests |

Nothing in this branch overwrote a failed or pending gate. The report generator now **refuses to
say PASS** unless a scored, passing audit is hash-linked to the exact corpus used; otherwise the
verdict is WITHHELD.

## 4. What do the current provisional results actually show?

**Deal architecture (machine-suggested, pending human review):**

| Deal | Legal form | Workforce movement addressed | Talent motive stated? | Suggested archetype(s) |
| --- | --- | --- | --- | --- |
| Intuit–Mailchimp | equity purchase | continuing employees; two named founders | partial | full_acquisition; talent emphasis |
| Clarivate–ProQuest | transaction agreement (form not asserted) | continuing employees | unknown | full_acquisition |
| Oracle–Cerner | statutory merger | continuing employees | unknown | full_acquisition |
| Microsoft–Nuance | statutory merger | named CEO continuity | unknown | full_acquisition |
| Okta–Auth0 | statutory merger | named founders and key employees | partial | full_acquisition; talent emphasis |
| Roper–Frontline | equity purchase and merger | severance and retention liabilities | unknown | full_acquisition |
| Take-Two–Zynga | statutory merger | continuing employees | unknown | full_acquisition |
| Unity–ironSource | statutory merger | continuing employees; officers/key employees pre-closing | partial | full_acquisition; talent emphasis |
| Skyworks–Silicon Labs Analog | asset purchase | defined transferred-employee group | partial | asset_acquisition; talent emphasis |
| Salesforce–Tableau | tender offer + back-end merger | continuing employees; three named founders; one named executive | partial | full_acquisition; talent emphasis |

Every "partial" is people-specific contract machinery (founder offer letters as closing
conditions, mandatory transfer offers, quantified retention pools) with no stated motive. No deal
is a license-and-hire or reverse acquihire. IP treatment is inferred from legal form in all ten
cases; no reviewed passage addresses it. Business continuity has direct evidence only for
Microsoft–Nuance (an announced intention, not an observation).

**Employee-language topics:** none on cycle 5. The earlier three-component output (benefits and
plan transitions; executive compensation, tax, and merger arrangements; equity-award conversion
and vesting) is retained only as a rejected prototype.

**Tone and word-use:** secondary drafting-style diagnostics; not rerun, and their manifests now
state the corpus gate they were computed under.

**Cross-table:** the generator is built and tested, but it cannot be populated until the cycle-5
topic matrix exists. Because the architecture layer has almost no variation, the cross-table on
these ten deals will describe one archetype family with different topic weights, not a contrast
between structures.

## 5. Which exact paragraphs support each displayed example?

Every displayed example in a generated report now links to its **paragraph**, not only its
document: each evidence row carries `source_url` and, where the quoted text is verbatim,
`source_highlight_url` using the `#:~:text=` directive. On the six cached SEC document families
tested (8-K body, EX-2.x agreement, EX-10.x compensation, EX-99.x press release, proxy, other
filing body) the quoted fragment was found in the rendered text 6/6 times; this was verified
against extracted document text, not by opening a browser.

The ten architecture rows currently cite the human-curated salvage record, whose excerpts are
paraphrases. They therefore carry the canonical URL and section locator with
`highlight_status = unsupported_paraphrase_not_quotable`; no highlight link was fabricated.
Replacing each paraphrase with the verbatim clause once the documents are retrieved populates the
highlight links with no other change.

| Deal | Document | Locator |
| --- | --- | --- |
| Intuit–Mailchimp | [EX-2.1](https://www.sec.gov/Archives/edgar/data/896878/000119312521271682/d226456dex21.htm) | §§7.6–7.7 |
| Clarivate–ProQuest | [EX-2.1](https://www.sec.gov/Archives/edgar/data/1764046/000110465921067259/tm2116608d1_ex2-1.htm) | §8.01(a) |
| Oracle–Cerner | [EX-2.1](https://www.sec.gov/Archives/edgar/data/1341439/000119312521363742/d235675dex21.htm) | §3.06(c) |
| Microsoft–Nuance | [EX-99.1](https://www.sec.gov/Archives/edgar/data/789019/000119312521112687/d171120dex991.htm) | announcement |
| Okta–Auth0 | [EX-2.1](https://www.sec.gov/Archives/edgar/data/1660134/000119312521156436/d145794dex21.htm) | recitals; §8.02(f) |
| Roper–Frontline | [EX-2.1](https://www.sec.gov/Archives/edgar/data/882835/000119312522233743/d356123dex21.htm) | "Indebtedness" definition |
| Take-Two–Zynga | [EX-2.1](https://www.sec.gov/Archives/edgar/data/946581/000119312522005771/d282059dex21.htm) | §§1.8, 6.2 |
| Unity–ironSource | [EX-2.1](https://www.sec.gov/Archives/edgar/data/1810806/000119312522193960/d292378dex21.htm) | §§5.1, 6.7 |
| Skyworks–Silicon Labs Analog | [EX-2.1](https://www.sec.gov/Archives/edgar/data/4127/000110465921053805/tm2113063d1_ex2-1.htm) | §5.5 |
| Salesforce–Tableau | [SC 14D-9](https://www.sec.gov/Archives/edgar/data/1303652/000119312519188693/d744331dsc14d9.htm) | Employee Matters; Offer Letters |

## 6. What cannot yet be concluded?

- Nothing about which themes the repaired corpus contains: the cycle-5 model has not run.
- Nothing about actual employee retention, headcount, or behaviour: every source is a contract or
  announcement.
- Nothing causal, and nothing about deals outside these ten.
- No archetype for any deal: all ten are machine suggestions awaiting a reviewer.
- No contrast between talent-driven and conventional structures: the pilot contains only the
  latter.
- No claim that one buyer "cared more" from tone or term counts.

## 7. Smallest remaining human-review decisions

1. **Supply the pilot inputs** (`pilot_review_queue.csv` with its confirmed CIK/scope columns and
   `pilot_runs/`, or authorise a live SEC rerun under a real `SEC_USER_AGENT`) so the cycle-5
   corpus and packet can be rebuilt here.
2. **Label the 150-row cycle-5 packet** (one assessor, ~1–2 hours) and score it. This single act
   decides whether any employee-language output can leave `pending`.
3. **Review the ten architecture rows** (one reviewer, <1 hour): confirm or change each suggested
   archetype and fill the three human columns.
4. Decide whether to **add deals with genuinely different structures** (a license-and-hire, a
   team acquihire) before any cross-table is interpreted.

## 8. Is this pipeline ready to expand to 100 deals?

**Not yet, for two reasons that are independent of code.** First, the corpus screen has not
passed its human relevance gate; expanding an unvalidated screen multiplies its errors. Second,
the pilot sample has no structural variation, so the study cannot yet show that the two layers
produce a usable contrast. The code is ready: the pipeline is deterministic, hash-linked,
gate-propagating, source-linked to the paragraph, and tested. The right next step is the
150-row audit, then a 10-deal cycle-5 run, then a deliberately structure-diverse second batch of
10–20 deals, before 100.

## Appendix: corpus-flow counts (cycle 5, as built in the originating checkout)

```
469 retrieved documents parsed
 ├─ 358 transaction-linked, included
 └─ 111 excluded
5,550 screened candidate passages
 ├─ 2,331 included (cycle-5 screen)
 └─ 3,219 excluded
150-row blinded audit packet (75 included + 75 excluded) — pending_human_labels
```

Reproduction: `docs/cycle5_freeze_and_assessor_instructions.md` §4.
