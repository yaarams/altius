# Requirements Document

## Introduction

The Investor Document Platform automates the end-to-end flow of pulling investment documents from a family-office investor portal, classifying and extracting structured data from those documents, and surfacing the data through a web frontend. The frontend provides a holdings table (current portfolio value per fund), a chat interface grounded in the downloaded reports and statements, a sync action to trigger the pipeline, and an optional files browser for audit and debugging.

The system is designed for non-technical investment-team users who need quick, trustworthy answers about their portfolio without manually opening dozens of PDFs each quarter.

---

## Glossary

- **LP (Limited Partner)**: The family office — the investor whose credentials and documents this system manages.
- **GP (General Partner)**: The fund manager who operates the investor portal and publishes documents.
- **Portal**: The GP-run web application at `fo1.altius.finance` where the LP logs in to access deal documents.
- **Deal**: A named investment opportunity listed in the portal; each deal has one or more associated files.
- **Capital Account Statement**: A structured, tabular document reporting one LP's position in a fund as of a specific date. Contains fields such as amount committed, contributed, distributed, and current value of the stake.
- **Report**: A longer, narrative document covering portfolio activity, strategy, risks, and outlook for a fund or quarter.
- **Current Value**: The present value of the LP's stake in a fund, referred to by different names across documents (e.g., "ending capital balance", "closing NAV", "partner's capital — ending").
- **Crawler**: The component that automates browser interaction with the portal to discover and download files.
- **Classifier**: The component that labels each downloaded file as `capital_account_statement`, `report`, or `other`.
- **Extractor**: The component that parses capital account statements and outputs structured fields.
- **Pipeline**: The sequential execution of Crawler → Classifier → Extractor triggered by the Sync action.
- **Corpus**: The full set of downloaded reports and capital account statements available to the Chat component.
- **Vector Store**: An embedding-indexed store used for semantic retrieval over the Corpus.
- **System**: The Investor Document Platform as a whole.
- **Backend**: The Python server that orchestrates the Pipeline and serves the API.
- **Frontend**: The browser-based web application the investment team uses.
- **Database**: The persistent store (Postgres or SQLite) tracking files and extracted data.

---

## Requirements

### Requirement 1: Portal Authentication

**User Story:** As the investment team, I want the system to authenticate with the investor portal using configured credentials, so that it can access deal documents on behalf of the family office.

#### Acceptance Criteria

1. WHEN the Sync action is triggered, THE Crawler SHALL log in to the portal at `fo1.altius.finance` using credentials supplied via environment variables.
2. IF login fails due to incorrect credentials, THEN THE Crawler SHALL abort the sync and surface an authentication error message to the Frontend as a sync-job status update before downloading any files.
3. IF the portal session expires during a crawl, THEN THE Crawler SHALL attempt re-authentication up to 3 times and, if successful, resume from the last successfully completed deal.
4. IF re-authentication fails after 3 attempts, THEN THE Crawler SHALL abort the sync and surface a session-expiry error message to the Frontend as a sync-job status update.
5. THE Crawler SHALL store no credentials in source code or any committed file, and SHALL NOT log credential values at any log level.

---

### Requirement 2: Deal Discovery and File Enumeration

**User Story:** As the investment team, I want the crawler to walk the full deal hierarchy in the portal, so that every available file is discovered and considered for download.

#### Acceptance Criteria

1. WHEN authenticated, THE Crawler SHALL enumerate all deals listed on the portal's deal index page.
2. FOR EACH deal, THE Crawler SHALL navigate to the deal's file listing and enumerate all files associated with that deal.
3. THE Crawler SHALL record the deal name, file name, and portal URL for every discovered file in the Database before attempting to download.
4. IF a deal page fails to load after the configured number of retries, THEN THE Crawler SHALL log the failure with the deal name and HTTP status or error message, skip the deal, and continue enumerating remaining deals.
5. WHEN deal enumeration completes, THE Crawler SHALL have recorded at least one file entry per successfully loaded deal in the Database before proceeding to downloads.

---

