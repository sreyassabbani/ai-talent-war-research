# Word-for-word meeting script

Read this out loud as written. Square brackets are stage directions, not spoken.

The main script is about 1,330 spoken words, which is **nine to eleven minutes** at a normal
pace. The "If he asks" section at the end is a bank to draw from, not something to read through.
If you are short on time, the sections that matter most are the opening, the results, and the
weaknesses.

---

## Opening

"Thanks for making the time. I want to give you the result first, then how we got there, then the parts I am not confident about.

We now have 133 completed acquisitions where the SEC filings actually contain employee-related language. That gave us 13,817 passages of text. We ran the unsupervised model on it and it produced three clear themes, and all three passed the stability tests that our earlier ten-deal pilot failed.

Before I go further, I want to be straight with you about one thing. There is a quality check we did not run this cycle, so I am calling everything provisional. I will come back to it and I am not going to bury it."

---

## Why the old approach had to go

"The version I showed you before searched for AI companies first, and then went looking for their filings. That approach gave us thirteen usable deals and seventy-two passages of text. Forty-four percent of that text came from one single deal. There was nothing there to model.

The reason it failed is structural. AI startups are mostly bought by private companies, private equity funds, and foreign corporations. Those buyers do not file anything with the SEC. Out of a hundred and nineteen candidate deals, fifty-seven of the acquirers did not exist in the SEC system at all. There was no document to read, no matter how interesting the deal was.

Here is the comparison that made it obvious. Intuit buying Mailchimp gave us eighty-four passages. Fastly buying Glitch gave us zero. Both of those targets were private companies. The difference was entirely on the buyer's side.

So what actually predicts whether employee text exists is whether the buyer is an SEC registrant who filed the purchase agreement. It has almost nothing to do with whether the target is an AI company."

---

## What we did instead

"So we flipped the order of the search.

Instead of finding AI companies and hoping filings exist, we start from transactions where the filings provably exist, retrieve those, and then apply the AI label at the end instead of using it as the filter at the start. That turns an unanswerable question into an answerable one: among deals whose employee terms are public, how many are described in AI terms?

[Point at the funnel table.]

We started with twenty-six thousand deals in the database. Requiring the buyer to resolve on the SEC system took that to four thousand seven hundred. Requiring a technology target took it to one thousand and sixty.

Then we did something that saved us a lot of time. Before downloading anything, we asked the SEC index directly whether each of those one thousand and sixty deals had actually filed a transaction document. That took about forty minutes and turned a blind crawl into a targeted one.

We downloaded four hundred deals. A hundred and thirty-three of them had enough employee text to use. That is the sample."

---

## The results

"The model was given no categories at all. It was never told that words like equity or severance matter. It read the text and grouped it on its own.

It found three themes.

The largest is benefit plans and retirement law. That is five thousand seven hundred and sixty-two passages. It is promises about health plans, pensions and benefits after the deal closes.

The second is executive and officer language. Five thousand seven hundred and forty-one passages. Senior employment terms, mixed with officer and director talk from proxies and press releases.

The third is equity awards at closing. Four thousand five hundred and seventy-six passages. What happens to employees' stock options and share awards the moment the deal closes.

Now, how much do I trust those. The main test is: remove one deal, refit the model, and see whether the theme comes back. We set the bar at zero point eight before running it. The three themes scored zero point eight six, zero point eight nine, and zero point nine eight.

The ten-deal pilot scored zero point six three on that same test and failed it. Same method, same thresholds, more deals. So the pilot's failure was a sample size problem, not a method problem. I think that is honestly the most useful methodological result of this whole project.

One more thing. We re-ran the entire model three different ways, changing how the text sample was balanced. We got the same three themes every time. So they are a property of the text, not something I produced by configuring it a particular way."

---

## The weaknesses, volunteered

"There are four things I want to flag myself rather than have you find them.

First, the themes are not surprising. Benefits, equity and executives is roughly what anyone who has read a merger agreement would predict. The model confirmed structure. It did not discover something new.

Second, and this is the sharpest problem, all three themes appear in all one hundred and thirty-three deals. Every deal has all three. So right now the model does not separate one kind of deal from another. I cannot tell you that these deals treat people differently from those deals.

