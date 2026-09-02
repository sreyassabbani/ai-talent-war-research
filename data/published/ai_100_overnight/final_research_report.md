# AI-Transaction Employee-Disclosure Research Report

## Research question

How do source-backed AI-related transactions publicly describe employee, team, compensation, equity, retention, termination, and integration arrangements?

## Scope and inclusion

The discovery manifest contains 119 candidate transactions. Deterministic primary-source screening marked 35 as machine-qualified and pending human review, against a target of 100. The remaining shortfall is 65; no generic merger was added to pad the sample.

Legal transaction form and talent motive are stored separately. SEC filings are primary evidence; rows without source-backed AI evidence remain nonqualifying or unresolved.

## Corpus and method

The run retrieved 1402 documents and constructed 72 unique employee-related passages while preserving source occurrences and zero-passage states. The primary unsupervised method is fixed-seed word/bigram TF-IDF plus NMF over K=[3, 4, 5, 6, 7]. Document-family lexical baselines control for standardized drafting language. Tone results are transparent per-100-token lexical rates and describe writing style, not mental states.

## Topic status

Topic analysis status: `exploratory_rejected_deal_concentration`. All themes remain provisional until source-linked representative passages receive human review.

| Provisional topic | Top terms | Stability |
|---|---|---:|
| topic_5787d58e | zebra technologies; technologies; zebra; workers; front; front line; line; productivity; worker; worker productivity; line workers; productivity zebra | 0.2464 |
| topic_1a765e60 | workforce; management; workforce management; nucleus; research; nucleus research; research workforce; value matrix; matrix; technology value; management technology; leader nucleus | 0.2464 |
| topic_0036981e | ai; founder; ceo; founder ceo; data; said; glia; platform; co; co founder; customers; technology | 0.2464 |

## Representative source evidence