### Requirement 3: Idempotent File Download

**User Story:** As the investment team, I want re-running the sync to be safe, so that it never creates duplicate records, duplicate downloads, or redundant extraction work.

#### Acceptance Criteria

1. WHEN a file is discovered, THE Crawler SHALL check the Database for an existing record matching the portal URL and file name (case-sensitive, exact match on both fields) before downloading.
2. IF a matching record already exists in the Database with status `downloaded` or `extracted`, THEN THE Crawler SHALL skip the download for that file.
3. WHEN a new file is downloaded successfully, THE Crawler SHALL record it in the Database with status `downloaded` and a UTC download timestamp.
4. IF a download fails, THEN THE Crawler SHALL record the file in the Database with status `failed` and continue with remaining files without marking the file as successfully downloaded.
5. WHEN the Sync action is re-run, THE System SHALL not re-extract data for files already marked `extracted` in the Database.
6. WHEN the Sync action is re-run, THE Crawler SHALL retry the download for any file whose existing Database record has status `failed`.

---

### Requirement 4: File Classification

**User Story:** As the investment team, I want every downloaded file to be labeled with its document type, so that the pipeline routes it correctly and the team can audit the classification.

#### Acceptance Criteria

1. WHEN a file is downloaded, THE Classifier SHALL assign it one of three labels: `capital_account_statement`, `report`, or `other`.
2. THE Classifier SHALL produce a confidence score in the range [0.0–1.0] for each classification.
3. IF the confidence score for a classification is below 0.75, THEN THE Classifier SHALL flag the file as `low_confidence` in the Database.
4. WHEN a sync run completes, THE Backend SHALL include in the sync result summary the total count of `low_confidence` files, plus the file name, assigned label, and confidence score for each such file.
5. THE Classifier SHALL store the assigned label and confidence score in the Database for every classified file.
6. WHILE a sync run is in progress, THE Classifier SHALL classify files without requiring manual user input.
7. IF a file cannot be classified due to a parse error or service failure, THEN THE Classifier SHALL record the label as `unclassified` and the confidence score as 0.0 in the Database, and SHALL include the file in the sync result summary failure count with a human-readable reason.
8. IF a file already has a classification label recorded in the Database (any label including `unclassified`), THEN THE Classifier SHALL skip re-classification of that file on subsequent sync runs.

---

### Requirement 5: Capital Account Statement Extraction

**User Story:** As the investment team, I want structured data extracted from every capital account statement, so that the holdings table can display accurate, up-to-date fund values.

#### Acceptance Criteria

1. WHEN a file is classified as `capital_account_statement`, THE Extractor SHALL extract: fund name, statement date, and current value of the LP's stake.
2. THE Extractor SHALL recognise variant field labels for current value, including but not limited to: "ending capital balance", "closing NAV", "partner's capital — ending", and "net asset value".
3. IF the Extractor cannot determine the current value from a statement, THEN THE Extractor SHALL record an extraction failure in the Database with a human-readable reason, and SHALL NOT store any partial extracted fields for that statement.
4. IF the Extractor cannot determine the statement date, THEN THE Extractor SHALL record an extraction failure in the Database with a human-readable reason, and SHALL NOT store any partial extracted fields for that statement.
5. THE Extractor SHALL store extracted fields (fund name, statement date in ISO 8601 format, current value) in the Database linked to the source file record.
6. WHEN a fund name appears in multiple statements, THE Database SHALL retain all statement records; the holdings query SHALL return only the record with the most recent statement date per fund, using case-insensitive and whitespace-normalized fund name matching, with the highest file ID as a tie-breaker when two records share the same statement date.

---

### Requirement 6: Sync Action and Pipeline Orchestration

**User Story:** As the investment team, I want a sync button in the UI that runs the full pipeline and shows live progress, so that I know when documents have been updated without refreshing the page.

#### Acceptance Criteria

