# Meeting briefing: what we did and what we found

Rewritten 2026-09-04 for Aarav, before the Wednesday 2026-09-09 meeting with Dr. Singh.
Everything here is in plain words. Full detail is in [`disclosure_sample_report_c6.md`](disclosure_sample_report_c6.md)
and [`second_level_topics_c6.md`](second_level_topics_c6.md).

**This describes cycle 6.** The version you read before the 09-03 meeting described cycle 5. The
corpus was rebuilt after that meeting because three defects were found in it. The headline result
did not change; several things inside it did, and one earlier recommendation is now withdrawn.
Where this document and the older tables disagree, this one is right.

The meeting is 2:30 with a hard stop at 3:00. Budget 25 minutes. Dr. Singh navigates from the
GitHub repo, so everything named here is reachable by link from [`../NAVIGATION.md`](../NAVIGATION.md).

---

## Part 1 — The one-sentence version

- We collected **134 real company acquisitions** whose SEC filings actually say something about employees.
- We pulled **13,954 pieces of employee-related text** out of those filings.
- We ran a model that reads the text and finds **recurring themes on its own**, with no categories given to it.
- It found **three clear themes**, and they held up under every stability test we ran.
- **They then survived a full rebuild of the corpus** — which is the real news since the last meeting.

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
| **Deals with enough employee text** | **134** | This is our final sample |

**What the SEC check found across the 1,060:**

- **89 deals** filed the actual purchase agreement (the best source).
- **81 deals** filed a merger proxy or tender offer (also good).
- **724 deals** filed only a press release.
- **166 deals** filed nothing at all in the relevant time window.

**Why we still downloaded 400 and not just the 170 best:**

- Press-release-only deals sometimes still turn out rich. Microsoft–Nuance looked press-release-only but gave **231 passages**.
- That judgement paid off: **32 of our final 134 deals** came from that "weaker" group. (The other 102 split 67 from a filed agreement and 35 from a merger proxy.)

---

## Part 5 — What happened to the 400 we downloaded

- **134 deals** had enough employee text to use → these are our sample.
- **104 deals** had a little text, but not enough → set aside, still counted.
- **162 deals** had documents but **zero** employee text → we kept them in the record.

Last cycle those numbers were 133 / 102 / 165. Fixing the corpus pushed **one deal over the
threshold**, which is a real change to the sample rather than a rounding difference.

**Important honesty point:**

- A deal with no employee language is **not** proof the company ignored its employees.
- It only means **the public filings don't discuss it**. We say this plainly in the report.

---

## Part 6 — What the sample looks like

- **134 deals**, announced 2020–2022 (35 in 2020, 67 in 2021, 32 in 2022).
- **13,954 employee passages** in total.
- Biggest single deal is only **6.6%** of the text (FiscalNote–Aicel). In the failed attempt, one deal was 44%. This means **no single deal drives the results**.
- Deal size: value disclosed for 108 of 134. **Median $311 million**, largest **$43.5 billion** (S&P Global buying IHS Markit).
- Target types: 71 private, 20 subsidiaries, 14 public, 1 joint venture, 28 not stated.
- **17 of 134** describe the target in clear AI terms.

**Where the text came from:**

- 6,156 documents read → 2,862 were actually about the deal.
- 36,642 candidate passages found → **16,173 kept** after filtering.
- The rest were thrown out as page navigation, accounting notes, legal disclaimers, and headings that mention "employees" but say nothing about how they are treated.

---

## Part 7 — THE RESULTS: what the model found

The model was given **no categories**. It read the text and grouped it by itself. It found three
themes. Dr. Singh's own reading of them, from the last meeting, is noted under each.

### Theme 1 — Executive and officer language
- **4,100 passages.** Dr. Singh read this as the language aimed at **the C-suite**.
- Words that define it: executive, officer, chief, board, employment, directors.
- **What it is:** talk about senior people — their employment terms, and mentions of officers and directors in proxies and press releases.
- Internal consistency **0.309**, stability **82%**.

### Theme 2 — Benefit plans and retirement law
- **7,689 passages.** Dr. Singh read this as the language aimed at **rank-and-file workers**.
- Words that define it: plan, benefit, ERISA, pension, employee benefit.
- **What it is:** promises about health plans, retirement plans, and benefits after the deal closes.
- Internal consistency **0.198**, stability **92%**. It is now the **largest** theme and the **least internally consistent** one.

