# Hiring-outcome feasibility decision

Audit date: 2026-08-23. This memo evaluates whether the existing 2021–2022 ten-deal pilot can
support a historical outcome study using no paid APIs. It does **not** treat filing language as an
employee outcome.

## Decision

**Do not proceed with a broad historical hiring-outcome model using the currently available free
sources.** No audited source provides a consistently observed, firm-level measure of overall hiring
before and after at least 80% of the pilot deals. Current applicant-tracking-system endpoints are not
historical snapshots. H-1B labor-condition applications and WARN notices are useful secondary
signals, but each selects a narrow and changing subset of workforce activity.

The preferred next branch is a licensed, historically versioned job-postings source with stable
company identifiers. If that is unavailable, choose either a prospective monitored cohort or an
explicitly narrower H-1B/WARN study. Do not combine the narrow sources and relabel the result as
retention or total hiring.

## Prespecified estimand and gate

The admissible estimand is an association between pre-deal disclosure-theme weights and a later,
observable signal such as employer job-posting volume, certified H-1B positions, or WARN-covered
layoffs. It is not employee retention, realized headcount, worker welfare, or a causal acquisition
effect.

A primary outcome source passes only when:

1. at least 8 of the 10 pilot deals have comparable pre- and post-event observations;
2. missingness is not mechanically produced by acquisition, employer-name change, industry,
   geography, or disclosure theme;
3. the recorded event is interpretable consistently across employers and time; and
4. company linkage, source version, extraction date, and raw-record provenance are reproducible.

Passing row coverage alone is insufficient if the data-generating process violates items 2 or 3.

## Source audit