- **Alphabet Inc–Kaggle Inc** (2017-03-08): [supp_327ff1ecfdd9a623](https://blog.google/innovation-and-ai/infrastructure-and-cloud/google-cloud/100-announcements-google-cloud-next-17/) — acquisitions to the Google Cloud family this week, Kaggle and AppBridge. 1 . Kaggle - Kaggle is one of the world's largest communities of data scientists and machine learning enthusiasts. Kaggle and Google Cloud will continue to support machine learning training and deployment services in addition to offering the community the ability to store and query large datasets. 2 . AppBridge - Google Cloud acquired Vancouver-based AppBri
- **HubSpot Inc–Motion Ai Inc** (2017-09-20): [supp_6bb6449c48074311](https://www.hubspot.com/company-news/hubspot-acquires-motion-ai-one-of-the-top-visual-chatbot-builders) — d Nelson, founder and CEO of Motion AI. "We're excited to be joining the HubSpot team, and can't wait to get to work on some really innovative AI tools." The Motion AI technology will be incorporated into the HubSpot platform over the next several months, with the team working to create tools that help users automate important tasks, scale conversations, and proactively engage and acquire new customers.
- **Smartsheet Inc–Converse.AI Inc** (2017-12-28): [supp_afd5f3e53a041df6](https://www.smartsheet.com/content-center/news/smartsheet-announces-converseai-natural-language-automation-acquisition) — e to hire in order to meet growing customer demand. Existing Converse.AI customer relationships and agreements will not be impacted by the acquisition, and the Converse.AI platform will continue to be supported. About Smartsheet Organizations need a way to get work done, not just talk about it. Smartsheet is the best way to plan, track, automate, and report on work, enabling you to move from idea to impac
- **Leanplum Inc–Connecto.ai** (2018-06-19): [supp_2d6e94103484791d](https://www.prnewswire.com/news-releases/leanplum-acquires-connecto-a-conversational-marketing-company-300668664.html) — SAN FRANCISCO , June 19, 2018 /PRNewswire/ -- Leanplum , the leader in mobile engagement, today announced the acquisition of Connecto, a provider of AI-powered conversational marketing. With this acquisition, Leanplum is taking the next step forward in transforming the relationship between brands and their customers. By bringing together Connecto's AI-driven automation with Leanplum's mobile enga
- **Facebook Inc–Bloomsbury AI Ltd** (2018-07-03): [supp_0ba198132a3ce9ce](https://about.fb.com/news/2018/07/facebook-ai-research-expands/) — Also joining us in London is the team behind Bloomsbury AI, which we announced earlier this month. They have a strong background in natural language processing.
- **Box Inc–Butter AI Corp** (2018-07-10): [supp_0efd95a26b6f4ecc](https://blog.box.com/welcome-butter-ai-team-Box) — We're incredibly excited to share that the team from Butter.ai is joining Box to help us execute on our vision to bring intelligent search to the enterprise. Butter.ai, a member of All Turtles, has been focused on using machine learning to solve everyday problems.
- **Microsoft Corp–Lobe Artificial Intelligence** (2018-09-13): [supp_eee385ba990d0f07](https://blogs.microsoft.com/blog/2018/09/13/microsoft-acquires-lobe-to-help-bring-ai-development-capability-to-everyone/) — Today, we’re excited to announce the acquisition of Lobe. Based in San Francisco, Lobe is working to make deep learning simple, understandable and accessible to everyone.
- **Sensory Inc–Vocalize AI Inc** (2019-02-13): [supp_4b9aa9fc3ba3f604](https://sensory.com/news/sensory-acquires-vocalize-ai-for-speech-technology-testing-capabilities/) — g need for an independent evaluation service and software tools that ensure a quality user experience. It’s exciting to have access to the deep bench of AI and machine learning talent and resources of Sensory. It is also important to recognize that Vocalize.ai will operate as an independent company under the Sensory umbrella. In this model, we will continue to provide quality evaluations and competitive benchmarking services for the entire voice-enabled industry.” Sensory’s clients will ben
- **Navicure Inc–Digitize.AI Inc** (2019-06-21): [supp_24e34863bc502dcb](https://www.waystar.com/news/waystar-acquires-digitize-ai-to-automate-prior-authorization/) — Waystar announced the acquisition of Digitize.AI, an artificial intelligence technology firm. Digitize.AI leverages artificial intelligence and machine learning to automate prior authorizations.
- **Hitachi Ltd–Waterline Data Science Inc** (2020-01-22): [supp_481be70c17b4acbe](https://www.hitachivantara.com/pt-br/news-old/gl200122) — Waterline Data delivers catalog technology enabled by machine learning (ML) that automates metadata discovery to solve modern data challenges for analytics and governance.
- **Nylas Inc–June.Ai** (2020-03-17): [supp_0d563879c627e619](https://www.nylas.com/blog/nylas-juneai-acquisition/) — kflow features into their application in a fraction of the time. Today, we’re excited to announce the next big milestone on that journey: our acquisition of June.ai, a powerful email and productivity tool that combines AI/ML, data extraction, and sentiment analysis to improve the experience of reading and replying to email. Integrating June.ai’s core technology with Nylas’ universal email, calendar, and contacts APIs will enable developers to create sophis
- **Niantic Inc–6D.ai** (2020-03-31): [supp_90ae73638955701d](https://medium.com/6d-ai/6d-ai-joins-niantic-making-a-major-step-toward-building-the-ar-cloud-1594be62e85f) — When Victor and I first started 6D.ai, our mission was to solve the hardest computer vision software problems preventing developers from building engaging AR applications.
- **365 Retail Markets LLC–Stockwell AI Inc** (2020-08-13): [supp_483684a4076e1a42](https://365retailmarkets.com/blog/365-retail-markets-acquires-stockwell) — Troy, Michigan– August 13, 2020 –365 Retail Markets announced today the acquisition of the smart-store technology company, Stockwell of Oakland, California. Stockwell has gathered some of the best minds to build a retail platform that focuses on artificial intelligence, machine learning, and computer vision. 365 intends to hire select team members and integrate the technology platform into its industry-leading 365 Point of Sale systems. “The future of retail is unattended, no doubt. By adding th
- **W2O Group–IPM.ai Inc** (2021-01-07): [supp_a47910b5436bd97a](https://swoop.com/blog/w2o-acquires-swoop/) — W2O announced it acquired Swoop and IPM.ai. Swoop and IPM.ai are pioneers in using artificial intelligence and real world data to solve healthcare challenges.
- **Algolia Inc–MorphL AI Inc** (2021-01-26): [supp_f27a205c0a017de2](https://www.globenewswire.com/news-release/2021/01/26/2164201/0/en/Algolia-Acquires-MorphL-Launches-AI-Powered-Predictive-Experiences-and-Personalization.html) — Algolia Acquires MorphL, Launches AI-Powered Predictive Accessibility: Skip TopNav Consumer Products and Ser
- **FleetCor Technologies Inc–Roger.ai Inc** (2021-01-28): [supp_5c5e3c455537ea83](https://www.corpay.com/corporate-newsroom/14201/fleetcor-acquires-cloud-software-platform-provider-of-b2b-online-bill-payment) — FLEETCOR announced it acquired Roger, an accounts-payable cloud platform. Roger eliminates manual data entry using machine learning technology.
- **AppHarvest Inc–Root AI Inc** (2021-04-08): [supp_f56ffb1c8870a6f6](https://www.globenewswire.com/news-release/2021/04/08/2206486/0/en/appharvest-acquires-agricultural-robotics-and-artificial-intelligence-company-root-ai-to-increase-efficiency.html) — More Browse the Latest News AppHarvest Acquires Agricultural Robotics and Artificial Intelligence Company Root AI to Increase Efficiency April 08, 2021 06:00 ET | Source: AppHarvest AppHarvest Acquisition of Root AI and its signature robot, Virgo, bolsters company’s intelligent tools
- **Life Clips Inc–Cognitive Apps Software** (2021-04-15): [supp_f0f18f18d45e2547](https://www.globenewswire.com/news-release/2021/04/06/2204941/0/en/Life-Clips-Closes-Transaction-to-Acquire-Cognitive-Apps-Software-Solutions-Inc.html) — Life Clips closed the acquisition of Cognitive Apps Software Solutions, a developer of artificial intelligence applications for healthcare and psychedelic research.
- **Liveaction Inc–CounterFlow AI Inc** (2021-05-04): [supp_bfe94cddfded4cfb](https://www.liveaction.com/press/liveaction-acquires-counterflow-ai-to-expand-network-security-offerings/) — CounterFlow AI’s unique security portfolio will help LiveAction partners and customers gain end-to-end network visibility. Its Streaming Machine Learning Engine processes packet data in real-time.
- **SkySpecs Inc–Vertikal AI ApS** (2021-05-17): [supp_c0a01e7012c4bb9e](https://skyspecs.com/blog/skyspecs-acquires-fincovi-and-vertikal-ai/) — SkySpecs acquired Vertikal AI, a pioneer in predictive maintenance for wind energy. Vertikal AI uses data analytics and applied AI to optimize wind-turbine health.

## Limitations and conclusion

This is a selected public-disclosure sample, not a representative census of AI transactions. Private documents, unfiled employment terms, and later employee outcomes are often not observable. The results are descriptive and exploratory. A disclosed retention provision does not establish that an employee stayed, and silence does not establish that no arrangement existed.

The current run did not reach the 100-deal target. Machine-qualified rows still require human evidence review before being called verified deals.

## Reproduction

```powershell
.venv\Scripts\python.exe -m tag_edgar.overnight --candidates data\derived\ai_100_candidate_preflight.csv --raw-dir data\raw\ma_events --out-dir data\derived\ai_100_overnight --supplemental-sources config\ai_100_supplemental_sources.csv --include-reserves
```
