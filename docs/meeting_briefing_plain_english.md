# Meeting briefing: what we did and what we found

Prepared 2026-09-02 for Aarav, before the meeting with Dr. Singh.
Everything here is in plain words. Full detail is in `docs/disclosure_sample_report.md`.

---

## Part 1 — The one-sentence version

- We collected **133 real company acquisitions** whose SEC filings actually say something about employees.
- We pulled **13,817 pieces of employee-related text** out of those filings.
- We ran a model that reads the text and finds **recurring themes on its own**, with no categories given to it.
- It found **three clear themes**, and they held up under every stability test we ran.

---

## Part 2 — The problem we had to solve first

- Our earlier attempt searched for **"AI companies"** and then went looking for their filings.
- That failed badly: only **13 deals** produced any employee text at all, and **72 passages** total.
- Worse, **44% of that text came from one single deal**. A model cannot learn anything from that.

**Why it failed:**

- Most AI startups are bought by **private companies, private-equity funds, or foreign buyers**.
- Those buyers **do not file anything with the SEC**. So there is no public document to read.
- Out of 119 AI candidates, **57 acquirers simply did not exist on the SEC system**.

**The key insight:**

- What predicts whether employee text exists is **not** whether the target is an AI company.
- It is whether **the buyer is an SEC-registered company that filed the purchase agreement**.
- Proof from our own data: Intuit buying Mailchimp (a private target) gave **84 passages**. Fastly buying Glitch (also private) gave **0**. The difference was the buyer, not the target.

---

## Part 3 — What we changed

- We **flipped the order of the search**.
- Old way: find AI companies → hope filings exist.
- New way: find deals where **filings definitely exist** → then check which ones are AI.
- "AI" became a **label we apply at the end**, not a filter at the start.

---

## Part 4 — How we found the deals (the funnel)

| Step | Deals left | What happened |
| --- | ---: | --- |
| Starting deal list (Thomson/SDC) | 26,369 | Every deal in the database we have |
| Buyer must exist on the SEC system | 4,718 | 21,651 buyers dropped — private, PE, or foreign |
| Target must be a technology company | 1,060 | 3,658 dropped for being outside tech |
| We asked SEC directly: did they file? | 1,060 | We checked every single one |
| Deals we actually downloaded | 400 | Best-documented ones first |
| **Deals with enough employee text** | **133** | This is our final sample |

**What the SEC check found across the 1,060:**

- **89 deals** filed the actual purchase agreement (the best source).
- **81 deals** filed a merger proxy or tender offer (also good).
- **724 deals** filed only a press release.
- **166 deals** filed nothing at all in the relevant time window.

**Why we still downloaded 400 and not just the 170 best:**

- Press-release-only deals sometimes still turn out rich. Microsoft–Nuance looked press-release-only but gave **231 passages**.
- That judgement paid off: **32 of our final 133 deals** came from that "weaker" group.

---

## Part 5 — What happened to the 400 we downloaded

- **133 deals** had enough employee text to use → these are our sample.
- **102 deals** had a little text, but not enough → set aside, still counted.
- **165 deals** had documents but **zero** employee text → we kept them in the record.

**Important honesty point:**

- A deal with no employee language is **not** proof the company ignored its employees.
- It only means **the public filings don't discuss it**. We say this plainly in the report.

---

## Part 6 — What the sample looks like

- **133 deals**, announced 2020–2022 (35 in 2020, 66 in 2021, 32 in 2022).
- **13,817 employee passages** in total.
- Biggest single deal is only **5.8%** of the text. (In the failed attempt, one deal was 44%.) This means **no single deal drives the results**.
- Deal size: value disclosed for 107 of 133. **Median $312 million**, largest **$43.5 billion** (S&P Global buying IHS Markit).
- Target types: 70 private, 20 subsidiaries, 14 public, 28 not stated.

**Where the text came from:**

- 6,156 documents read → 2,862 were actually about the deal.
- 42,235 candidate passages found → **16,079 kept** after filtering.
- We threw out **26,156** passages: page navigation, accounting notes, legal disclaimers, and headings that mention "employees" but say nothing about how they are treated.

---

## Part 7 — THE RESULTS: what the model found

The model was given **no categories**. It read the text and grouped it by itself. It found three themes:

### Theme 1 — Executive and officer language
- **5,741 passages.**
- Words that define it: executive, officer, chief, employment, directors, board.
- **What it is:** talk about senior people — their employment terms, and mentions of officers and directors in proxies and press releases.
- **Caution:** this is the **messiest** theme. It mixes real contract terms with quotes from CEOs in announcements. Its internal consistency score is the lowest (0.258).

### Theme 2 — Benefit plans and retirement law
- **5,762 passages.**
- Words that define it: plan, benefit, ERISA, pension, employee benefit.
- **What it is:** promises about health plans, retirement plans, and benefits after the deal closes.
- This is the **cleanest contract theme**.

