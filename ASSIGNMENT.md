# Full-Stack Take-Home: Investor Document Platform

## Background

Private equity funds work like this: investors (called **limited partners**, or LPs) commit money to a fund run by a manager (the **general partner**, or GP). The GP takes that money, invests it in private companies, holds those positions for years, and eventually sells them and returns the proceeds. Because there's no public market price for any of this, the GP is responsible for telling each LP, every quarter, what their stake is currently worth and what's been going on with the fund.

That communication happens through two kinds of document:

- **Capital account statements** — short, tabular. Report one LP's position in the fund as of a date: amount committed, contributed, distributed, and the current value of the stake. The holdings table is built from these.
- **Reports** — longer, narrative. Cover portfolio activity, strategy, risks, and outlook. The chat is grounded in these.

Both arrive through **investor portals**: GP-run web apps where the LP logs in and downloads files for the funds they're invested in. Think Dropbox per GP. There is no standard — every portal looks different.

## Your Task

Build a small web app for a family office that automates this whole flow end-to-end. Specifically:

1. Pulls files from an investor portal on demand by automating the login, navigation, and download flow.
2. Classifies each downloaded file and extracts structured data from the capital account statements.
3. Surfaces the data through a frontend with a holdings table and a chat that can answer questions over the reports.

## What We Provide

A test investor-portal login:

| Site | Username | Password |
|---|---|---|
| `fo1.altius.finance` | (Sent separated) | (Sent separated) |

The portal contains a mix of capital account statements, reports, and other files for the funds the office is invested in.

## Requirements

The data pipeline:

- **Crawler.** The portal has no API — it's a website with a login screen, a list of deals, and per-deal file listings. The crawler has to drive it like a user would: log in, walk the deal hierarchy, and download every file it hasn't seen before. Tool of your choice (Playwright, Selenium, plain HTTP). Be ready to defend the choice. Sync must be **idempotent** — re-running it shouldn't re-download known files, duplicate rows, or re-do extraction work.
- **Classifier.** Labels every downloaded file as one of:
  - **Capital account statement** — the position-level documents the holdings table feeds from.
  - **Report** — narrative documents that feed the chat.
  - **Other** — anything else the portal serves (tax forms, capital call notices, side-letter amendments, marketing decks, etc.). Recorded but not processed further.

  LLM, heuristics, or hybrid — your call. Files the classifier isn't confident about should be visible, not silently bucketed.
- **Extractor.** For each capital account statement, pull at minimum: fund name, statement date, and current value of the LP's stake. Different documents call this last field different things ("ending capital balance", "closing NAV", "partner's capital — ending", etc.) — all the same concept.
- **Database.** Postgres, SQLite, anything. The two things that matter: every file and its type are tracked, and extracted statement data is queryable.

The frontend — a small web app a non-technical user opens in a browser. It has the following:

- **A sync action** (button, header item, however you want to surface it). Triggers the pipeline above for the configured portal, shows the user that something is happening, and reports success or failure when it's done. The user shouldn't have to refresh the page to see results.
- **A chatbot page.** A chat interface over the corpus of downloaded reports and statements. Reports are dense, repetitive across quarters, and mix narrative commentary (strategy, risks, governance, macro views) with financial data — skimming dozens of PDFs to answer one question is slow. The chatbot should let a user ask natural-language questions including cross-quarter synthesis like *"how did the fund's risk posture evolve in 2023?"*, *"which quarters mentioned the subscription credit facility?"*, or *"what was the manager's commentary on valuations in Q1 2025?"*. Every answer must cite the source file(s) and the relevant reporting period(s), and the user should be able to trace citations back to the original document. Out-of-corpus questions should be answered honestly, not fabricated.
- **A holdings page.** A table of every fund the office is invested in, one row per fund. Each row shows at least: fund name, current value of the office's stake, and the statement date that number came from. This is the page the investment team checks to know "what's our portfolio worth right now."
- **(Bonus) A files page.** A list of every downloaded file with its detected type, source deal, download date, and a way to open it. Useful for the user to spot-check what was pulled, and for you to debug the classifier.

Python backend, any frontend framework. Frontend visual polish is not graded — we care that the pages are clear, the holdings table is correct, and the chat is grounded.

## Sample Questions

Use these to sanity-check your chat. They're not a hidden test set — we'll ask different questions when we evaluate.

1. What was the manager's commentary on valuations in Q1 2025?
2. How did the manager describe the use of the subscription credit facility across 2024?
3. Which quarters mentioned material write-downs or impaired investments?
4. Has the fund's strategy shifted between 2022 and 2025?
5. What is the fund's policy on quarterly dividend distributions to LPs? *(Likely not in the corpus — see how your chat handles it.)*

## How We'll Evaluate

Roughly in order of importance:

- **Does it work end-to-end?** Login, walk deals, download without duplicates. Holdings table populated correctly from the statements. Chat answers report questions with real citations.
- **Quality of extraction.** The "current value" field comes out correctly across heterogeneous statement layouts. We spot-check against the source PDFs.
- **Quality of retrieval.** Answers stay grounded in the documents. Citations are real. The system doesn't stuff everything into one prompt.
- **Honest handling of failure.** Bad credentials, parser failures, low-confidence classifications are visible — not silently dropped or guessed.
- **Quality of thinking.** Your README should make us understand *why* you built it the way you did. Honest tradeoffs over long feature lists.

We are **not** grading: frontend polish, production readiness (auth, observability, rate limits), test coverage as a number.

## Deliverables

A Git repo (private GitHub / GitLab / Bitbucket shared with the addresses we sent you, or a zip) containing:

1. **Source code.**
2. **`README.md`** with:
   - Setup and run instructions.
   - A short architecture overview.
   - The three or four most interesting design decisions and why.
   - A short note on what you'd improve or evaluate more rigorously with more time.
3. **`.env.example`** showing the expected environment variables (no real keys).

We'll then schedule a ~45-minute follow-up to walk through the code and your decisions.

## FAQ

**Do I need to handle non-PDF formats?**
PDF is enough.

**The PDFs have very different layouts — is that intentional?**
Yes. Real GPs don't coordinate on formats.

**Can I stub the crawler for local development?**
Sure — cache the responses or work off a local copy if it speeds you up. But the submitted system must run the live crawler end-to-end. We will sync against the portal when we evaluate.

**What if the classifier isn't sure?**
Real portals serve genuinely ambiguous files. Tell us how your system handles low-confidence classifications. Silently picking one bucket is worse than surfacing the uncertainty.

**Can I use a vector DB / embeddings library?**
Yes. Anything off-the-shelf is fine. Be ready to explain why you picked what you picked.

**What if the same fund appears in multiple statements?**
That happens. The holdings table should always show the latest one per fund.

Good luck.
