# Meeting script: what to say to Dr. Singh

Read the bold lines out loud if you want. The rest is there so you are not caught out.
Total speaking time if you go straight through: about six minutes.

---

## 0. Before you start

- Have open: `docs/full_research_report.pdf`, and the funnel table in Section 3.
- The single number to remember: **133 deals, 13,817 passages.**
- The single sentence to remember: **"The pilot failed because of sample size, not because the method was wrong."**
- If you only get through three sections, make them **1, 4, and 6**.

---

## 1. Open with the result, not the story (30 seconds)

> **"We now have 133 acquisitions with 13,817 employee-related passages from SEC filings, and the unsupervised model runs cleanly on them. Three themes came out, and all three passed the stability tests that the 10-deal pilot failed."**

- Do not start with the methodology. Lead with the fact that it worked.
- Then immediately hand over the honest framing, before he has to ask for it:

> **"I want to be upfront that these are provisional. One quality check was not run, and I will come back to that."**

---

## 2. Why the old approach had to be abandoned (60 seconds)

> **"The earlier approach searched for AI companies first and then looked for their filings. That gave us 13 usable deals and 72 passages, and 44% of the text came from a single deal."**

> **"The reason is that AI startups are mostly bought by private companies, private-equity funds, and foreign buyers. Those buyers do not file with the SEC. Out of 119 candidates, 57 acquirers did not exist in the SEC system at all."**

**The line that makes the point land:**

> **"Intuit buying Mailchimp gave us 84 passages. Fastly buying Glitch gave us zero. Both targets were private companies. The difference was entirely the buyer."**

- So: what predicts whether employee text exists is whether **the buyer** is an SEC registrant who filed the agreement. Not whether the target is an AI company.

---

## 3. What we did instead (60 seconds)

> **"So we flipped the order. We start from deals where the filings provably exist, retrieve those, and apply the AI label at the end instead of the beginning."**

Walk the funnel with your finger on the table:

| Step | Deals |
| --- | ---: |
| Starting deal database | 26,369 |
| Buyer resolves on the SEC system | 4,718 |
| Target is a technology company | 1,060 |
| We asked the SEC directly whether each one filed | 1,060 |
| Downloaded | 400 |
| **Had enough employee text to use** | **133** |

- One extra detail worth saying, because it shows judgment:

> **"Before downloading anything, we asked the SEC index whether each of the 1,060 deals had actually filed a transaction document. That took about forty minutes and turned a blind crawl into a targeted one."**

---

## 4. The results (90 seconds)

> **"The model was given no categories. It found three themes on its own."**

| Theme | What it is | Passages |
| --- | --- | ---: |
| Benefit plans and retirement law | Health, pension and benefit promises after closing | 5,762 |
| Executive and officer language | Senior employment terms, plus officer talk in proxies and press releases | 5,741 |
| Equity awards at closing | What happens to options and share awards the day the deal closes | 4,576 |

> **"The stability test was: remove each deal one at a time and see whether the theme comes back. The bar was 0.80, set in advance. The three scored 0.86, 0.89 and 0.98."**

> **"The 10-deal pilot scored 0.63 on the same test and failed. Same method, same thresholds, more deals. That tells us the pilot's failure was sample size, not method. I think that is the most useful methodological result of the project."**

- Also say, because it pre-empts an obvious challenge:

> **"We re-ran the whole thing three different ways and got the same three themes each time. So they are not an artefact of how I configured it."**

---

## 5. Volunteer the weaknesses before he finds them (90 seconds)

This is the part that earns credibility. **Say all four.**

> **"Four things I want to flag myself."**

1. **The themes are not surprising.**
   > "Benefits, equity and executives is roughly what anyone who has read a merger agreement would expect. The model confirmed structure rather than discovering something new."

2. **All three themes appear in all 133 deals.**
   > "That is the sharpest limitation. Every deal has all three, so the model does not yet separate one kind of deal from another. I cannot say these deals treat people differently from those deals."

