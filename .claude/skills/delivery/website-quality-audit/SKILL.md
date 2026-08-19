---
name: bpt-website-quality-audit
description: Strategic website quality audit with iterative checkpoints. Identifies problem areas, analyzes impact, and hands off to the 12-month project plan.
---

# Website Quality Audit (WQA) — v3.2

Comprehensive page-level website audit that pulls Ahrefs + GSC + GA4 + crawl data, classifies every URL into Technical and Content workstreams, surfaces missing on-page elements + thin content + depth gaps + striking-distance opportunities, scores link-building targets, and produces a strategist-approved audit that feeds the 12-month project plan.

The skill produces deliverables in this exact order:

1. **Audit spreadsheet** (xlsx) — the master artifact. Tabs covering every URL, every recommendation, every keyword, and a scored link-building roster.
2. **Approval review** — the human-in-the-loop step where the strategist confirms, edits, rejects, or defers each recommendation AND approves the link-building roster.
3. **Visual report** (HTML) — branded client-facing report with 4 title-slide sections (Performance, Technical, Content, Links), generated *only after* approvals are parsed and confirmed. Performance data MUST be populated (see Checkpoint 2) and Chart.js is inlined so it renders offline.
4. **12-month project plan** — built in the next step (`/bpt-project-plan`) from the approved recommendations. It is NOT embedded in the report.

Each handoff requires explicit user confirmation before the next phase runs.

---

## Phase 0: Pre-Flight Check

**The moment the user says "run the WQA," do these two things up front, in parallel — before any data pulls:**

1. **Request the Screaming Frog crawl immediately, with the exact path.** It's the one thing that genuinely requires a user action, so ask for it first (don't make the user wait while you check other things). Use this message:

   > "Awesome, let's run the WQA for {Company}. Before I get started, I need a crawl of the website — I'm built for Screaming Frog. Please run a crawl of {domain}, export the **Internal → HTML** report as CSV, and drop it in this exact folder: `{AGENCY_ROOT}/clients/{slug}/crawls/` (or say the word and I'll take it via `wqa_upload_crawl`).
   >
   > In the meantime, I'll check that I have access to the platforms I need."

   **Always give the FULL absolute path** to the crawls folder (resolve `{AGENCY_ROOT}` to the real path, e.g. `/Users/.../test-workspace/clients/{slug}/crawls/`), not the relative `clients/{slug}/crawls/` — the user needs a path they can paste into Finder/Explorer. Create the folder if it doesn't exist.

2. **Check access yourself — Windsor is the default source of truth. Do NOT assume the client record holds everything.** A client (especially a freshly onboarded one) may have an empty record while Windsor is fully wired. Run the resolution in 0.1 before declaring anything missing.

Only halt for what is *genuinely* unavailable after checking.

### 0.1 Client record + agency profile — resolve from Windsor, don't assume

| Property | Location | Used for |
|----------|----------|----------|
| `vertical` | `client.vertical` | Page-type classifier |
| `ga4_property_id` | `client.ga4_property_id` | Per-URL traffic |
| `gsc_property` | `client.gsc_property` | Impressions, clicks, position, CTR |
| Ahrefs target | `client.custom_fields.ahrefs_target` | Keywords + backlinks (NOT a crawl substitute) |
| Competitor list | `client.custom_fields.competitors` (array) | Competitor data pulls (Phase 1.5) |
| Windsor accounts | `client.custom_fields.windsor_accounts.{ga4,gsc}` | Monthly time-series + period comparison |
| `agency.branding` | `agency.branding.*` | Report styling (falls back to defaults) |

**Resolution order for the analytics identifiers (`ga4_property_id`, `gsc_property`, `windsor_accounts`, GMB):**

1. Read them from the client record.
2. **If any are missing, call `windsor_list_accounts` and match this client by name and/or domain.** e.g. `googleanalytics4__Cutter Law - GA4` → GA4 `309447460`; `searchconsole__https://cutterlaw.com/` → that GSC property; `google_my_business__... <Company>` → GMB location(s). Write what you find back to the record with `clients_update` so it persists.
3. `ahrefs_target` defaults to the client website if unset.
4. `vertical` and `competitors` are **not** auto-discoverable from Windsor. If missing, offer to research and propose competitors, or ask the user — don't hard-halt on these alone.

Only block if, after checking Windsor, the GA4/GSC access genuinely isn't connected — in which case tell the user **exactly** which platform to connect in Windsor and that it lands in `custom_fields.windsor_accounts`. Branding is optional.

