---
name: bpt-local-seo-audit
description: The Local SEO + GEO optimization sub-process — a guided, step-by-step conductor that walks the strategist through the local stack one micro-step at a time (NAP → competitive research → GBP → aggregators → citations → reviews). Use this skill when the project plan + dashboard are complete and it's time to kick off local SEO, or when the user says "start the local seo process", "local seo sub-process", "run local seo", "next local seo step", "kick off local", or names any of the six steps. This is NOT a one-pass audit — it runs interactively, produces/updates one artifact per step, and pauses for the user at each checkpoint before advancing.
---

# Local SEO + GEO — Guided Optimization Process

This skill is a **living, talking SOP**. It does not batch-run. It walks the strategist through the Local SEO sub-process **one step at a time**, doing the pullable work itself, prompting the user for what only they can supply, and **pausing at the end of every step for review before advancing**. Small, verifiable chunks are what make the data pulls reliable.

Owner throughout: the **Local SEO Engineer / strategist**. Begins in week 1 of the campaign; runs independently of the WQA/content/link sprints. Target: complete in ≤ 8 business days.

---

## How to run this skill (conductor behavior — read first)

**1. Handoff trigger.** When the project plan + agency dashboard are complete (or the user asks to start local SEO), open with:

> "Project plan complete. Ready to kick off the **Local SEO optimization sub-process**?"

**2. On kickoff, lay out the map.** Show the full step list as a table of contents so the user sees the whole road, then start Step 1:

> Here's the process — we'll go through it together, one step at a time:
> 1. **Collect NAP info** — accurate Name/Address/Phone + core profile data for every location
> 2. **Competitive research + current performance** — SERP/Maps landscape, competitors, baseline rankings
> 3. **Optimize GBP(s)** — categories, description, services/products, photos, attributes
> 4. **Optimize aggregator profiles** — Apple/Bing/Yelp + vertical directories
> 5. **Citation management** — audit, clean, build, dedupe
> 6. **Review strategy** — generation + response system
>
> Let's start with **Step 1**.

**3. Run ONE step at a time.** For each step:
- State the goal in a sentence.
- Do everything Claude can pull/build autonomously (see per-step detail).
- Clearly list what only the user/client can supply, and ask for it.
- Produce or update **that step's artifact**.
- **Checkpoint:** present the artifact, summarize what's filled vs. still needed, and ask the user to review. **Do not advance to the next step until the user says go.**

**4. Never fabricate data.** If a value can't be verified, flag the cell (⚠) with a note about where it must come from — never guess a phone number, URL, or category. Verified-from-source beats plausible-looking.

**5. Persist artifacts to the client folder** so the process survives across sessions: `clients/{slug}/local-seo/`. Each step reads the prior step's output.