### Theme 3 — Stock and equity awards
- **4,576 passages.**
- Words that define it: stock, shares, restricted stock, units, options.
- **What it is:** what happens to employees' stock options and share awards the moment the deal closes — converted, cashed out, or carried over.
- This is the **most stable** theme of all.

---

## Part 8 — How much can we trust these three themes?

**The main test: "leave one deal out."**
- We removed each deal one at a time and refit the model, to see if the themes survived.
- Theme 1 survived **86%** of the time. Theme 2, **89%**. Theme 3, **98%**.
- The bar we set in advance was 80%. **All three passed.**

**Compare to the old 10-deal pilot:**
- The old pilot scored **0.63** and **failed** this same test.
- Same method, more deals → it now passes. The problem was sample size, not the method.

**We also re-ran it three different ways** (different ways of balancing the text sample):
- All three ways produced **the same three themes**, just in different proportions.
- So the result is **not an accident of how we set it up**.

**Overall score card:**
- **71 automatic checks passed. 0 failed. 1 warning.**

**The one warning, in plain words:**
- We ran a **completely different clustering method** on the same text and compared.
- The two methods **did not agree closely** (score 0.03, we wanted above 0.20).
- Meaning: our three themes are each individually solid, but **another method would slice the text differently**.
- So: treat these as "recurring language patterns," not "the one true set of categories."

---

## Part 9 — The AI angle

- Of our 133 deals, **17 describe the target in clear AI terms** in their own filings.
- **45 deals** use language about a team "joining" the buyer.
- **3 deals** use explicit acqui-hire language.
- Examples: Microsoft–Nuance, HP–Plantronics, DocuSign–Seal Software, Intercontinental Exchange–Ellie Mae, Take-Two–Zynga.

**How to say this in the meeting:**

- This is **technology M&A with an AI subgroup inside it**, not a pure AI-deal sample.
- 17 is a small number, and that is **itself a finding**: among deals with public employee terms, only a minority are described in AI language.
- These labels are **machine-made and not yet human-checked**.

---

## Part 10 — What we CANNOT say (read this before the meeting)

- ❌ We **cannot** say anyone actually stayed at their job. These are contracts and announcements, not outcomes.
- ❌ We **cannot** say one buyer treated people better than another.
- ❌ We **cannot** say anything caused anything. This is description, not cause and effect.
- ❌ We **cannot** claim this represents all acquisitions. Our sample is deliberately made of deals that file with the SEC. Private and foreign buyers are missing — that is a property of the public record, not a mistake we can fix.
- ❌ We **cannot** call the themes final. Two reviewers still need to check them independently.

**The biggest gap, stated openly:**

- There is a **quality check we did not run**: a human reading 150 sample passages to confirm the filter kept the right ones.
- We skipped it for time. **It is disclosed on the front page of the report**, not hidden.
- Why it matters: a similar check on an older version scored **72%** when we needed 90%. So this is a **real risk, already measured**, not a formality.
- Because of this, nothing in the report is called a "validated finding."

---

## Part 11 — The other thing that got fixed

- Sreyas built a separate layer describing **what kind of deal** each of the 10 pilot deals was.
- He added a strict new rule: **every claim must quote the actual SEC document word-for-word.**
- All 70 existing rows were **summaries in our own words**, so the tests broke.

**What was done:**

- **20 rows** now quote the real filing text, each one checked to be an exact match of the document.
- **23 rows** were **withdrawn to "unknown"** because no sentence in the document actually said it.

**Why withdraw instead of finding some quote:**

- Attaching a nearby quote that doesn't prove the point **looks like evidence but proves nothing**. That is worse than admitting we don't know.
- Example: Microsoft–Nuance's only document is a press release saying "acquisition." That **cannot** prove it was legally a merger, so we marked it unknown.
- All 9 "what happened to the IP" rows were withdrawn — the record itself said no document addressed it.

---

## Part 12 — Where everything lives

- **Main report:** `docs/disclosure_sample_report.md` and the Word version `.docx`.
- **The data tables:** `data/published/disclosure_sample_133/` — 410 KB, all 400 deals, checkable by anyone.
- **Rebuild command:** `bash scripts/run_disclosure_analysis.sh`.
- **Code status:** 269 tests passing, all checks green, pull request #5 ready to merge.

---

## Part 13 — Suggested things to ask Dr. Singh

- Is a **disclosure-selected sample** acceptable for this research question, given private buyers can never be included?
- Should we **spend the hour** on the 150-passage human check to upgrade the results from provisional to validated?
- Theme 1 mixes contract terms with press-release quotes. Should we **split announcements out** of the corpus and re-run?
- Is **17 AI-labelled deals** enough for an AI comparison, or should we widen the years beyond 2020–2022?
- Should the 10-deal deal-structure layer be **rebuilt at 133 deals**, or stay a deep-dive on 10?