### 0.2 Screaming Frog crawl — HARD PREREQUISITE

**An SF crawl is the source of truth for all per-page on-page data:** title, meta description, H1, word count, inlinks, outlinks, crawl depth, indexability, canonical, status codes. **Ahrefs does NOT substitute for this.** The site-audit endpoint requires a separately-run Ahrefs Site Audit crawl that often isn't current, and `site-explorer-crawled-pages` returns only URL/status/title with no on-page content fields.

**Before any data pulls, verify** that the file exists at:

```
clients/{client-folder-slug}/crawls/latest-crawl.json
```

with at least 10 pages of data.

**If missing, halt immediately** with this message to the user:

> WQA cannot run without a Screaming Frog crawl. SF is the source of truth for per-page title, meta, H1, word count, inlinks, outlinks, and crawl depth. Ahrefs is used for keywords and backlinks only — not as a substitute.
>
> To proceed:
> 1. Run Screaming Frog SEO Spider against the client's domain.
> 2. Export the Internal HTML report (Internal > HTML).
> 3. Run `wqa_upload_crawl` OR drop the CSV into `clients/{slug}/crawls/`.
> 4. Re-run this skill.

Do NOT proceed with partial-data fallbacks. Surface the requirement clearly and wait.

---

## Phase 1: Data Collection

**Goal:** Pull every data source into the audit folder so the xlsx builder has what it needs.

### 1.1 Create the audit workspace

```
wqa_create_audit { client_id, notes }
```

Returns `audit_id` and creates the folder:

```
clients/{client-folder-slug}/wqa/audits/{audit_id}/
```

Note: the **client folder slug** (e.g. `the-blueprint-training`) may differ from the **file-prefix slug** used in output filenames (e.g. `tbt`). Scripts accept both via `--client-slug` (file prefix) and `--audit-dir` (full path to the audit folder).

### 1.2 Pull data from connected sources

Run these in parallel where possible.

| Source | Tool | Output file | `wqa_save_data_file` `file_type` |
|--------|------|-------------|-------|
| Ahrefs site audit (current pages) | *(no tool — requires a pre-configured Ahrefs Site Audit `project_id`; not wired up)* | `{slug}-ahrefs-pages.json` | — |
| Ahrefs crawled pages (status codes for every URL Ahrefs has seen) | `ahrefs_crawled_pages_raw` | `{slug}-ahrefs-crawled-pages.json` | `ahrefs-crawled-pages` |
| Ahrefs top pages (traffic/keywords/RDs per URL) | `ahrefs_top_pages_raw` | `{slug}-ahrefs.json` | `ahrefs-top-pages` |
| Ahrefs full organic keyword list | `ahrefs_keywords_raw` (limit ≥ 1000) | `{slug}-ahrefs-keywords.json` | `ahrefs-keywords` |
| Windsor GSC monthly time-series (last 16 months) | `windsor_query platform=gsc fields=date,clicks,impressions,position` | `{slug}-gsc-monthly.json` | `gsc-monthly` |
| Windsor GSC current 90d per-page | `windsor_query platform=gsc fields=page,clicks,impressions,ctr,position date_from=<90d ago>` | `{slug}-gsc-90d-current.json` | `gsc-90d-current` |
| Windsor GSC prior 90d per-page | same, date range = prior 90d | `{slug}-gsc-90d-prior.json` | `gsc-90d-prior` |
| Windsor GA4 monthly (organic + total) | `windsor_query platform=ga4 fields=date,medium,sessions,conversions` | `{slug}-ga4-monthly.json` | `ga4-monthly` |
| Windsor GA4 90d comparison (organic + total) | derived from same daily file | `{slug}-ga4-90d-compare.json` | `ga4-90d-compare` |
| Screaming Frog crawl | `wqa_upload_crawl` (not `wqa_save_data_file` — this one has its own dedicated tool) | `clients/{slug}/crawls/latest-crawl.json` | — |
| GA4 aggregate per-URL | `windsor_query platform=ga4 fields=page_location,sessions,users,engagement_rate,conversions` | `{slug}-ga4.json` | `ga4` |
| GSC aggregate per-URL | `windsor_query platform=gsc fields=page,clicks,impressions,ctr,position` | `{slug}-gsc.json` | `gsc` |

**Every pull above (except the SF crawl) must be persisted with `wqa_save_data_file { audit_id, file_type, content }` right after fetching it.** There is no automatic sync from a raw tool pull into these files — `build_audit_xlsx.py` / `build_report.py` just read hardcoded filenames off disk, so if you don't explicitly save the pull's result, the corresponding section of the spreadsheet/report will silently come back empty (not an error — just blank). Pass the tool's returned data straight through as `content`; don't re-encode it as a string.