### Theme 3 — Stock and equity awards
- **4,384 passages.** Dr. Singh read this as the language aimed at **high-skilled workers**.
- Words that define it: stock, shares, restricted stock, options, effective.
- **What it is:** what happens to employees' stock options and share awards the moment the deal closes — converted, cashed out, or carried over.
- Internal consistency **0.399**, stability **99.6%**. Still the strongest theme on every measure.

**Which theme dominates a deal:** benefits for 100 of 134 deals, equity for 19, executive for 15.

### The four things actually worth the meeting

**1. The strongest result survived the rebuild completely intact.**
Inside Theme 3 there is a sub-theme we call **"award treatment at the effective time"** — what
happens to each option and RSU at closing: assumed, converted, accelerated, or cancelled. It has
**all ten of its defining terms identical** across the two cycles, 1,159 → 1,154 passages,
consistency 0.469 → 0.464, stability 98% → 97%. This is the most durable finding in the study and
the one closest to the research question. Its internal *number* changed (it was `topic_3`, it is
now `topic_2`), which is why we now match components **by their terms and never by their number**.

**2. The sub-theme that answered Dr. Singh's own benefits question dissolved.**
He asked whether benefits are actually continued after a deal. In cycle 5 there was one component
holding **372 of 387** benefit-continuity passages — though even then it **failed** the stability
test at 75%. In cycle 6 those passages **scatter across all three** sub-themes (111 / 210 / 82),
and the word "continuing" appears in **no** cycle-6 term list at all. Say this plainly: **the
question he asked is the one this method currently answers least well.** It is not a small
caveat and it should not be buried.

**3. Collective bargaining changed parent and fails under both.**
It sat under Theme 1 in cycle 5 (213 passages) and sits under Theme 2 in cycle 6 (492 passages).
It **fails the stability bar in both** — 54% now. Failing at around the same level under two
different parents, across a full corpus rebuild, is a **robust negative finding** and worth
reporting as one. But it also lost what made it interesting: its consistency fell from 0.628 to
0.272.

**4. An earlier recommendation is now reversed.**
Cycle 5 found that dropping 622 press releases took Theme 1 from 1-of-3 sub-themes passing to
3-of-3, and the report **recommended excluding EX-99 press releases**. In cycle 6 Theme 1 passes
**3 of 3 with press releases in and 2 of 3 with them out**. The corpus fix had already been doing
what the exclusion appeared to do. **Treat that recommendation as withdrawn.** This is a live
question for the meeting, not a settled one.

---

## Part 8 — How much can we trust these three themes?

**The main test: "leave one deal out."**
- We removed each deal one at a time and refit the model, to see if the themes survived.
- Theme 1 survived **82%** of the time. Theme 2, **92%**. Theme 3, **99.6%**.
- The bar we set in advance was 80%. **All three passed, in both cycles.**

**The strongest evidence is that they survived the rebuild.**
- The corpus was rebuilt from scratch with three defects fixed. The model still chose **three** themes.
- They are **the same three by their terms**, and **all 133 deals present in both cycles kept the same dominant theme**.
- That is a much harder test than any single re-run, and it is the main thing to report.

**What moved inside them.** Of 14,888 passages assigned in both cycles, **84.2% stayed put**. There
is exactly one large movement: **1,955 passages went from Theme 1 to Theme 2**. Every other
category of movement is under 250 passages.

**We also re-ran it three different ways** (different ways of balancing the text sample):
- All three ways produced **the same three themes**, just in different proportions.

**Overall score card:** **71 automatic checks passed. 0 failed. 1 warning.**

**The one warning, in plain words:**
- We ran a **completely different clustering method** on the same text and compared.
- The two methods **agree only weakly** — 0.19, where we wanted above 0.20.
- It is worth saying that this improved a lot: it was **0.03** in cycle 5, so cleaning the corpus made the two methods **much** closer to agreeing. It still does not clear the bar.
- Meaning: our three themes are each individually solid, but **another method would slice the text differently**.
- So: treat these as "recurring language patterns," not "the one true set of categories."

### Splitting each theme in two levels

We split each theme into three sub-themes. **7 of 9 now pass the 80% bar, up from 5 of 9.**