**6. Every step ends with a MANUAL-WORK handoff — never let it look "done."** Claude writes the content (descriptions, services/products, graphics, citation lists, review templates), but Claude cannot log into or update the live profiles/directories — a human or a service must apply it. So at the **end of each step**:
- **Log the manual follow-up as tracked work** — append it to a running **Execution Backlog** (a tab in the workbook and/or `deliverables_create` on the client's Local SEO sprint), e.g. "Manually update all 4 GBPs with the new descriptions/services/photos", "Manually build/fix the 67 citations", "Load the aggregator profile content", "Enable the review-request automation". Each carries the source (which tab) + owner + status.
- **Say it plainly to the user:** the deliverable is a worklist, not applied work — the profiles/citations/reviews are **not live until someone updates them manually** (recommend Loganix for citations/profiles). Repeat this at every step, not just once.
- The Local SEO Audit workbook is the source of truth; the Execution Backlog is the "now go do it" list that mirrors into the project plan's Local SEO sprint.

> Steps 7–9 of the original 10-step SOP (website architecture, content optimization, local link building) are **out of scope** here — each is its own large process build handled by the content and link-building skills. This sub-process ends at Step 6.

---

## Data-reliability playbook (applies to every step)

Hard-won lessons — follow these or pulls come back empty/wrong:

- **Google Business Profile data:** pull GBP fields from third-party sources — DataForSEO (`dataforseo_business_data` / `dataforseo_reviews`), Local Falcon, and Windsor — but DataForSEO frequently returns empty. **The reliable path is the browser** (Claude in Chrome): read the live Google listing / knowledge panel directly. This is how we pull phones, categories, hours, reviews count/rating, and profile links when the APIs fail.
- **DataForSEO is unreliable — do not depend on it.** Across testing, `business_data` returned empty and `reviews` rarely resolved (slow async crawls). Treat DfS as best-effort only. Anything DfS would provide (GBP fields, reviews, review velocity) should come from the **browser** or **Ahrefs** instead; if a metric's ONLY source is DfS, prefer to drop it rather than ship unreliable/empty data.
- **Phone numbers:** a GBP's displayed **Primary** phone is often a **CallRail tracking number**. The true NAP number is usually the GBP **Alternate**, and it matches the license/bar record, Yelp, and directories. Always record the true local line for citations and **flag the tracking number** so it doesn't leak into the NAP.
- **Local Falcon:** scope every call by **`place_id`** (per office). `campaign_name` is ignored.
- **Keyword tracker:** always pass **`state_full`** = the client's real state, or it geo-targets the wrong same-named city and returns nulls.
- **Windsor:** returns all accounts — post-filter to the client's domain / GMB location.
- **Multi-location:** location-specific fields get **one column per verified GBP location**; business-wide fields are filled once.
- **Workbook formatting standard:** the default font for every workbook is **Arial** (all cells). Keep the visual system from Step 1 — navy section bands, blue location-header row, amber (`FFF3CD`) fill on any flagged/attention cell, light-yellow (`FFFDEA`) fill on input cells, gray italic notes, wrapped text, frozen header.

---

# STEP 1 — Collect NAP Info  ✅ (fully built)

**Goal:** an accurate, consistent Name / Address / Phone + core profile record for every verified location — the foundation for the Maps Pack, citation trust, and LLM/GEO local results.

**Artifact:** `clients/{slug}/local-seo/{Client} - Local SEO Audit.xlsx` — the single workbook for the whole sub-process (the "NAP Info" tab is Step 1; later steps add tabs). Formatted, mirroring the master **"Blueprint // Local SEO + GEO - NAP + Competitors"** NAP tab, generalized for any client vertical (not legal-specific).

### 1.1 Set up the workbook
- Copy/generate the NAP tab into the client folder. Layout: a **Field** column, one **column per verified GBP location** (primary first), and a **Notes** column. Section bands: **Business Section** (per location), **Key Profiles – per location**, **Business-wide**, **Brand Assets**, **Owner/Principal**, **Key Profiles – social & directories (business-wide)**.
- Match the master template's field list exactly; do not drop rows. Keep the ☐ done-checkboxes on asset/profile rows.

### 1.2 Auto-fill everything Claude can
Prefill from the client record, the client website, and the live GBPs:
- **Per location:** Business Name (as on GBP), Address / Suite / City / State / Zip / Country, Website (location-specific page for multi-location), Featured Message + GBP link, Business Hours, **Short (<300) + Long descriptions** and a **keyword set — for ALL locations**, each with its own city terms.
- **Business-wide:** categories (from GBP), languages, date opened / years in business.
- **Phones — pull from the live GBP via the browser** (see playbook). Record the **true local NAP line** per office; put the shared toll-free in the Toll Free row; **flag any CallRail/tracking number** found as the GBP primary.
- **Key profile links — pull and verify:** socials + GBP map links from the site footer; browser-confirm Instagram, Yelp (exact biz URL), etc. Mark ones that don't exist (e.g. "no Pinterest") and directories with only category placements (e.g. Expertise) rather than inventing a URL.

### 1.3 Flag what only the client can supply
Leave these blank-but-flagged (⚠), with a note, and ask the user:
- Public/general inbox email + a dedicated **citation email** (expect ~100 verification emails + ongoing spam).
- Owner / principal name + title.
- Brand assets: logo, profile photo, image folder (need ~5 photos — create if none), intro video URL.
- Confirm hours, languages, and any location that should be in/out of scope.

### 1.4 Checkpoint
Present the workbook. Summarize: which locations/fields are filled and verified, which cells are flagged for the client, and any data-quality catches (e.g. tracking numbers on the GBPs, an office with no local line). Ask the user to fill the flagged cells and confirm the NAP is accurate. **Wait for their go before Step 2.**

---

# STEP 2 — Competitive research + current performance  ✅ (built)

**Goal:** map the local SERP/Maps landscape, identify the true local competitors, and capture a performance baseline so every later step can be measured against a starting point.

**Artifact:** a **Comp. Analysis** sheet added to the client's `{Client} - Local SEO Audit.xlsx` (same workbook, Arial, same visual system) — one competitor table **per primary market/location**, plus a **Baseline** block for the client.

Run it as micro-chunks, one market at a time (a "market" = one office's target city). For a multi-location client, do the primary market first, checkpoint, then repeat per office.

### 2.1 Frame the market
- Pull the client's primary keyword set + grid center from the record (`local_falcon_config.keywords`, per-office `place_id`).
- Confirm the target city/zip for this market.

### 2.2 Pull the Maps/SERP landscape (browser is the reliable source)
For each primary keyword in the market, read the **live Google Maps pack** (Chrome: `maps/search/{keyword} {city}`) and capture the top 3–5 competitors that outrank/flank the client. Cross-check with Local Falcon competitor data (`localfalcon_competitors` / `get_lsg_competitors`) for grid-wide average rank where a scan exists. De-dupe and exclude the client itself and unrelated same-name businesses.

### 2.3 Profile each competitor (one row each) — and include the client
Put the **client as the first (highlighted) row** so it's a direct head-to-head. Columns: **Competitor (GBP name) · Primary category · Reviews (total) · Avg rating · Website · Organic traffic (site-wide, US) · Keyword-in-name? · Notes.**
- **Reviews (total) + rating:** from the live Maps listing — this is the competitive review comparative for a one-time audit. (Review VELOCITY / new-reviews-30d was dropped: the only source is DataForSEO reviews, which is unreliable — see playbook — and total count + rating captures the competitive picture without it.)
- **Website:** grab the exact domain from each GBP's website link (`read_page` on the Maps results exposes the "Visit … website" href, incl. UTM). Don't guess domains.
- **Organic traffic:** from Ahrefs (`ahrefs_live_explore` overview). Label it clearly as **site-wide / US domain traffic — NOT location-specific** (a national brand looks huge here but that says little about the local market). Domain-strength signal only; for local, reviews + Maps rank matter more. (No "top-3 keywords" column — low-signal.)
- **Keyword-in-name?** flags competitors stuffing the target keyword into their GBP business name.

### 2.4 Baseline the client (the "current performance" half)
Capture the starting line so progress is measurable later:
- **Maps Pack + organic rank** for each primary keyword — `local_keyword_track_batch` with **`state_full`** set (playbook), scoped per office. At minimum, note from the live Maps pull whether the client is in/out of the top-10.
- **GBP review count + avg rating** per office (already in the client row).
- Optional if connected: **GMB views/calls/clicks + GSC local-intent clicks** (Windsor, post-filtered to the client).
- End with a one-line **baseline read** (e.g. "gap is local, not domain strength").

### 2.4b Keyword Performance tab (services × locations)
Build a **Keyword Performance** tab: the service×location target list with **search volume** (Ahrefs `ahrefs_keywords_overview` — statewide terms scoped with "california", NOT national), **organic rank** (cutterlaw-style `ahrefs_keywords_raw` export cross-reference), and **Maps Pack rank** (Local Falcon grid ARP). Drop keyword-difficulty (low signal). Group by market; flag striking-distance (11–20) and not-ranking rows.

> ⚠️ **Maps Pack rank prerequisite — tell the user up front:** the Maps column only fills for keywords that were actually **scanned in Local Falcon**, and scans are **per location**. Before this step, make sure the client's Local Falcon campaign has a **grid scan for every keyword you want to track, at every office/location**. Any keyword not scanned shows "— not scanned" (the read-only LF tools can't trigger new grids; that's done in Local Falcon). DfS `local_keyword_track_batch` can approximate a single-point Maps rank as a fallback, but it isn't the same as a grid ARP — keep one methodology per column.

### 2.5 Checkpoint
Present the competitor table (client included) + baseline + Keyword Performance for the market. Confirm the competitor set + keyword list are right (the strategist knows the market) before repeating for the next office / advancing to Step 3.

> Not in this step: SERP-feature cataloguing and keyword research were dropped — the first is better handled inside the GBP/GEO work (Step 3), and keyword research belongs to the content process unless run properly with volumes.

---

# STEP 3 — Optimize GBP(s)  ✅ (built)

**Goal:** turn each verified GBP into a fully-optimized, keyword + GEO-aligned listing.

**Hard constraint:** no GBP write access (native API is approval-gated; editing a live listing is a manual, permissioned action). So Step 3 produces a **paste-ready change-set** — Claude drafts the optimal values; the strategist applies them in business.google.com or via Search Atlas. Never auto-write.

**Artifact:** a **GBP Optimization** tab in the workbook — `Field | Current (live GBP) | Recommended | Action/Notes` per office, plus a shared Services table and a Photo plan.

### 3.1 Audit current GBP (browser) per office
Read each office's live listing: primary/secondary categories, description, services, attributes, hours, photos, posts. Capture the real current values so the change-set shows Current → Recommended.

### 3.2 Draft the optimized knowledge graph per office
- **Categories:** primary + secondary aligned to practice areas AND to what ranking competitors use (from Step 2). Audit the existing category set in the dashboard.
- **Business name:** keep the real legal name — do NOT keyword/city-stuff it (suspension risk), even though competitors do. Keyword-in-name only via a real DBA (Step-6 bonus).
- **Description (≤750):** localized, keyword-first, GEO/LLM-friendly, ends with the office's NAP + CTA. Refine the Step-1 long description.
- **Services/Products (full):** a **Products (GBP)** tab — one row per practice area with landing URL + a **full ≤1000-char persuasive description ending in a CTA + full NAP** (write the body once; swap the closing NAP line per office). This is the SOP "Products" deliverable, not a blurb.
- **Practice-area graphics:** generate a branded card per practice area (1200×900, 4:3, brand banner, monogram, practice-area name, no CTA text) — **centered + lower-third** variants — into `clients/{slug}/local-seo/gbp-images/`, filenames `{service}-{layout}.png`. Reliable path is **Pillow** (programmatic branded template). For photographic/blurred-background versions use Canva (needs auth) or an image model. Confirm the client's exact brand hex (default navy+gold placeholder).
- **Phone:** recommend the TRUE local NAP line as primary (GBP primaries are often CallRail tracking numbers — flag them).
- **Hours / attributes / service areas:** standardize hours across offices (reflect 24/7 intake in the description, not the hours field); verify attributes before enabling.
- **Posts:** de-duplicate — localize weekly posts per office (don't run the same post on every listing).
- **Photo plan:** logo, cover, ≥3 headshots, office exterior+interior, ≥5 practice-area images; filename convention `{city}-{service}-cutter-law-##.jpg`.

### 3.3 Checkpoint
Present the change-set. Strategist reviews the Recommended values (and the ✎ decisions: category set, hours policy, phone, attributes) before anything is applied to the live listings.

---

# STEP 4 — Optimize aggregator profiles  ✅ (built)

> **Step 4 vs Step 5 — keep them separate.** Step 4 = **DEPTH on a few**: claim + fully build out the handful of high-value profiles like mini-GBPs. Step 5 = **BREADTH across all**: NAP consistency + presence across the entire directory list. Same data, different jobs — separate tabs.

> **Educate the user (put this in the kickoff prompt).** These are **aggregator profiles** — high-authority sites (Google, Apple, Yelp, Avvo, etc.) with **rich, standalone profile pages** (photos, reviews, services, descriptions) that rank on their own, earn referral traffic, and build trust. You *claim and fully optimize* them. That's different from a plain **citation** (Step 5): a citation is just a **NAP mention** of the business across many directories — its job is consistency + volume as a local trust/ranking signal, not deep content. Simplest framing for the client: *aggregator profiles are destinations you build; citations are mentions you keep consistent.* Every aggregator profile is also a citation, but not every citation is worth optimizing as a profile.

**Goal:** deeply optimize the highest-value aggregator profiles — a **niche-aligned** set, not a hardcoded one.

**Detect the niche first, then build the set.** Read the client's vertical from the website (homepage / services / meta) or the client record `vertical`; if unclear, **ask**. Then `citation_directory_loader.select_for_vertical(dirs, vertical)` returns the **deep-optimize set** = the ~11 universal profiles (GBP, Apple, Bing, Facebook, Instagram, LinkedIn, Yelp, BBB, Foursquare, Trustpilot, Nextdoor) **+ the niche add-ons for that vertical** (legal → Avvo/Justia/FindLaw/LII/US Legal/HG; home_services → Houzz/HomeAdvisor/Angi/Porch/Thumbtack; healthcare → WebMD/Healthgrades; hospitality → TripAdvisor/Hostelworld; etc.). Verticals with no built-in add-ons still get the universal core — then add market/vertical-specific dirs you find. (GBP is Step 3; Facebook/LinkedIn also live on the NAP tab.)

**Constraint:** no account creation / login (manual, permissioned). Step 4 produces an **audit + content change-set**, not live edits.

**Artifact:** an **Aggregator Optimization** tab — `Profile | Scope | Priority | Status | NAP fix | Content to load | Action/owner`.

### 4.1 Audit the key profiles (live)
Browser-check each of the set: claimed? live? NAP correct? A `"{client}" (site:avvo.com OR site:justia.com OR …)` search finds the profiles fast. **Capture the exact profile URL for every live one** (use `read_page` on the SERP to read the result hrefs — don't just mark "LIVE"; the URL is needed to optimize + track it). Flag NAP mismatches, old/duplicate listings, and **unrelated same-name businesses** (don't conflate).

### 4.2 Content to load (reuse, don't recreate)
On each, load: logo + cover + ≥5 practice-area graphics (Step 3 `gbp-images/`); firm description (GBP Optimization tab); services + descriptions (Products tab); links to matching location/service pages + social & bar profiles; attorney bios; authority signals (awards, notable verdicts, review counts). NAP identical to the NAP Info tab.

### 4.3 Checkpoint + set expectations (say this every time)
Present the optimization set + NAP fixes. **Make clear this output is a worklist, not done work:** claiming, verifying, and building out each profile is **manual** — Claude can't create accounts, log in, or submit (permissioned). Tell the user plainly that the actual claim/build still has to happen, and **we recommend [Loganix](https://loganix.com) for citation/profile building & cleanup if they don't want to do it in-house** (also WhiteSpark / BrightLocal / Yext). Strategist prioritizes before hand-off.

---

# STEP 5 — Citation management  ✅ (built)

**Goal:** consistent, complete NAP across the **entire** directory universe (not deep optimization — that's Step 4). Inconsistent citations hurt Maps ranking, so **clean-existing usually beats add-new**.

**Artifact:** a **Citations** tab — the full list with `Category | Tier | Directory | Domain | Submission link | Status | NAP/notes`, sorted into a fix-first → Tier-1-missing build order.

### 5.0 Resolve the directory list (two questions — do this first)
1. **Ask:** *"Do you have your own citation directory list for this client/vertical (CSV with Name / Domain / Submission link)?"* → **Yes:** drop it in the client folder; `citation_directory_loader` auto-finds any `*citation*.csv`.
2. **If no, ask:** *"Use the built-in default — ~50 high-DA general + niche directories (Tier 1 = DA ≥ 90)?"* → **Yes:** `templates/citations-fallback-generic.csv` (or a vertical template like `citations-fallback-legal.csv`). **No:** build from 3–5 competitors (WhiteSpark/BrightLocal or Ahrefs referring domains) + universal General tier + data aggregators; save as the agency's reusable list.

Whichever base list, **add the client's local/market-specific directories** (city chambers, regional/vertical orgs).

**Niche-align the full list:** the generic CSV is vertical-tagged, so `select_for_vertical(dirs, vertical)['full']` returns the citation universe for THIS client — universal directories + the niche ones matching their vertical, with other verticals' niche sites dropped (a plumber's list won't carry Avvo; a law firm's won't carry Angi). Detect the vertical the same way as Step 4 (website / record / ask).

### 5.1 Audit each → status
Per directory (per office where location-based): **Live-correct / Live-wrong (NAP mismatch) / Duplicate / Missing**.

### 5.2 Clean
Fix wrong NAP to match the NAP Info tab exactly; remove/suppress duplicates.

### 5.3 Build the missing
Submit via each directory's link, identical NAP + optimized content, **Tier-1 / high-DA free directories first**, per office. **This is manual work** — Claude preps the worklist + tracks, but claiming/submitting each listing is done by a person or a bulk citation service. **Always tell the user this, and recommend [Loganix](https://loganix.com)** for citation building & cleanup if they need help (also WhiteSpark / BrightLocal / Yext).

### 5.4 Data aggregators
Submit to **Data Axle, Neustar/Localeze, Foursquare** to syndicate NAP across the long tail automatically instead of hand-submitting hundreds.

### 5.5 Track
Status per directory/office (Pending → Submitted → Live / Fixed / Duplicate) + profile URL; re-audit quarterly to catch drift.

---

# STEP 6 — Review strategy

**Goal:** stand up a working review **generation + automation + response** system the agency owns — not just hand the client a doc. Reviews are the biggest Maps Pack lever and the #1 driver of which firm gets the call, so this step is measured and delivered like every other, with the velocity tracking + monthly reporting loop handled later in the reporting build.

### 6.0 Read the baseline
Pull each office's current **review count + rating** (from Step 2's Comp. Analysis / live Maps listings). Call out the gaps — thin offices (few/no reviews, low rating) get reviews **first**; healthy offices just need steady recency. This priority order drives the client doc.

### 6.1 Generate the client-facing playbook
Produce **`{Client} - Review Generation & Management Playbook.docx`** in `clients/{slug}/local-seo/` (build with the `docx` skill; Arial; branded). Faithful to the WEBRIS Review SOP, tailored to the client:
- **Where they stand today** — per-office review count/rating + a **direct “leave a review” link per office** (`https://search.google.com/local/writereview?placeid={PLACE_ID}`) and a priority order.
- **Five generation plays** — (1) reach out to past clients, (2) tap your professional network, (3) make the ask part of closing every case, (4) follow up after consultations (two-step: feedback first, *then* ask), (5) empower the team (staff-only incentives — never pay reviewers). **Write these client-facing:** address the client firm directly (“your firm / your team / your clients”), consultative-strategy prose (not an ops checklist), and reference the client's own offices/gaps. This doc is what the agency hands to *their* client.
- **Call & text scripts** — past-client/post-case + the two-step post-consult scripts, with client name/attorney swapped in.
- **Managing reviews** — respond to every review (positive + negative) within 48h; never share case details; flag fake/policy-violating reviews for removal.
- **Ethics/compliance callout** — no paid/incentivized reviews to the public (Google policy + bar rules); every review must be real.

Then **prompt the user to add the doc to the client's Drive folder** (offer to push it via the Google Drive connector on confirmation). **At the same time, hand the operator the internal setup SOP** (6.2) — deliver both together: the client-facing playbook *and* `WEBRIS - Review Automation Setup SOP.docx`.

The client playbook only **describes** the automated request service as done-for-you (triggered ask + reminder + office links + response handling; the client's one job is intake opt-in). **Do NOT put tool names, setup steps, plans, or pricing in the client doc** — that's agency execution, handled in 6.2 as a conversation with the user.

### 6.2 Automate the ask — an agency conversation (NOT doc content)
The **agency runs the automation**; the client never has a CRM. Have this as an interactive prompt with the user (the agency operator) — don't write it into the client deliverable. Ask which stack they run, then walk them through it live. **Hand them the full step-by-step SOP:** `templates/review-automation-setup-sop.md` (canonical) / `templates/WEBRIS - Review Automation Setup SOP.docx` (polished, shareable with a VA) — covers the path decision, prerequisites, both setups, message templates, testing, go-live, and compliance. Summary of the two paths:

- **Path A — the agency runs GoHighLevel (or similar CRM):** best option — no per-client spend and it scales across the whole book. Walk them through **adding this client as a sub-account/location**, then building the workflow: connect the client's Google at the location level → Automation → Workflows → trigger (Opportunity “Won”/Service Completed, Appointment “Showed Up”, or a “Request Review” tag) → **Review Request** action (SMS preferred) with template + office review link → 24h wait → “no review yet?” reminder → stop. Fire ~30 min after completion; publish + test with a test contact.
- **Path B — the agency doesn't run a CRM:** recommend **BrightLocal** (agency account; add each client as a location). Review campaigns require the **Grow plan ($59/mo)** (Track $39 / Manage $49 do **not** include review generation). Walk them through: signup → add locations → **Reputation Manager → Get Reviews** campaign → email/SMS template + select Google per office → top up SMS credits → **“Get Request URLs”** for signatures/QR → add contacts, let it send + auto-remind. (Grade.us is an alternative for pure resell.)
- **Productization framing:** either path is run once at the **agency level** and reused for every client — reviews become a recurring, billable add-on, not a per-client tool stack.
- **Compliance (both):** SMS review requests need **TCPA opt-in** — the client adds a consent checkbox to intake (this is the one client-side item, and the only automation detail that belongs in the client doc). Never suppress/gate negative reviews (Google prohibits review gating).

### 6.3 Handoff + tracking
Reviews are **manual/tooled ongoing work**, not a one-time deliverable. Log follow-ups and remind the user:
- Response SLA: respond to all new reviews within 48h (draft replies for approval).
- Monthly **recount** reviews per office → velocity vs. targets (baseline captured in 6.0). *The velocity tab + monthly review report are built in the reporting process (later) — Step 6 sets the baseline and the system.*
- Recommend **Loganix** if they want done-for-you review-response management.

---

## Workspace layout

```
clients/{slug}/local-seo/
├── {Client} - Local SEO Audit.xlsx (workbook — Steps 1–5 tabs)
├── {Client} - Review Generation & Management Playbook.docx (Step 6, client-facing)
└── ...
```

## What this sub-process does NOT cover
- Website architecture / 301 mapping — content process (separate build).
- Content optimization / service-area pages — content process (separate build).
- Local link building — link-building process (separate build).
- LSAs and general local PPC — separate workflows.