**Aggregation note:** GA4 and GSC both return multiple rows per page (one per source/medium/query/etc). The xlsx builder **sums** by normalized URL — do not use last-wins joins, you'll drop 90%+ of homepage traffic. When saving GA4/GSC aggregate pulls via `wqa_save_data_file`, pre-aggregate to one row per URL before saving.

### 1.2a — SCOPE EVERY WINDSOR PULL TO THIS CLIENT (required)

`windsor_query` can return data for **every account connected to the agency's Windsor**, not just this client — passing `client_id` alone is not always enough. An unscoped GSC/GA4 pull both (a) leaks other clients' data into the audit and (b) returns tens of thousands of rows that overflow context. Always scope:

1. **Post-filter every GSC/GA4 pull to the client's domain — do not trust Windsor's `filter`/`account_id` params.** In testing, Windsor IGNORED `filter=[["page","contains","<domain>"]]` and `account_id` and still returned every connected client's rows. The only reliable scope is to drop rows whose `page`/`page_location` host isn't the client's bare domain (from `client.website`, strip protocol + `www.`) when you aggregate. (The rebuilt `windsor_query` MCP tool now does this post-filter server-side; until it's rebuilt, you MUST do it yourself.) You can still pass the `filter` param too — it doesn't hurt — but never rely on it.
2. **Verify scope before saving.** Spot-check the first rows of each pull — every `page`/`page_location` must be on `<domain>`. Date-only pulls (e.g. monthly with no `page` field) can't be domain-filtered at the row level — pull them WITH `page`/`page_location` and aggregate after filtering, or you'll silently sum other clients' traffic.
3. **If a pull is still too large for context** (it saves to a tool-results file and reports the path): do NOT read it inline. Hand the saved file path to a subagent that reads it in chunks, aggregates per normalized URL, and writes the compact `{slug}-gsc.json` / `{slug}-ga4.json` (one row per page) into the audit folder — keeping the raw rows out of the main context.

### 1.3 Discover legacy URLs + redirect targets

For URLs in GSC that aren't in the current crawl, HEAD-fetch to determine status (200/3xx/4xx) and redirect target. Save to `{slug}-legacy-urls.json` and `{slug}-redirect-targets.json`.

Reference implementation: `scripts/discover_redirects.py`.

---

## Phase 2: Generate Audit Spreadsheet (FIRST OUTPUT)

**Goal:** Produce a single xlsx that the strategist reviews and approves from.

**Preferred — if the `wqa_build_xlsx` MCP tool is available, use it:**

```
wqa_build_xlsx { audit_id }
```

It resolves the client slug, audit folder, and root domain automatically and runs the
builder server-side, so it works from any MCP client — including ones without Bash/file
execution access (e.g. Cowork).

**Fallback — if the tool isn't available, run the script directly** (requires Bash and
Python 3 + openpyxl on the machine you're running on):

```bash
python3 scripts/build_audit_xlsx.py \
  --client-slug {file-prefix} \
  --audit-dir {full-audit-folder-path} \
  --root-domain https://{client-domain}
```

The xlsx is written to:

```
clients/{client-folder}/wqa/audits/{audit_id}/{slug}-wqa-data.xlsx
```

### Tabs (final order — 4 tabs total)