| Parent theme | Sub-theme | Passages | Stability | |
| --- | --- | ---: | ---: | --- |
| Equity | shares and vesting | 2,174 | 81.4% | pass |
| Equity | **award treatment at the effective time** | 1,154 | 97.1% | pass |
| Equity | option and incentive plans | 1,056 | 67.4% | **fail** |
| Executive | costs and customers | 1,466 | 95.9% | pass |
| Executive | executive roles and board governance | 1,944 | 88.0% | pass |
| Executive | proxy-statement language | 690 | 81.6% | pass |
| Benefits | payment and severance | 3,495 | 83.2% | pass |
| Benefits | labor and collective bargaining | 2,671 | 54.1% | **fail** |
| Benefits | ERISA and pension definitions | 1,523 | 100.0% | pass |

**The one caution that matters most here.** Theme 1's sub-split has the **best** stability recovery
in the study (95.9%) attached to the **worst** internal consistency anywhere (0.116). That
combination tells you the language is **templated**, not that it is important. **"3 of 3 pass" is a
statement about reproducibility and nothing else.** If Dr. Singh takes one methodological point
from this meeting, it should be this one.

---

## Part 9 — The AI angle

- Of our 134 deals, **17 describe the target in clear AI terms** in their own filings.
- **45 deals** use language about a team "joining" the buyer.
- **3 deals** use explicit acqui-hire language. **None** uses explicit license-and-hire language.
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
- ❌ We **cannot** treat a high stability score as a sign a theme is important. See the caution in Part 8.

**The biggest gap, stated openly:**

- There is a **quality check we still have not run**: a human reading 150 sample passages to confirm the filter kept the right ones.
- **This is unchanged since the last meeting and it is now the single largest open item.**
- What *has* changed: the packet is now **published and readable** at [`../data/published/corpus_relevance_audit_c6/`](../data/published/corpus_relevance_audit_c6/) — 150 rows across 78 deals, tied to the corpus by checksum, and built on the **cycle-6** corpus so it scores the text we actually report. Earlier packets only ever existed in a git-ignored folder, which is why no second reader ever saw one.
- **What is needed:** Aarav and Sreyas each fill in their **own complete copy** — not half each — so that agreement between the two readers can be measured. Then one command scores it.
- Why it matters: a similar check on an older version scored **72%** when we needed 90%. So this is a **real risk, already measured**, not a formality.
- Because of this, nothing in the report is called a "validated finding."

---

## Part 11 — Seven defects, and the one thing they had in common

This is worth five minutes of the meeting on its own, because the *pattern* generalises.

**Three were in the corpus** (found before the last meeting, fixed in this rebuild):

1. The page's **running header counted as passage text**. The filter threw away anything containing "table of contents" — so real provisions printed under that header were discarded as index entries. Rebuilding readmits **1,266 passage texts**: indemnification survival, RSU award schedules, vesting terms, benefit continuation.
2. **Headings were fed to the model as features.** The words "table", "contents" and "table contents" were literally among the **top ten defining terms of Theme 1**. A running header was a defining feature of a theme.
3. **The same clause was counted twice** when an exhibit and the proxy reprinting it disagreed about its heading — 968 rows, 7.0% of the sample.

**What fixing them did:** navigation exclusions 6,855 → **331**; heading tokens in the model text
9,717 → **9**; duplicate rows 1,017 → **0**. And the mechanism is *measured*, not guessed: the
header had been **misfiling benefit-plan text into the executive theme**, which is exactly the
1,955-passage migration in Part 8. The 1,266 readmitted passages split 516 / 214 / 536 across the
three themes — Theme 2 got the **fewest** — so Theme 2's growth is **reassignment, not
readmission**.

**Four more were in the reporting, not the corpus** (found this week):

4. The pipeline's last step passed only two of its five path settings, so the cycle-6 report was written from a cycle-6 corpus against a **cycle-5 sample**. It printed last cycle's headline over this cycle's tables.
5. The written descriptions of the themes asserted two things cycle 6 had **measured to be false** — that Theme 1 had the lowest consistency (it is now the middle) and Theme 2 the highest (it is now the lowest).
6. **The worst one.** The second-level report matched its written descriptions to sub-themes **by number**, and numbers are not stable across refits. It therefore described the **67%-failing** option-plan sub-theme as *"the most coherent and the most stable of the three"* — and then contradicted itself two paragraphs later. Every quoted example had also silently vanished, and the summary paragraphs were hardcoded prose asserting six now-wrong figures **and recommending the EX-99 exclusion that cycle 6's own evidence contradicts**.
7. The report told readers to check its numbers against the **cycle-5 published tables**, because that path was a hardcoded string.

