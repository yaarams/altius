# Portal Recon Findings — fo1.altius.finance

**Date:** 2026-06-24
**Method:** Live Playwright session, authenticated, network inspection.
**Outcome:** Crawler strategy de-risked. One conflict with approved plan surfaced (CONF-3, idempotency key).

---

## 1. Portal nature
- The portal is the **Altius SaaS deal-management platform itself** (not a bespoke file portal). React SPA.
- Login at `/login`. Standard **email + password** form works (also offers "Easy Login" email-OTP and "SSO" — not needed, we have a password).
- After login → `/main/my-deals`. Deal → `/main/deal/{id}` → `/main/deal/{id}/workspace`.
- Hierarchy: **My Deals → Deal → Workspace → Folder → Files** (workspace table shows a FOLDER row with nested items).

## 2. THERE IS A JSON API (assignment said "no API")
Backed by `https://fo1.api.altius.finance/api/v0.0.x/`. Auth = **httpOnly session cookie** set at login (no bearer token; cookie auto-attached). Key endpoints observed:

| Method | Endpoint | Returns |
|---|---|---|
| POST | `/api/v0.0.2/deals-list` | all deals (filter body) |
| GET | `/api/v0.0.2/deals/{id}` | deal detail |
| GET | `/api/v0.0.3/deals/{id}/folders` | folder tree |
| GET | `/api/v0.0.3/deals/{id}/files` | **all files for deal (the gold)** |
| GET | `/api/v0.0.3/documents?deal_id={id}` | documents |
| GET | `/api/v0.0.3/files/document-types` | type taxonomy |
| GET | `/api/v0.0.2/users/session` | session/whoami |

### `/deals/{id}/files` response shape
- Top-level `{"data": { "<file_id>": {…}, … }}` — **object keyed by stable integer file id**.
- Per-file fields (35): `id`, `name`, `file_url`, `document_type`, `document_type_altius`, `type`, `date`, `size_in_bytes`, `deal_id`, `created_at`, `updated_at`, `state`, `extraction_status`, `tags`, `is_private`, `section_id`, …
- **`file_url` = presigned S3 URL** (`altius-staging-files.s3.eu-west-2.amazonaws.com/...?X-Amz-Signature=…&X-Amz-Expires=3600`). **Expires in 1h, regenerated on every API call** → no auth needed on the URL itself, but it is NOT a stable identifier.
- `document_type` = portal's own label ("Capital account" / "Quarterly update" / null). `date`, `document_type_altius` = null in this dataset.

## 3. The actual corpus (deal 10495)
- **40 PDFs, 1 deal, 6 funds** (alpha, beta, gamma, delta, epsilon, zeta). All `type=pdf`.
- By portal `document_type`:
  - **8 Capital account statements** (holdings source). Heterogeneous names: `... - Capital Statement - 2025-09-30`, `_Statement_2025Q3`, `_CAS_Sep2025`, `_Q3_2025_CapitalAccount`, `_capacct_q3_2025`.
  - **30 Quarterly-update reports** (chat source). Names: `_fs_commentary`, `Quarterly Update`, `_letter_qN`, `_FS_Commentary`, `_update`.
  - **2 unlabeled junk** (`345.pdf`, `7470-01-136 - 3 2021.pdf`) → the deliberate **"other" / low-confidence** test cases.
- Funds span quarters 2021–2025 → cross-quarter chat questions are answerable.
- Portal `document_type` gives us **free eval ground-truth** to measure our classifier (we still classify ourselves per the assignment).

## 4. Crawler strategy (de-risked)
**Recommended: Playwright login + Playwright `APIRequestContext` (`page.request`) against the internal JSON API.**
- Login via browser (robust to whatever the SPA login does; cookie managed automatically).
- Then call `/deals-list` → `/deals/{id}/files` using the same authenticated context (cookies shared).
- Download each `file_url` (presigned S3 GET) promptly (<1h).
- **Avoids** scraping the heavy SPA workspace table with nested folders. **Avoids** reverse-engineering the login POST for pure-httpx.
- Defensible: "logged in like a user, then consumed the same internal JSON API the SPA uses — more robust and faster than DOM scraping."

## 5. ⚠️ CONF-3 — Idempotency key must change
- Approved plan (design.md + PRD R11.3) uses **UNIQUE `(portal_url, file_name)`**.
- **Problem:** `file_url` (portal_url) is a **presigned URL that rotates every call** → never stable. File names also carry `(1)` suffixes and could collide across funds.
- **Fix:** idempotency / skip key = the API's **stable integer `file id`** (e.g. `22064`) → store as `external_file_id` UNIQUE. Keep `(deal_id, name)` as secondary. This is the only safe dedup key.
- **Impact:** small schema change (`files.external_file_id` UNIQUE instead of/in addition to `portal_url,file_name`); updates ADR-007, R3.1/R11.3, Property 13. Needs user sign-off (conflicts with approved authoritative docs).

## 6. Residual risks (post-recon)
- R1 "portal unknown" → **largely retired** (mapped end-to-end).
- New: presigned URL 1h expiry → enumerate-then-download promptly; don't cache URLs.
- New: API version mix (`v0.0.2` deals-list vs `v0.0.3` files) → pin per-endpoint versions.
- Login flow could change (OTP/SSO enforced later) → Playwright login keeps us robust.

## 7. Suggested plan delta → v2.1
1. ADR-002 → confirm **Playwright + APIRequestContext over internal JSON API** (not DOM scrape, not pure httpx).
2. New ADR-011: enumerate via `/deals-list` + `/deals/{id}/files`; download presigned `file_url`.
3. CONF-3: idempotency key → `external_file_id` (stable). Update schema, ADR-007, Property 13.
4. Scope facts: 40 files / 1 deal / 6 funds / 8 CAS + 30 reports + 2 other. Use portal `document_type` as classifier eval ground-truth.
5. Risk register: add presigned-expiry + API-version-pin; retire "portal unknown".