1. **Aggregator** — every URL with full data. **First 6 columns frozen** (Technical Action · Content Action · Priority · Sprint · Address · Page Type). Layout:
   - **Technical Action** (col A, dropdown): Fix 404 · 301 redirect · Evaluate redirect · Add canonical · Add schema · Noindex · Update robots · Indexability fix · Sitemap fix · Monitor · Leave as is
   - **Content Action** (col B, dropdown): Rewrite · Rewrite title/meta · Expand content · Refresh content · Update onpage · Consolidate · Evaluate · Leave as is
   - **Priority** (col C, dropdown P1/P2/P3)
   - **Sprint** (col D, dropdown): Sprint 1 (Planning) · Sprint 2 (Technical) · Sprint 3 (Local) · Sprint 4 (Content) · Sprint 5 (Links) · Backlog · Done
   - **Address** (col E, hyperlink to full URL)
   - **Page Type** (col F, fill-coded)
   - Then unfrozen: Status · Status Type · Redirect Target (populated from SF crawl's Redirect URL) · Funnel Stage · Indexable · Title (+ length) · Meta Description (+ length) · H1 · Word Count · Crawl Depth · Inlinks
   - **GA4 (90d) block**: Sessions · Sessions Δ · Users · Users Δ · Eng % · Conversions · Conv Δ — Δ cells get green/red conditional fills vs prior 90 days
   - **GSC (90d) block**: Clicks · Clicks Δ · Impressions · Imp Δ · CTR · CTR Δ
   - Then: Total KWs Ranking · Top Keyword · Top KW Vol · Top KW Pos · Ref Domains · URL Rating · Problem Areas · Action Notes
   - Each row can carry one or both actions; whichever is the highest-priority finding from the detector populates the cells.
   - **Strategist edits here are authoritative** — see Phase 3 below for how parse_approvals propagates them.

2. **Recommendations** — project-plan-style matrix, 8 columns. No column freeze. Auto-filter explicitly bounded to A1:H so extras don't bleed into I-Z. Columns: # · **Approval** · Priority · **Category** (Technical/Content) · Sprint · Action Type · Page Address · **Specific Next Step**.
   - **One row per (page × finding)**. A page with three issues (missing meta + missing H1 + thin content) gets three separate rows.
   - **Edit the Specific Next Step inline** for any "Edit" approval — the parser diffs against the snapshot to detect changes.

3. **Keywords** — every ranking keyword with position color-coded (green ≤3, yellow ≤10, orange ≤20, red 21+). Includes volume, est. traffic, CPC, KW difficulty, intent flags, SERP features.

4. **Target Pages** — top 20 link-building roster. Strategist reviews and approves each. Columns: # · **Approval** · Page Address · Page Type · Target Keyword · KW Volume · Current Pos · Ref Domains · Word Count · GSC Impressions · Score · Approver Notes.

### Removed tabs

- **Notes** — removed; strategists use the Approver Notes column (or a separate doc) for free-form
- **Redirects** — removed; the Aggregator's Status Type column + Redirect Target column make this a filter, not a separate tab
- **Errors** — removed; same reason (filter Aggregator by Status Type = broken)
- **Action Plan** — removed; the approved recommendations feed the 12-month project plan (`/bpt-project-plan`), not this report

### Issue detection — what gets surfaced

The detector returns a list of findings per URL. Each finding becomes a Recommendation row.

**Technical findings:**
- 4xx with signal (impressions, backlinks, sessions) → Fix 404 · P1 if high-signal, P2 if some-signal, P3 monitor otherwise
- 3xx redirecting to homepage with signal → Evaluate redirect · P2
- WP auto-generated archives/feeds indexed without content (`/feed`, `/tag/`, `/category/`, `/trainings_cat/`, etc.) → Noindex · P2
- 3xx working as intended → Leave as is · P3

**Content findings (only flag if SF/site-audit has confirmed page data — prevents false positives on URLs Ahrefs/GSC know about but weren't crawled):**
- Missing title → Rewrite title/meta · P1 for money/authority/homepage, P2 elsewhere
- Missing meta description → Rewrite title/meta · P2/P3
- Missing H1 → Update onpage · P2/P3
- Thin content (<618w):
  - Money page → Rewrite · P1
  - Authority page → Rewrite · P2
  - Other → Expand content · P3
- Depth gap (618-1499w, targets a ≥500-volume KW, on money/blog/content/authority page) → Expand content · P2
- Low CTR (>1000 imp, CTR <2%) → Rewrite title/meta · P2
- Striking distance (pos 4-15 with ≥500 imp) → Update onpage · P2
- Stale blog heuristic — substantial blog post (≥1000w) stuck at pos 11-30 with ≥200 imp → Refresh content · P3. (This is a proxy for content age until we wire a `last_modified` data source.)

### Target Pages scoring

Live pages on the commercial side of the site, ranked by link-building value:

```
score = keyword_volume × position_multiplier × business_value_multiplier
```

- **business_value_multiplier**: Money Page 6.0× · Authority 1.8× · Content Hub 1.3× · Blog Post 1.0×
- **position_multiplier**: Top 3 = 0.7 (marginal lift) · 4-10 = 1.5 (best ROI) · 11-30 = 1.2 (achievable with links) · 31+ = 0.4 (likely content gap, not link gap)
- Excluded: homepage, utility pages, 404s, redirects, pages with no keyword signal

Take the top 20.

### Snapshot

When the xlsx is built, the script also writes `{slug}-wqa-recommendations-original.json` next to the xlsx. This is a snapshot of the original "Specific Next Step" text for every row, used later by the approval parser to detect edits.

### Formatting

- Arial 10 body, Arial 11 bold headers. Headers: white text on `#2563EB` blue fill.
- Body cells: overflow text (no wrap), middle vertical-aligned.
- Wrap only narrative columns: Aggregator → Meta Description, Action Notes · Recommendations → Specific Next Step, Current State, Target State, Why It Matters, Approver Notes · Notes → Note · Redirects/Errors → Notes · Target Pages → Approver Notes.
- Color coding: Action columns · Priority (P1 red / P2 orange / P3 yellow) · Status Type (live green / redirect yellow / broken red) · Page Type · Approval (Approved green / Edit yellow / Rejected red / Deferred blue).

---

## Phase 2.5: Publish workbook to Google Sheets + tie to client

**Goal:** turn the generated `{slug}-wqa-data.xlsx` into a **Google Sheet** the team can
review/sync and Claude can read, and **save its URL on the client** so every downstream
deliverable can link to it.

If a Google Drive MCP is connected and the client has a Drive folder
(`custom_fields.drive_folder_id`):

1. Create the workbook as a Google Sheet from the xlsx in the client's Drive folder, e.g.:
   ```
   mcp__claude_ai_Google_Drive__create_file
     name: "{Company} — WQA Workbook"
     parent: {client drive_folder_id}
     # upload {slug}-wqa-data.xlsx converting to a Google Sheet
     # (mimeType target: application/vnd.google-apps.spreadsheet)
   ```
   Capture the resulting share/`webViewLink` URL.

   > **Capability note:** if the connected Drive MCP can't upload+convert an xlsx, fall back to
   > (a) uploading the .xlsx to the Drive folder (still yields a URL), or (b) the manual
   > "File → Import" path below — then ask the user to paste the resulting Sheet URL. Either way,
   > finish by recording it in step 2.

2. Save it on the client (idempotent — re-running updates in place):
   ```
   client_resource_set { client_id, type: "wqa_workbook", label: "WQA Workbook", url: <sheet_url>, source: "wqa" }
   ```

If Drive isn't connected, skip creation and use the manual instruction in Checkpoint 1; you can
still record a pasted URL via `client_resource_set` later. The `wqa_workbook` resource then
appears on the client's Kickoff + Content deliverables in the Projects view.

---

## CHECKPOINT 1: Approval Review

**STOP and send this message to the user:**

> The audit workbook is ready. If Drive is connected it's now a Google Sheet on the client:
> **{wqa_workbook URL}** (also saved as a client resource). Otherwise open
> `clients/{slug}/wqa/audits/{audit_id}/{slug}-wqa-data.xlsx` and upload to Google Sheets
> (File → Import) — the dropdowns and color coding carry over.
>
> **Two tabs to review:**
>
> **Recommendations** — for each row, fill in the **Approval** column (col B):
> - **Approved** — build it as-written
> - **Edit** — edit the "Specific Next Step" cell inline, then mark Edit
> - **Rejected** — don't build it
> - **Deferred** — valid but next quarter (goes to backlog)
>
> **Target Pages** — same Approval dropdown on each of the top 20 link-building targets.
>
> Skim the **Aggregator** tab too — if you disagree with a Technical Action or Content Action in col A or B, flip it via the dropdown.
>
> When done: File → Download → .xlsx → save back to the same audit folder (overwrite the original). Then come back here and say "approvals done."

Wait for the user to confirm they've finished. Do NOT proceed without confirmation.

---

## Phase 3: Parse Approvals

**Goal:** Read the returned xlsx and produce a structured approval summary.

**Preferred — if the `wqa_parse_approvals` MCP tool is available, use it:**

```
wqa_parse_approvals { audit_id }
```

**Fallback — if the tool isn't available, run the script directly:**

```bash
python3 scripts/parse_approvals.py \
  --client-slug {file-prefix} \
  --audit-dir {full-audit-folder-path} \
  --root-domain https://{client-domain}
```

The parser:

1. Loads the (now edited) `{slug}-wqa-data.xlsx`.
2. Reads every row of the Recommendations tab.
3. Compares each row's current "Specific Next Step" against the snapshot to detect edits.
4. **Reads the Aggregator tab as an override layer** — strategist edits to Technical Action / Content Action / Priority / Sprint on a URL are merged into the matching Recommendation row(s). Disambiguation rules:
   - **action_type override** only applies when the URL has exactly one Recommendation row in that category (else can't safely target which rec it modifies)
   - **priority + sprint override** only applies when all of that URL's Recommendation rows had the same value originally AND the Aggregator differs (else the variance signals the strategist didn't intend a uniform change)
   - Each applied override is logged on the row as `aggregator_overrides_applied: ["action_type: Rewrite → Refresh content", ...]`
5. Buckets rows by Approval status.
6. Reads the Target Pages tab and buckets those by Approval.
7. Writes a structured summary to `{slug}-approvals.json`.
8. **Writes the final xlsx back to the same path** — single source of truth:
   - Overridden cells in Recommendations highlighted **light blue**
   - Edited Specific Next Step cells highlighted **soft yellow**
   - A pinned **Audit Summary** tab at position 1 with totals, override count, last-parsed timestamp, and a legend explaining the cell colors

### What "Edit" means

For Edit rows, the parser takes whatever text is in the "Specific Next Step" cell as the new recommendation. The strategist makes edits inline in the spreadsheet — no conversational follow-up. The `original_text` field in the summary preserves the original wording.

### Approval summary presented to user

After parsing, show this table:

| Bucket | Recommendations | Target Pages | What happens |
|--------|----------------|--------------|--------------|
| Approved | n | n | Built as written |
| Edit | n | — | Uses your edited text |
| Rejected | n | n | Dropped |
| Deferred | n | n | Backlog |
| Unmarked | n | n | Blocks next phase |

If there are Unmarked rows, list them and ask for resolution.

---

## CHECKPOINT 2: Build Visual Report

**STOP and ask:**

> "Approvals are parsed: {n} approved, {n} edited, {n} rejected, {n} deferred. Target pages: {n} approved. Ready for me to build the visual report?"

Wait for explicit yes.

**REQUIRED before building — populate the performance data (never skip this).** The report's Performance Metrics KPIs and trend chart come from data files that MUST exist and be non-empty in the audit folder. These are separate from the spreadsheet's inputs — producing the spreadsheet does NOT produce them. If any are missing, pull them now (scoped to the client's domain per §1.2a) before running the builder:
- `{slug}-gsc-monthly.json` — 16-month GSC clicks/impressions/position
- `{slug}-ga4-monthly.json` — monthly organic + total sessions/conversions
- `{slug}-gsc-90d-current.json` and `{slug}-gsc-90d-prior.json` — each with `by_page` + `site` + `period`
- `{slug}-ga4-90d-compare.json` — organic/total current vs prior
- `{slug}-target-pages.json` — link roster from the approved Target Pages

`build_report.py` prints a loud WARNING if these are empty. **After building, VERIFY the HTML**: the "at a glance" KPIs must be non-zero and the trend chart must contain data. If they're blank, the data files weren't produced — fix and rebuild. A report with empty performance data must never be delivered.

**Preferred — if the `wqa_build_report` MCP tool is available, use it:**

```
wqa_build_report { audit_id, client_name: "{Client Display Name}", primary_color: "#YourHex" }
```

(`client_name` and `primary_color` are optional — they default to the client's `company_name`
and `#2563EB` respectively.)

**Fallback — if the tool isn't available, run the script directly:**

```bash
python3 scripts/build_report.py \
  --client-slug {file-prefix} \
  --audit-dir {full-audit-folder-path} \
  --root-domain https://{client-domain} \
  --client-name "{Client Display Name}" \
  --primary-color "#YourHex"   # optional, defaults to #2563EB
```

### Report structure — 4 title-slide sections
(The implementation/project plan is NOT in this report — it's built in the next step as the full **12-month** project plan via `/bpt-project-plan`. Keeping a plan here would duplicate/contradict that.)

**Section 1 · Performance Metrics**
- At a glance: 8 KPIs (organic sessions, conversions, GSC clicks, impressions, CTR, avg position, indexable URLs, ranking keywords) — each with ▲/▼ % change vs prior 90 days
- Organic performance over time: monthly chart showing GA4 organic sessions + GSC clicks + GSC impressions (16-month GSC limit, GA4 goes as far back as the property has data)
- Performance by page type: pie chart (GSC clicks only) + accordion for each page type listing every page in that category
- Performance by funnel stage: pie chart (GSC clicks only)
- Top 15 keywords by traffic: keyword · intent · position · volume
- Striking distance opportunities: keyword → URL with trend arrows on position/imp/clicks/CTR

**Section 2 · Technical Improvements**
- Site health snapshot (status mix donut + top broken URLs by signal)
- Indexability + critical elements: KPIs (missing title / meta / H1 / thin pages) + indexability breakdown + crawl depth distribution
- Redirects analysis (specifically calls out redirects pointing to homepage — relevance leak)
- (No PSI panel — pending API access. Full per-page technical detail lives in the audit spreadsheet's Recommendations tab.)

**Section 3 · Content**
- Content depth overview: KPIs (live pages with content / avg word count / median / thin pages)
- Word count distribution: <300 · 300-617 · 618-1500 · 1500-3000 · 3000+
- Depth by page type: avg words and thin count per page type
- (No card list — full per-page detail is in the audit spreadsheet's Recommendations tab.)

**Section 4 · Links**
- Target pages — link-building roster (only Approved + Edit rows): #, page, page type, target keyword, KW vol, current pos, ref domains, score
- Backlink gap analysis: pending (next iteration pulls top 5 SERP + their referring domains per target page)

> **No Project Plan section in this report.** The implementation roadmap is built separately as the full **12-month** project plan (`/bpt-project-plan` → Checkpoint 3), sourced from the approved recommendations. Embedding a plan here previously produced a 6-month schedule that contradicted the 12-month engagement — removed to avoid confusion.

### Brand styling

- Headers / titles / KPI values: **Bebas Neue**, uppercase, condensed.
- Body / tables / pills / paragraphs: **Figtree** (weights 300-800).
- Hero + title slides + sprint headers: deep ink (`#0a0e1a`) with a blue left-border accent.
- Primary accent color is the client's brand blue (defaults to `#2563EB`; pass `--primary-color` to override).
- Self-contained HTML: **Chart.js is inlined** from `assets/chart.umd.min.js` (never CDN — a CDN `<script src>` is blocked in sandboxed/offline viewers and leaves every chart blank). Google Fonts load from CDN with a system-font fallback. The `assets/` folder must ship with the skill bundle.

When the report is built, **tie it to the client** so deliverables can link to it. If Drive is
connected, upload `{slug}-wqa-report.html` to the client's Drive folder and record the URL;
otherwise record the local path:

```
client_resource_set { client_id, type: "wqa_report", label: "WQA Report", url: <drive_url_or_path>, source: "wqa" }
```

Then **stop again** and wait for confirmation before the Agency OS project is created.

---

## CHECKPOINT 3: Create Agency OS Project

**STOP and ask:**

> "Visual report is at `{path}`. Ready to generate the 12-month project plan
> (sprints + deliverables) in Agency OS?"

Wait for explicit yes, then **hand off to `/bpt-project-plan`** — that skill owns
the plan generator (`build_project_plan.py`) and the `project_plan_import` step.
Keeping a single owner means the plan is generated by exactly one code path and is
never created twice.

Invoke `/bpt-project-plan` for this client; it will:
1. Read this audit's `{slug}-approvals.json`,
2. Generate the 12-month plan, passing **`--vertical`** from the client's
   `custom_fields.vertical` (Sprint 3 Local SEO is included only for `local_service`;
   other verticals suppress it and shift content up to Month 2). Sprints 1-6: Kickoff
   (WQA + Project Plan) / Technical / Local SEO / Content / Links / Reporting (Analytics
   Audit + monthly Client Check-ins + WQA Refreshes at M6/M12) — team-routed assignees,
3. **Present the plan as a month-by-month table in chat (Checkpoint 2.5)** for the
   strategist to review/edit before committing, then
4. Import it via `project_plan_import` (idempotent — re-running replaces the prior
   plan rather than duplicating it), then
5. **Regenerate the agency dashboard** (`build_agency_dashboard.py`) so this client —
   its 12-month plan and analytics tracking — appears on `{AGENCY_ROOT}/agency-dashboard.html`.
   This is the whole point of finishing the WQA: the client lands on the agency dashboard.

Rejected recommendations are not included; Deferred are left out of the active
schedule.

---

## Phase 4: Final Recap

Send a Slack + email recap with:

- Link to the xlsx
- Link to the visual report
- Project link in Agency OS
- Counts: approved / edited / rejected / deferred / total + target pages approved / total link slots

---

## Scripts Reference

All scripts live in `scripts/`. `build_audit_xlsx.py`, `parse_approvals.py`, and
`build_report.py` each have a corresponding MCP tool (`wqa_build_xlsx` /
`wqa_parse_approvals` / `wqa_build_report` — see MCP Tools Reference below) that runs
them server-side; prefer those when available and only invoke the script directly as a
fallback. `discover_redirects.py` has no MCP tool yet — run it directly (Bash only).

| Script | Purpose |
|--------|---------|
| `build_audit_xlsx.py` | Build the 7-tab audit spreadsheet from pulled data. Multi-finding detector. Snapshots originals to JSON. |
| `discover_redirects.py` | HEAD-fetch legacy URLs to determine 200/3xx/4xx and redirect targets. |
| `parse_approvals.py` | Read the returned xlsx, diff against the snapshot, write approval summary JSON. Reads both Recommendations + Target Pages tabs. |
| `build_report.py` | Generate the branded HTML report (4 sections: Performance/Technical/Content/Links). Chart.js inlined; no embedded plan. Requires the performance data files (see Checkpoint 2). |

The detailed 12-month project plan (sprints + deliverables) is generated by the
**`/bpt-project-plan`** skill (its `scripts/build_project_plan.py` + the
`project_plan_import` MCP tool) — invoked at Checkpoint 3 above.

---

## MCP Tools Reference

| Tool | Phase | Purpose |
|------|-------|---------|
| `wqa_create_audit` | 1 | Create audit workspace |
| `wqa_upload_crawl` | 1 | Upload Screaming Frog CSV |
| `wqa_get_audit_state` | Any | Check audit progress |
| `wqa_list_audits` | Any | List client audits |
| `wqa_update_patterns` | Any | Update URL patterns |
| `wqa_build_xlsx` | 2 | Build the audit spreadsheet server-side (runs `build_audit_xlsx.py`) — prefer over the raw script |
| `wqa_parse_approvals` | 3 | Parse strategist approvals server-side (runs `parse_approvals.py`) — prefer over the raw script |
| `wqa_build_report` | Checkpoint 2 | Generate the branded HTML report server-side (runs `build_report.py`) — prefer over the raw script |
| `wqa_save_data_file` | 1 | Persist a Phase 1.2 pull (Ahrefs/GSC/GA4/etc.) into the audit folder under the filename the builder expects — **required after every pull, nothing does this automatically** |
| `windsor_query` | 1 | Pull GA4 + GSC data (monthly time-series + 90d compares) |
| `ahrefs_keywords_raw` | 1 | Full organic keyword list |
| `ahrefs_top_pages_raw` | 1 | Per-URL traffic/keywords/referring domains/UR |
| `ahrefs_crawled_pages_raw` | 1 | Per-URL status code + last-crawled date |
| `ahrefs_backlinks_raw` | — | Backlink inventory (not consumed by the xlsx builder; available for other analysis) |

**Not available:** an MCP tool for Ahrefs Site Audit (`{slug}-ahrefs-pages.json`) — it requires a pre-configured, verified Site Audit `project_id` in the Ahrefs dashboard, which isn't modeled anywhere in this system. That column of data stays blank until this is built.

---

## Decision Points

**No SF crawl yet** → **HALT.** This is a hard prerequisite — see Phase 0.2. SF is the only reliable source for title, meta, H1, word count, inlinks, outlinks, and crawl depth at the per-page level. Ahrefs is for keywords + backlinks only. Tell the user to run an SF crawl with the Internal HTML export and drop it in `clients/{slug}/crawls/`. Do not attempt partial-data fallbacks.

**GSC API limit** → 16 months max. The Section 1 time-series chart will show GSC limited to 16 months and GA4 going further back (29+ months for properties with history).

**Large site (1,000+ pages)** → Aggregator can handle it. The Recommendations tab will be large, but the report itself stays lean (KPIs, charts, roster) since the per-item plan lives in the separate 12-month project plan.

**No last_modified column** → The stale-blog heuristic (mid-position substantial blog posts) approximates this. For a true date-based rule, re-export SF with the Last Modified column.

**Strategist disagrees with the auto-classification** → Override in the Aggregator tab via either action dropdown. The approval parser respects whatever's in the sheet.

---

## Tips

- Always pause at each checkpoint. The whole point of the v3 flow is human-in-the-loop, not Claude-decides-everything.
- Hand-curate the top 5-10 P1 recommendations with section-by-section outlines (proposed titles, target word counts, sections to add). Auto-generated rows are fine for everything else.
- Keep the Notes tab — strategists use it during the review to flag things they want to come back to.
- The Approval dropdown values are exactly: `Approved`, `Edit`, `Rejected`, `Deferred`. Don't add new values without updating `parse_approvals.py`.
- The two action columns on the Aggregator can BOTH be populated for a single URL — Technical and Content are separate workstreams.
- We don't work in hours. The report and spreadsheet talk in capacity units (pages, pieces, words, links) and months — never billable hours.

---

*Agency OS v1.3 — Blueprint Training One-Person Agency program*