Third, we ran a completely different clustering algorithm over the same text as a check, and it disagreed with ours. The agreement score was zero point zero three against a bar of zero point two. So our three themes are individually stable, but they are not the only valid way to divide the text.

Fourth, the quality check. There is a step where a person reads a hundred and fifty sampled passages blind and confirms the filter kept the right ones. We skipped it for time this cycle. That same check on an earlier version of the corpus scored seventy-two percent where we needed ninety. So this is a measured risk, not a formality."

[If he asks how bad it might be, say this. Do not soften it.]

"I went and looked at the most representative passages in each theme. The strongest ones are ERISA definitions, share-count footnotes, and a CEO quote from a press release. I then did a rough check on the middle of each cluster and found only three to nine percent of passages contain an actual promise about employees. So the model reliably grouped how these documents talk about employees, but a lot of that talk is definitions and disclosures rather than commitments. That is exactly what the audit was designed to catch."

---

## The AI question

"On the AI side. Of the one hundred and thirty-three deals, seventeen describe the target in explicit AI terms in their own filings. Forty-five use language about a team joining the buyer. Only three use explicit acqui-hire language.

So I would describe this honestly as technology M and A with an AI subgroup inside it, not as an AI-deal sample. But I think the absence is itself worth reporting. The talent story that dominates press coverage is almost entirely missing from the binding legal documents.

Seventeen is not enough for a real AI comparison. If you want that, the cheapest fix is widening the years. We used 2020 to 2022 and the database goes back to 1980."

---

## What I need from you

"Four things I would like your call on.

One. Is a disclosure-selected sample acceptable for this question? Private and foreign buyers can never be included, and no amount of statistical adjustment fixes that, because the documents were never filed.

Two. Should we spend the hour on the hundred and fifty passage audit before anything gets written up as a finding?

Three. The executive theme mixes real contract terms with press release quotes. Should we drop announcements from the corpus and re-run it?

Four. Should the deal structure layer be rebuilt across all one hundred and thirty-three deals, or stay as a deep verification of ten?"

---

## Close

"Everything is on the branch. The result tables are committed, so you or anyone else can check any number in the report against the file it came from. The code has two hundred and sixty-nine tests passing and everything is green.

The single hour that would most improve this is the audit. I would like your call on whether we do that before writing anything up."

---

# If he asks

**"Why should I believe the clusters mean anything?"**

"Individually they are stable. Each one survives removing any single deal, and they survive three different configurations. But I would not claim they are the true taxonomy, because a different algorithm splits the same text differently. I would call them recurring patterns of language."

**"What is the actual contribution here?"**

"Two things. A method, which is that you should select on disclosure rather than on subject matter when the evidence is disclosure-dependent. And the infrastructure, which is fully reproducible. Every number traces back to a published file."

**"Did you find anything about retention?"**

"No, and we cannot with this data. These are contracts and announcements. A retention bonus is a contractual design, not proof that anyone stayed. Measuring retention needs employment data we do not have."

**"Why only 2020 to 2022?"**

"That is what the linked export covers for the resolved-acquirer sample. Extending the years is the cheapest way to grow the AI subgroup and it is on my list."

**"Is any of this ready to write up?"**

"The methodology and the funnel are ready. The interpretation of the clusters should wait for the audit and for a second reviewer."

**"What went wrong along the way?"**

"Two real bugs, both found and fixed. Our search window was too short and missed tender offers filed months after the announcement, one of them at day one hundred and thirty-three. And we were reading exhibit types out of a field that actually contains icon filenames, so every agreement lookup was silently failing. Both are documented."

**"How is this different from what Sreyas did?"**

"They are two separate layers and we keep them apart. His layer is rule-based human coding of what kind of transaction each deal was, on ten deals. Mine is the unsupervised text model on a hundred and thirty-three. His is not unsupervised learning and I never describe it that way."

---

# Do not say

- Do not say the model "discovered" the themes. Say it grouped recurring language.
- Do not say any company retained employees or treated them well. You have no outcome data.
- Do not call anything a finding. Say provisional, until the audit is labelled.
- Do not describe the deal structure layer as unsupervised. It is rule-based coding.
- Do not say the sample represents acquisitions generally. It is disclosure-selected, by design.