3. **A rival algorithm disagreed.**
   > "We ran a completely different clustering method on the same text. Agreement was 0.03 against a 0.20 bar. So the themes are stable, but they are not the only valid way to cut the text."

4. **The quality check was skipped, and it matters.**
   > "There is a check where a person reads 150 sampled passages and confirms the filter kept the right ones. We skipped it for time. The same check on an earlier corpus scored 72% where 90% was needed, so this is a measured risk, not a formality."

**If he asks how bad that might be, do not soften it:**

> **"I looked at the most representative passages in each theme. They are ERISA definitions, share-count footnotes, and a CEO quote from a press release. A rough check found only 3 to 9% of passages contain an actual promise about employees. So the model grouped how these documents talk about employees, but a lot of that talk is definitions rather than commitments."**

---

## 6. The AI question (45 seconds)

He will ask this. Have the answer ready.

> **"Of the 133 deals, 17 describe the target in explicit AI terms. 45 use language about a team joining the buyer. Only 3 use explicit acqui-hire language."**

> **"So honestly, this is technology M&A with an AI subgroup inside it, not an AI-deal sample. But I think the absence is itself a finding: the talent story that dominates press coverage is almost entirely missing from the binding legal documents."**

- If he pushes on whether 17 is enough: **it is not, for a comparison.** Say so, and offer the fix: widen the year range beyond 2020–2022, since the database goes back to 1980.

---

## 7. What you want from him (45 seconds)

Ask these directly. Do not bury them.

1. > **"Is a disclosure-selected sample acceptable for this question? Private and foreign buyers can never be included, and no amount of statistics fixes that."**
2. > **"Should we spend the hour on the 150-passage audit before anything gets presented as a finding?"**
3. > **"The executive theme mixes contract terms with press-release quotes. Should we drop announcements from the corpus and re-run?"**
4. > **"Should the deal-structure layer be rebuilt at 133 deals, or stay a deep dive on 10?"**

---

## 8. If he asks something harder

**"Why should I believe the clusters mean anything?"**
> "Individually they are stable, and they survive removing any single deal and three different setups. But I would not claim they are the true taxonomy, because a different algorithm splits the text differently. I would call them recurring language patterns."

**"What is the actual contribution here?"**
> "Two things. A method: select on disclosure, not on subject matter, when the evidence is disclosure-dependent. And infrastructure: the whole pipeline is reproducible, every number traces to a published file, and 269 tests pass."

**"Did you find anything about retention?"**
> "No, and we cannot with this data. These are contracts and announcements. A retention bonus is a contractual design, not proof anyone stayed. Measuring that needs employment data we do not have."

**"Why 2020 to 2022?"**
> "That is what the linked database export covers for the resolved-acquirer sample. Extending is the cheapest way to grow the AI subgroup, and it is on my list."

**"Is any of this ready to write up?"**
> "The methodology and the funnel are. The cluster interpretation should wait for the audit and the two-reviewer check."

**"What went wrong that you had to fix?"**
> "Two real bugs. Our search window was too short and missed tender offers filed months after announcement, one at day 133. And we were reading exhibit types from a field that actually holds icon filenames, so every agreement lookup silently failed. Both are fixed and documented."

---

## 9. Close (15 seconds)

> **"Everything is on the branch, the result tables are committed so anyone can check a number, and the code is green. The one hour that would most improve this is the audit. I would like your call on whether to do it before we write anything up."**

---

## 10. Things not to say

- Do not say the model "discovered" the themes. Say it **grouped recurring language**.
- Do not say any company retained employees, or treated them well. **You have no outcome data.**
- Do not call anything a finding. **Say provisional**, until the audit is labelled.
- Do not describe the deal-structure layer as unsupervised. **It is rule-based coding.**
- Do not claim the sample represents acquisitions generally. **It is disclosure-selected, by design.**