1. THE Frontend SHALL display a sync control (button or header item) that is accessible from every page.
2. WHEN the sync control is activated, THE Frontend SHALL send a pipeline-trigger request to the Backend without reloading the page, and SHALL disable the sync control for the duration of the pipeline run.
3. WHILE the pipeline is running, THE Frontend SHALL display a progress indicator updated via server-sent events or polling no less frequently than every 5 seconds, showing the current stage as one of: "Crawling", "Classifying", "Extracting", or "Indexing".
4. WHEN the pipeline completes successfully, THE Frontend SHALL display a success summary including the count of new files downloaded, classified, and extracted, and SHALL re-enable the sync control — all without requiring a page refresh.
5. IF the pipeline fails at any stage, THEN THE Frontend SHALL display a failure message identifying the stage ("Crawling", "Classifying", "Extracting", or "Indexing") and the error cause, and SHALL re-enable the sync control — all without requiring a page refresh.
6. THE Backend SHALL prevent concurrent pipeline runs; IF a sync is already in progress and a second trigger is received, THEN THE Backend SHALL return an HTTP 409 status with a body indicating the pipeline is already running, and THE Frontend SHALL display a message that a sync is already in progress without disabling or hiding the sync control.

---

### Requirement 7: Holdings Page

**User Story:** As the investment team, I want a holdings page showing one row per fund with the latest value and statement date, so that I can immediately see the current portfolio worth.

#### Acceptance Criteria

1. THE Holdings page SHALL display a table with one row per fund.
2. EACH row SHALL show at minimum: fund name, current value of the LP's stake formatted as a currency amount with two decimal places and a currency symbol, and the statement date the value was sourced from displayed in a human-readable format (e.g., "March 31, 2025").
3. THE Holdings page SHALL display only the most recent statement per fund — when multiple statements exist for the same fund, only the record with the latest statement date SHALL appear, consistent with the fund name matching and tie-breaking rules in Requirement 5.
4. WHEN no statements have been extracted, THE Holdings page SHALL display an empty-state message prompting the user to run a sync.
5. WHEN a sync completes and new statements are extracted, THE Holdings page SHALL reflect the updated data without requiring a full page reload.
6. WHEN a statement's current value cannot be displayed (e.g., extraction failure), THE Holdings page SHALL display a clearly labeled placeholder (e.g., "—" or "N/A") in the value cell rather than leaving it blank or showing a raw error.

---

### Requirement 8: Chat Page

**User Story:** As the investment team, I want a chat interface over the downloaded reports and statements, so that I can ask natural-language questions and get grounded, cited answers without reading every PDF.

#### Acceptance Criteria

1. THE Chat page SHALL accept natural-language questions submitted by the user via Enter key or a visible submit button.
2. WHEN a question is submitted, THE Frontend SHALL display a loading indicator, and THE Backend SHALL retrieve the most semantically relevant passages from the Corpus using the Vector Store and construct an answer grounded in those passages within 60 seconds; IF the response exceeds 60 seconds, THE Frontend SHALL display an error message and allow the user to resubmit.
3. EVERY answer produced by the Chat component SHALL cite the source file name(s) and the reporting period(s) the answer draws from.
4. THE Frontend SHALL render each citation as a reference displaying the source file name and reporting period, with a link that opens the original file.
5. IF the LLM determines that no retrieved passage supports an answer to the question, THEN THE Chat component SHALL respond stating that the information is not available in the downloaded documents.
6. THE Chat component SHALL support cross-quarter synthesis questions that require drawing from multiple documents or reporting periods.
7. WHEN the Corpus is updated after a sync, THE Vector Store SHALL index newly added documents so they are available for retrieval in subsequent queries.
8. THE Chat component SHALL retrieve a bounded set of relevant passages per query (no more than 20 passages) rather than including the full Corpus in the prompt.
9. IF the Vector Store is unavailable when a question is submitted, THEN THE Backend SHALL return an error response and THE Frontend SHALL display a message indicating the chat service is temporarily unavailable.

---

### Requirement 9: Files Page (Bonus)

**User Story:** As the investment team, I want a files page listing every downloaded file, so that I can audit what was pulled and spot-check classifier output.