**All seven are fixed.** Descriptions are now matched by **term overlap** rather than by number —
only 3 of 9 matched well enough to carry, and the other **six were dropped rather than guessed**,
with the report explaining each absence. Summary figures are now **computed** instead of typed.

**The pattern, which is the actual lesson:**

> In all seven, **nothing failed**. No test broke, no script errored. A wrong number printed under
> a correct-looking heading. Every single one was caught by **checking one number against another
> number that should have agreed with it** — a headline against a table three sections below, a
> passage count against a corpus manifest, a prose claim against the diagnostics printed beside it.

Two of these checks are now **automatic** — the publish step refuses to run if the report names the
wrong directory or carries the wrong passage count — and both were verified to actually fire, not
just to pass.

**One honest consequence:** the cycle-5 second-level report can no longer be regenerated
exactly, because deduplication renumbered the passage ids its examples pointed to. It is left in
the repo as the superseded record rather than quietly rewritten.

### Also still standing: the deal-architecture layer

- Sreyas built a separate layer describing **what kind of deal** each of the 10 pilot deals was, with a strict rule: **every claim must quote the actual SEC document word-for-word.**
- **20 rows** now quote real filing text, each checked to be an exact match. **23 rows were withdrawn to "unknown"** because no sentence in the document actually said it.
- Why withdraw rather than find some nearby quote: a quote that doesn't prove the point **looks like evidence but proves nothing**, which is worse than admitting we don't know.

---

## Part 12 — Where everything lives

- **Start here:** [`../NAVIGATION.md`](../NAVIGATION.md) — a map from question to file.
- **Main report:** [`disclosure_sample_report_c6.md`](disclosure_sample_report_c6.md).
- **Inside the themes:** [`second_level_topics_c6.md`](second_level_topics_c6.md).
- **The data tables:** [`../data/published/disclosure_sample_134/`](../data/published/disclosure_sample_134/) — checkable by anyone. Open `09_deal_profiles.csv` for a deal-level view, or `08_passage_links_sample.csv` and click a `source_highlight_url` to land on the actual sentence in the actual SEC filing.
- **The audit waiting to be scored:** [`../data/published/corpus_relevance_audit_c6/`](../data/published/corpus_relevance_audit_c6/).
- **The superseded cycle-5 tables:** [`../data/published/disclosure_sample_133/`](../data/published/disclosure_sample_133/) — its README opens by saying what replaced it and why.
- **Rebuild command:** `bash scripts/run_disclosure_analysis.sh`, then `bash scripts/publish_cycle6.sh`.
- **Timing, for planning:** a corpus rebuild is about **16 hours**; each model fit is about **7 minutes**.

---

## Part 13 — Suggested things to ask Dr. Singh

Ranked. If only three get asked, ask the first three.

1. **The benefits question came back unanswered.** The sub-theme that spoke to benefit continuity dissolved under a cleaner corpus (Part 7, finding 2). Is that worth attacking directly with a targeted search for continuation clauses, rather than hoping an unsupervised model isolates it?
2. **Should we spend the hour on the 150-passage human check?** Nothing here is a validated finding until two people score it, and it has been the top open item for two meetings now.
3. **EX-99 press releases: in or out?** The cycle-5 recommendation to drop them is withdrawn — the corpus fix had been doing that work. The decision is genuinely open again.
4. **What is the right next step — a third level of clustering, or measuring variation?** Our own view: **not** a third level. Leave-one-deal-out rewards language that recurs, so splitting further keeps finding templated boilerplate. The more useful question is how much these terms **vary across deals**, which is the opposite measurement.
5. Is a **disclosure-selected sample** acceptable for this research question, given private buyers can never be included?
6. Is **17 AI-labelled deals** enough for an AI comparison, or should we widen the years beyond 2020–2022?
7. Should the 10-deal deal-structure layer be **rebuilt at 134 deals**, or stay a deep-dive on 10?

---

## Before you present

- **Re-read the top passages of Theme 1 and Theme 2.** Their written descriptions were composed about components that have since reorganised. Theme 3's are safe.
- **Check the ERISA description first** — it carried across on the weakest term overlap of the three that matched (0.54).
- **Never match a theme by its number.** The single most durable result in the study changed number between cycles while keeping all ten of its terms.