| Candidate source | Historical availability | What it actually observes | Primary-outcome gate | Decision |
| --- | --- | --- | --- | --- |
| ATS/job-board endpoints | The audited [Lever Postings API](https://github.com/lever/postings-api) and [Greenhouse Job Board API](https://developers.greenhouse.io/job-board.html#list-jobs) expose postings, not a versioned 2021–2022 history. Web archives such as [Common Crawl](https://commoncrawl.org/get-started) require URL-by-URL recovery and do not establish a complete denominator. | Visible postings at an observed crawl/API time. A posting is neither a hire nor a filled job. | **Fail.** Current endpoints cannot reconstruct the event windows, and opportunistic archive recovery would create unquantified employer- and time-specific missingness. | Use a licensed historical panel or start a prospective monitor. |
| H-1B LCA disclosure data | The Labor Department publishes cumulative quarterly and historical fiscal-year [OFLC disclosure files](https://www.dol.gov/agencies/eta/foreign-labor/performance). | Employer applications for H-1B/H-1B1/E-3 specialty-occupation positions and case metadata. The [H-1B program](https://www.dol.gov/agencies/whd/immigration/h1b) concerns nonimmigrant workers in specialty occupations; certification is not proof that a worker was hired or started. | **Fail as the broad primary outcome.** Employer observations exist for much of the pilot, but the signal covers only sponsored specialty-occupation demand and name continuity changes after acquisitions. | Retain as a prespecified secondary outcome or make it the subject of a narrower study. |
| WARN notices | The Labor Department describes WARN as advance notice for *qualified* plant closings and mass layoffs in its [WARN compliance guidance](https://www.dol.gov/agencies/eta/layoffs/warn). Notices are administered through state/local recipients rather than a single longitudinal federal employer panel. | Threshold-triggered notices, not all layoffs, separations, or headcount reductions. | **Fail as the broad primary outcome.** Zero notices can mean no qualifying event, a below-threshold event, an uncovered employer/site, or a state archive/linkage gap. | Use only as a separate adverse-event indicator with state-by-state coverage and denominator auditing. |
| Census LEHD/QWI/J2J | [Public LEHD products](https://lehd.ces.census.gov/data/) report employment flows by geography, industry, firm characteristics, and worker demographics; firm microdata require restricted access. | Aggregate employment, hires, separations, and job-to-job flows. | **Fail for public firm-level linkage.** Public tables cannot identify these ten named acquirers/targets. | Useful for contextual baselines; firm analysis would require an approved restricted-data design. |

## H-1B pilot coverage audit

The audit used the official FY2020–FY2023 Q4 LCA workbooks, the versioned
[`h1b_pilot_aliases.csv`](../config/h1b_pilot_aliases.csv) crosswalk, and cases whose status began
with `CERTIFIED`. Employer names were normalized by uppercasing, replacing every non-alphanumeric
run with one space, and trimming. For each alias and fiscal year the audit counted cases and summed
the employer-reported `NEW_EMPLOYMENT` field. The files call that field “new employment,” but the
value remains an application field—not verified hiring. A pre/post coverage flag requires at least
one matching certified case in the fiscal year before announcement and in the fiscal year after
closing.

The table reports `certified cases / summed NEW_EMPLOYMENT`. “Pre” is the fiscal year before the
announcement; “post” is the fiscal year after closing. Counts combine the adjudicated acquirer and
target aliases shown in the final column.

| Deal | Pre FY | Pre cases / field | Post FY | Post cases / field | Both-period case presence | Matched employer aliases |
| --- | ---: | ---: | ---: | ---: | --- | --- |
| Intuit–Mailchimp | [2020](https://www.dol.gov/sites/dolgov/files/ETA/oflc/pdfs/LCA_Disclosure_Data_FY2020_Q4.xlsx) | 97 / 13 | [2022](https://www.dol.gov/sites/dolgov/files/ETA/oflc/pdfs/LCA_Disclosure_Data_FY2022_Q4.xlsx) | 119 / 1 | yes | Intuit; Rocket Science Group/Mailchimp (the latter matched only in FY2021) |
| Clarivate–ProQuest | [2020](https://www.dol.gov/sites/dolgov/files/ETA/oflc/pdfs/LCA_Disclosure_Data_FY2020_Q4.xlsx) | 14 / 0 | [2022](https://www.dol.gov/sites/dolgov/files/ETA/oflc/pdfs/LCA_Disclosure_Data_FY2022_Q4.xlsx) | 8 / 0 | yes | Clarivate Analytics (US/CompuMark); ProQuest |
| Oracle–Cerner | [2020](https://www.dol.gov/sites/dolgov/files/ETA/oflc/pdfs/LCA_Disclosure_Data_FY2020_Q4.xlsx) | 296 / 638 | [2023](https://www.dol.gov/sites/dolgov/files/ETA/oflc/pdfs/LCA_Disclosure_Data_FY2023_Q4.xlsx) | 243 / 1,039 | yes | Oracle America/Financial Services/Technical Network/Robotics; Cerner; Oracle Cerner |
| Fastly–Glitch | [2021](https://www.dol.gov/sites/dolgov/files/ETA/oflc/pdfs/LCA_Disclosure_Data_FY2021_Q4.xlsx) | 3 / 0 | [2023](https://www.dol.gov/sites/dolgov/files/ETA/oflc/pdfs/LCA_Disclosure_Data_FY2023_Q4.xlsx) | 0 / 0 | **no** | Fastly; no exact Glitch match |
| Microsoft–Nuance | [2020](https://www.dol.gov/sites/dolgov/files/ETA/oflc/pdfs/LCA_Disclosure_Data_FY2020_Q4.xlsx) | 1,467 / 220 | [2023](https://www.dol.gov/sites/dolgov/files/ETA/oflc/pdfs/LCA_Disclosure_Data_FY2023_Q4.xlsx) | 1,914 / 5,665 | yes | Microsoft; Nuance Communications/Enterprise Solutions |
| Okta–Auth0 | [2020](https://www.dol.gov/sites/dolgov/files/ETA/oflc/pdfs/LCA_Disclosure_Data_FY2020_Q4.xlsx) | 14 / 2 | [2022](https://www.dol.gov/sites/dolgov/files/ETA/oflc/pdfs/LCA_Disclosure_Data_FY2022_Q4.xlsx) | 44 / 0 | yes | Okta; Auth0 |
| Roper–Frontline | [2021](https://www.dol.gov/sites/dolgov/files/ETA/oflc/pdfs/LCA_Disclosure_Data_FY2021_Q4.xlsx) | 1 / 0 | [2023](https://www.dol.gov/sites/dolgov/files/ETA/oflc/pdfs/LCA_Disclosure_Data_FY2023_Q4.xlsx) | 1 / 0 | yes | Roper Technologies; Frontline Technologies Group |
| Take-Two–Zynga | [2021](https://www.dol.gov/sites/dolgov/files/ETA/oflc/pdfs/LCA_Disclosure_Data_FY2021_Q4.xlsx) | 8 / 1 | [2023](https://www.dol.gov/sites/dolgov/files/ETA/oflc/pdfs/LCA_Disclosure_Data_FY2023_Q4.xlsx) | 9 / 1 | yes | Take-Two Interactive Software; Zynga |
| Unity–ironSource | [2021](https://www.dol.gov/sites/dolgov/files/ETA/oflc/pdfs/LCA_Disclosure_Data_FY2021_Q4.xlsx) | 12 / 4 | [2023](https://www.dol.gov/sites/dolgov/files/ETA/oflc/pdfs/LCA_Disclosure_Data_FY2023_Q4.xlsx) | 14 / 2 | yes | Unity Technologies SF; no exact ironSource match |
| Skyworks–Silicon Labs unit | [2020](https://www.dol.gov/sites/dolgov/files/ETA/oflc/pdfs/LCA_Disclosure_Data_FY2020_Q4.xlsx) | 22 / 5 | [2022](https://www.dol.gov/sites/dolgov/files/ETA/oflc/pdfs/LCA_Disclosure_Data_FY2022_Q4.xlsx) | 18 / 2 | yes | Skyworks Solutions; Silicon Laboratories |

Exact employer-case presence is therefore 9/10, but only 6/10 deal windows have a positive
`NEW_EMPLOYMENT` value in both periods. Neither statistic is a measure of realized hires. The sharp
cross-firm concentration—for example, [Microsoft and Oracle dominate the FY2023 field
totals](https://www.dol.gov/sites/dolgov/files/ETA/oflc/pdfs/LCA_Disclosure_Data_FY2023_Q4.xlsx)—also
means that a pooled count model would largely compare sponsorship practices rather than
like-for-like workforce changes.

For reproducibility, the downloaded workbook SHA-256 values were:

- FY2020: `a2226a54a083884d640ce203d78e5abd78ecbbdac69002e762816b3324eb4112`
- FY2021: `02bc4e046a251ce61b6f0790d2f4ff1dc07758ec3a39bee0c6b5d58003840051`
- FY2022: `4b6ee1656fc7f59fb6f4314f3e7a31439c971d06994554b16307bbd96a35618e`
- FY2023: `a070600b44add357335c159109bd1747e6a683b95acb985e464f0fefbbb5561c`

The checked result can be regenerated offline without embedding a downloader in the research
workflow:

```bash
tag-edgar audit-h1b-coverage data/derived/pilot_review_queue.csv \
  --workbook 2020=/path/to/LCA_Disclosure_Data_FY2020_Q4.xlsx \
  --workbook 2021=/path/to/LCA_Disclosure_Data_FY2021_Q4.xlsx \
  --workbook 2022=/path/to/LCA_Disclosure_Data_FY2022_Q4.xlsx \
  --workbook 2023=/path/to/LCA_Disclosure_Data_FY2023_Q4.xlsx \
  --aliases-csv config/h1b_pilot_aliases.csv \
  --output-dir data/derived/h1b_coverage
```

The ignored output includes an alias/year CSV and a manifest containing the input hashes, exact
rules, deal summaries, aggregate coverage counts, and `broad_hiring_outcome_decision=no-go`.

Even if the measured deal-level presence exceeds 80%, the source does not pass the primary gate:
targets may stop filing under their prior names after closing, non-sponsoring employers appear as
structural zeros, and the composition of specialty-occupation sponsorship differs substantially
across firms. Those mechanisms can correlate with both technology subsector and disclosure theme.

## Recommended next design

### Preferred: licensed historical postings panel

Require immutable daily or weekly snapshots spanning at least 12 months before announcement and
24 months after closing, stable employer/brand/location identifiers, documented crawl coverage,
reposts and duplicate handling, filled/removed-post interpretation, and auditable raw-record IDs.
Before modeling, hand-validate employer linkage and weekly coverage on all 10 pilot deals. Expand
only if at least 8 pass and missingness is unrelated to the candidate disclosure themes.

### If licensing is unavailable: prospective cohort

Freeze a new deal cohort and collect postings prospectively from announcement onward. Record every
scheduled fetch, HTTP status, ATS migration, company redirect, posting ID, first/last-seen time, and
raw body checksum. This sacrifices immediate historical inference but provides an observable
denominator and honest missingness.

### Narrow fallback: H-1B and WARN

Define two separate outcomes before viewing theme associations: certified LCA new-employment
positions and occurrence/count of a source-covered WARN notice. Keep employer-alias adjudication,
state coverage, event windows, transformations, and zero-versus-missing rules fixed. Report
permutation intervals and leave-one-deal-out results; label the analysis exploratory and do not use
“retention,” “workforce effect,” or “caused” in conclusions.

## Promotion rule

The hiring branch remains **no-go for a broad outcome study**. It can be promoted only after a
primary source produces a frozen coverage table satisfying the four-part gate above. The H-1B and
WARN branches may proceed independently as narrow feasibility studies, but neither validates the
disclosure taxonomy and neither supports a causal claim.