#### Acceptance Criteria

1. THE Files page SHALL list every file recorded in the Database.
2. EACH file entry SHALL display: file name, detected document type, source deal name, download date, and confidence score as a numeric value in the range 0.00–1.00.
3. EACH file entry where the confidence score is below 0.75 SHALL display a visible badge or icon indicating low confidence; entries with a confidence score of 0.75 or above SHALL NOT display that badge or icon.
4. WHEN a user activates the open/download control on a file entry, THE Frontend SHALL open the original file in a new browser tab.
5. WHEN the Files page loads, THE Frontend SHALL display file entries sorted by download date in descending order by default; WHEN a user activates a column sort control for document type, THE Frontend SHALL re-sort the list by document type in ascending alphabetical order.

---

### Requirement 10: Document Parsing and Round-Trip Fidelity

**User Story:** As a developer, I want the PDF parsing layer to reliably extract text and structured fields, so that classification and extraction produce consistent results across heterogeneous document layouts.

#### Acceptance Criteria

1. THE Extractor SHALL parse PDF files to extract raw text before applying field-detection logic.
2. THE Extractor SHALL handle multi-page PDF documents without truncating content from any page.
3. WHEN a valid capital account statement PDF is parsed and the extracted fields are formatted into the Extractor's canonical structured output, then that output is parsed again by the same Extractor, THE resulting structured data SHALL match the original extraction exactly — same field names, same count, and same values — with no fields added or dropped.
4. IF a PDF cannot be opened or parsed, THEN THE Extractor SHALL record a parse failure in the Database including the file identifier and a description of the failure reason, and SHALL NOT attempt field extraction on that file.
5. IF parsing starts but fails mid-document, THEN THE Extractor SHALL discard any partially extracted data and SHALL NOT write partial results to the Database.

---

### Requirement 11: Database Integrity and Queryability

**User Story:** As a developer, I want a well-structured database that tracks the full lifecycle of every file, so that the pipeline is idempotent and extracted data is reliably queryable.

#### Acceptance Criteria

1. THE Database SHALL maintain a `files` table (or equivalent) with columns for: unique file ID, portal URL, deal name, file name, download timestamp, classification label, confidence score (numeric, range 0.0–1.0), low-confidence flag, extraction status (one of: `pending`, `downloaded`, `extracted`, `failed`), and extraction error message.
2. THE Database SHALL maintain a `statements` table (or equivalent) with columns for: unique statement ID, linked file ID, fund name, statement date, and current value.
3. THE Database SHALL enforce a uniqueness constraint on (portal URL, file name) in the files table to prevent duplicate records.
4. THE System SHALL support querying the latest statement per fund in a single database query, where "latest" is defined as the row with the maximum `statement_date` value per fund name, without application-level filtering across the full result set.
5. WHEN the Backend starts, THE System SHALL apply any pending database migrations automatically before accepting requests.
6. IF a database migration fails at startup, THEN THE Backend SHALL log a clear error identifying the failed migration and SHALL exit before accepting any requests.

---

### Requirement 12: Configuration and Secrets Management

**User Story:** As a developer, I want all credentials and environment-specific settings managed via environment variables, so that the system can be configured without changing code and secrets are never committed.

#### Acceptance Criteria

1. THE System SHALL read portal credentials (username, password) exclusively from environment variables.
2. THE System SHALL read LLM API keys and Vector Store connection details exclusively from environment variables.
3. THE System SHALL read the database connection string exclusively from environment variables.
4. THE Backend SHALL provide a `.env.example` file listing every environment variable required at startup, each with a non-functional, clearly fake placeholder value (e.g., `PORTAL_PASSWORD=your-portal-password-here`) and no real secret values.
5. IF one or more required environment variables are missing at startup, THEN THE Backend SHALL log a single error message that lists every missing variable by its exact variable name and SHALL exit before accepting any requests.
6. IF a required environment variable is present but its value is an empty string, THEN THE Backend SHALL treat it as missing and apply the behavior specified in criterion 5.
