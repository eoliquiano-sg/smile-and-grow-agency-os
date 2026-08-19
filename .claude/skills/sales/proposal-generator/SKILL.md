---
name: bpt-proposal-generator
description: Generate a professional SEO & GEO proposal with iterative checkpoints.
---

# SEO & GEO Proposal Generator

Generate a comprehensive, visual proposal with competitive analysis, traffic data, local SEO insights, and pricing recommendations.

## Output Format

Single HTML file with:
- 15-25 slides (modular based on configuration)
- Chart.js visualizations
- 1280x720 slide dimensions
- Print-ready styling

## Iterative Workflow

This skill uses a **5-phase iterative workflow** with explicit user checkpoints. At each checkpoint, pause and wait for user feedback before continuing.

There is also a **Phase 0 (Agency Setup)** that only needs to be completed once. It configures the agency-level slides (team, pricing, action plan) that are reused across all proposals.

---

## Phase 0: Agency Setup (One-Time)

**Goal:** Configure agency slides that are used in every proposal.

Before starting your first proposal, check if agency defaults are configured by calling `agency_get`. If the following fields are missing, guide the user to set them up:

### Required for Investment Slide

**Pricing Tiers** - Your standard service packages:

```
agency_update {
  "pricing_tiers": [
    {
      "name": "Starter",
      "monthly": 2500,
      "features": ["Foundation SEO", "2 content pieces/mo", "Monthly reporting"],
      "is_default_recommended": false
    },
    {
      "name": "Growth",
      "monthly": 4500,
      "features": ["Full sprints", "4 content pieces/mo", "Link building", "Bi-weekly calls"],
      "is_default_recommended": true
    },
    {
      "name": "Scale",
      "monthly": 7500,
      "features": ["Everything in Growth", "8 content pieces/mo", "Priority support", "Weekly calls"],
      "is_default_recommended": false
    }
  ]
}
```

### Required for Action Plan Slide

**Action Plan Template** - Your standard implementation phases:

```
agency_update {
  "action_plan_template": [
    {
      "title": "Foundation",
      "period": "Month 1-2",
      "items": ["Technical audit & fixes", "Google Business Profile optimization", "Analytics setup"]
    },
    {
      "title": "Content",
      "period": "Month 2-3",
      "items": ["Keyword research", "Content calendar", "First content sprint"]
    },
    {
      "title": "Authority",
      "period": "Month 3-4",
      "items": ["Link building campaign", "Local citations", "PR outreach"]
    },
    {
      "title": "Scale",
      "period": "Month 5-6",
      "items": ["Content acceleration", "Advanced link building", "Performance optimization"]
    }
  ]
}
```

### Required for The Team Slide

**Proposal Team Members** - Who appears on proposals (use team member IDs):

```
agency_update {
  "proposal_team_members": [
    "{team-member-uuid-1}",
    "{team-member-uuid-2}",
    "{team-member-uuid-3}"
  ]
}
```

To get team member IDs, call `team_list` first.

### Required for Next Steps Slide

**Proposal Defaults** - Standard terms and CTA:

```
agency_update {
  "proposal_defaults": {
    "cta_text": "Schedule Your Strategy Call",
    "expiry_days": 30,
    "contract_length": "6 months",
    "setup_fee": 1500,
    "payment_terms": "Net 15"
  }
}
```

### Alternative: Import from Existing Deck

If the agency already has a sales deck or pitch presentation, extract the info automatically:

**Supported formats:**
- PDF file (provide absolute file path)
- Canva link (public or shared)
- Google Slides link (public or shared)
- Any web URL with agency/pricing info

**How to import:**

1. Ask the user: "Do you have an existing sales deck or pitch presentation I can import from?"

2. If yes, get the file path or URL:
   - For PDF: Use the `Read` tool to read the PDF content
   - For URLs: Use `WebFetch` to retrieve the page content

3. Extract structured data from the content:
   - **Pricing tiers:** Package names, monthly rates, features per tier
   - **Team members:** Names, titles, bios, photos (note photo locations)
   - **Process/phases:** Implementation steps, timeline
   - **Case studies:** Client names, challenges, results
   - **Testimonials:** Quotes, client names, companies
   - **Agency info:** Tagline, description, differentiators

4. Present extracted data to user for confirmation:
   ```
   "Here's what I extracted from your deck:

   **Pricing Tiers:**
   - Starter: $2,500/mo - [features]
   - Growth: $4,500/mo - [features]
   - Scale: $7,500/mo - [features]

   **Team (4 members):**
   - Jane Smith, Founder & CEO
   - John Doe, SEO Director
   ...

   **Process Phases:**
   1. Foundation (Month 1-2): [items]
   2. Content (Month 2-3): [items]
   ...

   Does this look correct? I can adjust anything before saving."
   ```

5. Once confirmed, call `agency_update` with the extracted data:
   ```
   agency_update {
     "pricing_tiers": [...],
     "action_plan_template": [...],
     "proposal_defaults": {...},
     "services": [...],
     "testimonials": [...],
     "case_studies": [...],
     "differentiators": [...]
   }
   ```

6. For team members, create each one:
   ```
   team_create {
     "name": "Jane Smith",
     "email": "jane@agency.com",
     "role": "owner",
     "title": "Founder & CEO",
     "bio": "..."
   }
   ```

7. Then update `proposal_team_members` with the created IDs.

### Check Agency Setup

Before every proposal, verify agency data is configured:

```
agency_get
```

If `pricing_tiers`, `action_plan_template`, or `proposal_team_members` are missing:
1. First ask if they have an existing deck to import from
2. If not, guide them through manual setup above

**Note:** Once configured, these agency slides are automatically populated in every proposal. You can still override them per-proposal by providing custom slide data in `proposal_update_state`.

---

## Phase 1: Discovery & Data Collection

**Goal:** Gather all data and understand the client's situation.

### Step 1.1: Create Proposal Workspace

Ask the user for configuration:

1. **Lead ID** - Which lead is this proposal for?
2. **Business type** - law_firm, local_services, healthcare, ecommerce, saas, or other
3. **Has physical locations?** - Determines if Local SEO module is included
4. **Locations** (if applicable) - Name and address of each location
5. **Competitor domains** - 2-4 main competitors to analyze
6. **Primary service keywords** - e.g., "personal injury lawyer", "car accident attorney"

```
proposal_create {
  "lead_id": "{lead-uuid}",
  "business_type": "law_firm",
  "has_locations": true,
  "locations": [
    { "name": "Sacramento", "gbp_cid": "..." },
    { "name": "Oakland", "gbp_cid": "..." }
  ],
  "competitor_domains": ["competitor1.com", "competitor2.com"],
  "primary_service_keywords": ["personal injury lawyer", "car accident attorney"]
}
```

### Step 1.1b: Check API Availability

Before collecting data, determine which APIs are available:

| Data Type | API Key Required | Check |
|-----------|------------------|-------|
| Traffic History | `AHREFS_API_KEY` | Check if configured in MCP server |
| Top Pages | `AHREFS_API_KEY` | Check if configured in MCP server |
| Referring Domains | `AHREFS_API_KEY` | Check if configured in MCP server |
| Organic Keywords | `AHREFS_API_KEY` | Check if configured in MCP server |
| Local Grid Data | `LOCALFALCON_API_KEY` | Check if configured in MCP server |

Present options to the user:

**If APIs are available:**
"I can collect data via API or you can upload CSVs manually. Here's what's available:

| Data Type | API Status | Action |
|-----------|------------|--------|
| Traffic History | ✓ Ahrefs API | Auto-fetch |
| Top Pages | ✓ Ahrefs API | Auto-fetch |
| Referring Domains | ✓ Ahrefs API | Auto-fetch |
| Local Grid Data | ✓ Local Falcon API | Auto-fetch |

Would you like me to fetch data via API, or do you prefer to upload CSVs manually?"

**If no APIs configured:**
"No API keys are configured. Please upload the required CSV files manually (see CSV Mode below)."

### Step 1.2: Collect Data (API Mode)

If using API mode, fetch data automatically using `proposal_fetch_api_data`:

**Ahrefs Data (requires AHREFS_API_KEY):**

```
proposal_fetch_api_data {
  "proposal_id": "{uuid}",
  "data_type": "ahrefs_traffic"
}

proposal_fetch_api_data {
  "proposal_id": "{uuid}",
  "data_type": "ahrefs_pages"
}

proposal_fetch_api_data {
  "proposal_id": "{uuid}",
  "data_type": "ahrefs_domains"
}

proposal_fetch_api_data {
  "proposal_id": "{uuid}",
  "data_type": "ahrefs_keywords"
}
```

**Local Falcon Data (requires LOCALFALCON_API_KEY):**

For each location/keyword combination:
```
proposal_fetch_api_data {
  "proposal_id": "{uuid}",
  "data_type": "local_falcon",
  "location_name": "Sacramento",
  "keyword": "personal injury lawyer"
}
```

The tool automatically:
- Finds matching reports in Local Falcon
- Transforms data to match CSV-parsed format
- Saves to the proposal's `parsed/` folder
- Updates proposal state with data sources

**API Mode Benefits:**
- No manual CSV exports needed
- Automatic data transformation
- Consistent format across all proposals
- Real-time data (not stale exports)

### Step 1.2: Collect Data (CSV Mode)

If APIs are not configured or you prefer manual uploads, guide the user to upload files to the `inputs/` folder.

**Required for all proposals:**
| Data | Source | Destination |
|------|--------|-------------|
| Traffic history CSV | Ahrefs > Site Explorer > Overview > Export History | `inputs/ahrefs/traffic-history.csv` |
| Top pages CSV | Ahrefs > Site Explorer > Top Pages > Export | `inputs/ahrefs/top-pages.csv` |

**Required if `has_locations: true`:**
| Data | Source | Destination |
|------|--------|-------------|
| Local Falcon grid CSV | Local Falcon > Export Grid (per keyword/location) | `inputs/local-falcon/{keyword}-{location}.csv` |
| Local Falcon data points CSV | Local Falcon > Export Data Points | `inputs/local-falcon/{location}-data.csv` |

> **No Local Falcon data?** If the user doesn't have Local Falcon access or the business has no physical locations, set `has_locations: false` in the proposal config. The Local Performance section will be skipped entirely.

**Optional (enhances specific slides):**
| Data | When Needed | Slide |
|------|-------------|-------|
| Referring domains CSV (×3) | For detailed backlink comparison | Backlink Profile |
| Batch analysis CSV | For location/practice area page performance | Location Pages, Practice Area Content |
| Screaming Frog internal CSV | For technical audit details | Technical SEO Audit |
| Screaming Frog images CSV | For image alt text audit | Technical SEO Audit |
| AI tool screenshots | For GEO visibility panels | GEO/AI Visibility, ChatGPT Detail |
| PageSpeed Insights screenshots | For Core Web Vitals status | Technical SEO Audit |

**Minimum viable proposal:** Traffic history + Top pages CSVs only. All other slides will use API data or be marked for manual completion.

### Step 1.3: Parse All Data Files (CSV Mode Only)

If using CSV mode, parse each uploaded file:

```
proposal_parse_file {
  "proposal_id": "{proposal-uuid}",
  "file_path": "/path/to/traffic-history.csv",
  "file_type": "ahrefs_traffic_history"
}
```

**Auto-save:** By default, `proposal_parse_file` automatically copies input files to the proposal's
`inputs/` folder before parsing (organized by type: `ahrefs/`, `local-falcon/`, `screaming-frog/`).
This preserves the original files in case you need to re-parse or reference them later.

Repeat for each file type:
- `ahrefs_traffic_history`
- `ahrefs_top_pages`
- `ahrefs_referring_domains` (if available)
- `local_falcon` (per keyword/location, requires `location_name` parameter)
- `screaming_frog_internal` (if available)

> **Note:** If using API mode, data is already parsed and saved. Skip this step.

### Step 1.3b: Save Screenshots (Optional)

For screenshots that don't need parsing (AI tools, PageSpeed, etc.), use `file_save`:

```
file_save {
  "context_type": "proposal",
  "context_id": "{proposal-uuid}",
  "subfolder": "screenshots",
  "filename": "chatgpt-response.png",
  "content": "iVBORw0KGgo...",
  "encoding": "base64"
}
```

This saves the file to `inputs/screenshots/` within the proposal folder.

### Step 1.4: Classify Pages into Funnel

```
proposal_classify_pages {
  "proposal_id": "{proposal-uuid}",
  "pages": [/* from parsed top_pages */]
}
```

---

## CHECKPOINT 1: Data Summary

**STOP and present to user:**

"Here's what I found from the data collection:"

### Client Metrics
| Metric | Current | vs. Peak | vs. Competitors |
|--------|---------|----------|-----------------|
| Domain Rating | {dr} | - | {comparison} |
| Monthly Traffic | {traffic} | {delta}% from {peak_date} | {comparison} |
| Traffic Value | ${value}/mo | - | {comparison} |
| Referring Domains | {rds} | - | {comparison} |

### Traffic Trend
- **Status:** {Growing / Stable / Declining}
- {If declining: "Traffic has dropped {X}% from peak ({peak_traffic} in {peak_date}) to {current_traffic} today."}

### Local Visibility (if `has_locations: true`)
| Location | Keyword | SoLV% | ARP | Status |
|----------|---------|-------|-----|--------|
| {location} | {keyword} | {solv}% | {arp} | {Critical/Partial/Strong} |

### Local Visibility (if `has_locations: false`)
> "This is a non-local/national business - Local Performance section will be skipped. Proposal will focus on organic SEO, content, and backlinks."

### Data Gaps
{List any missing data or issues found}

**Ask user:** "Does this look correct? Say 'continue' to proceed to analysis, or let me know what needs correction."

> **Tip:** If local data is missing but should be included, the user can provide Local Falcon exports now. If the business genuinely has no physical locations, confirm `has_locations: false` and continue.

---

## Phase 2: Analysis & Insights

**Goal:** Analyze the data and identify strategic angles.

### Step 2.1: Identify Traffic Decline Causes (if applicable)

If traffic declined ≥15% from peak, analyze potential causes:
- Algorithm update timing
- Lost rankings on key pages
- Technical issues
- Competitor gains

### Step 2.2: Analyze Funnel Distribution

Examine traffic by buyer journey stage (top to bottom of funnel):
- Awareness (top of funnel) - What percentage? Informational, educational queries
- Consideration - What percentage? Comparison, "best", research queries
- Decision (high intent) - What percentage? Local/service keywords, "hire", "near me"
- Branded (bottom) - What percentage? Direct brand/firm name searches

### Step 2.3: Find Content Gaps

Compare client pages vs. competitor rankings to identify opportunities.

### Step 2.4: Assess Local Visibility (if applicable)

Analyze Local Falcon data:
- SoLV% (Share of Local Voice) by location
- ARP (Average Rank Position) trends
- Top GBP competitors

### Step 2.5: Identify Technical Issues (if applicable)

From Screaming Frog data:
- Missing titles/meta descriptions
- Thin content pages
- Broken links
- Indexability issues

---

## CHECKPOINT 2: Strategic Angles

**STOP and present to user:**

If data supports multiple distinct angles, present 2-3 options:

"Based on my analysis, here are the strategic angles I see for this proposal:"

### Angle A: {Title}
**Why this resonates:** {1-2 sentences}
**Key data points:**
- {Point 1}
- {Point 2}
- {Point 3}
**How it shapes the narrative:** {1 sentence}

### Angle B: {Title}
**Why this resonates:** {1-2 sentences}
**Key data points:**
- {Point 1}
- {Point 2}
- {Point 3}
**How it shapes the narrative:** {1 sentence}

### Angle C: {Title} (if data supports a third)
**Why this resonates:** {1-2 sentences}
**Key data points:**
- {Point 1}
- {Point 2}
- {Point 3}
**How it shapes the narrative:** {1 sentence}

**Ask user:** "Which angle should we use? You can also provide a different direction, or say 'continue' to use the first angle."

**If data is sparse** (limited metrics, single data source, or unclear differentiation):

"Based on the available data, I recommend this general approach:"

### Recommended Approach: {Title}
**Focus:** {1-2 sentences on the primary narrative}
**Key data points:**
- {Point 1}
- {Point 2}
**How it shapes the narrative:** {1 sentence}

**Ask user:** "Does this approach work? Say 'continue' to proceed, or provide a different direction."

---

## Phase 3: Outline & Structure

**Goal:** Build the proposal outline based on selected angle.

### Step 3.1: Determine Slides to Include

Based on configuration and data. Final slide count depends on optional slides included and number of locations.

**Typical counts:**
- No locations (national/online business): ~18-22 slides
- Single location: ~20-25 slides
- Multi-location (4 offices): ~28-35 slides

---

**Website Performance Section:**
| Slide | Status | Condition |
|-------|--------|-----------|
| Cover | Required | Always |
| Executive Summary | Required | Built last - summarizes all findings |
| The Market | Required | Competitor comparison table |
| Section Cover: Performance | Required | Visual divider |
| Organic Performance | Required | 24-month traffic + KPIs |
| Why Has Traffic Fallen? | Optional | Only if ≥15% decline from peak |
| Marketing Funnel | Required | Traffic by buyer journey stage |

**GEO / AI Visibility Section:**
| Slide | Status | Condition |
|-------|--------|-----------|
| GEO / AI Visibility | Required | 4-platform panel (Google AI, ChatGPT, Perplexity, Gemini) |
| ChatGPT Detail | Required | Dedicated close-up with annotations |

**Local Performance Section:**
| Slide | Status | Condition |
|-------|--------|-----------|
| Local Pack (×N) | **Skip if no locations** | One per location - 5×5 grid + SoLV% |
| Local Competitors: All Markets | **Skip if no locations** | If 2+ locations - competitor summary grid |
| Location Pages (×N) | **Skip if no locations** | One per location - hub performance |
| Citation Review | **Skip if no locations** | 14-directory audit table |

> **No locations?** If `has_locations: false`, skip the entire Local Performance section. The proposal focuses on organic SEO only. Citation Review moves to Backlinks section or is omitted entirely for non-local businesses.

**Content Performance Section:**
| Slide | Status | Condition |
|-------|--------|-----------|
| Top Pages | Required | Top 10 pages by traffic |
| Practice Area & Blog Performance | Optional | If meaningful content volume exists |
| Competitor Content Gap | Optional | If client lacks practice area pages |
| On-Site Content Optimisation | Optional | If pages have ranking potential but need depth |

**Backlinks & Citations Section:**
| Slide | Status | Condition |
|-------|--------|-----------|
| Backlink Profile: Competitive Comparison | Required | RD quality metrics vs competitors |
| Citation Review | Required | **Only if has_locations** - otherwise skip |

**Technical Optimisation Section:**
| Slide | Status | Condition |
|-------|--------|-----------|
| Technical SEO Audit | Optional | Only if significant issues found |
| Analysis Recap | Required | Built last - 5-row summary table |

**Forecast & Offer Section:**
| Slide | Status | Condition |
|-------|--------|-----------|
| Section Cover: Planning | Optional | Visual divider before recommendations |
| Traffic Projection | Required | 12-month dual trajectory chart |
| Action Plan | Required | 3-6 month roadmap |
| Investment | Required | Pricing tiers from agency.json |

**Social Proof Section:**
| Slide | Status | Condition |
|-------|--------|-----------|
| Case Studies (×3-5) | Optional | If relevant case studies available |
| Social Proof: Client Logos | Optional | If prospect unfamiliar with agency |

**Closing Section:**
| Slide | Status | Condition |
|-------|--------|-----------|
| The Team | Required | Team cards + agency differentiators |
| Next Steps | Required | CTA, calendar link, expiry date |

### Step 3.2: Assign Key Points Per Slide

For each slide, determine the key talking points based on the selected angle.

---

## CHECKPOINT 3: Proposal Outline

**STOP and present to user:**

"Here's the proposed outline for this proposal:"

### Slide Structure ({N} slides total)

| # | Slide | Key Points |
|---|-------|------------|
| 1 | Cover | {client_name}, prepared by {agency_name} |
| 2 | Executive Summary | {1-sentence description} |
| 3 | The Market | {1-sentence description} |
| ... | ... | ... |

### Conditional Slides
- **Why Has Traffic Fallen?** - {Included/Excluded because...}
- **Practice Area & Blog Performance** - {Included/Excluded because...}
- **Competitor Content Gap** - {Included/Excluded because...}
- **On-Site Content Optimisation** - {Included/Excluded because...}
- **Technical Audit** - {Included/Excluded because...}
- **Case Studies** - {Included/Excluded because...}
- **Social Proof: Client Logos** - {Included/Excluded because...}
- **Local SEO Module** - {Included/Excluded because...}

**Ask user:** "Does this outline work? You can reorder slides, add/remove any, or adjust the focus."

---

## Phase 4: Slide-by-Slide Building

**Goal:** Build each slide with user review at section checkpoints.

### Section A: Context Setting (Slides 1-5)

Build these slides using the data and prompts below:

**Slide 1: Cover**
- Client name and primary office address
- Presentation date
- Subtitle: "SEO & GEO Analysis"
- Agency logo and branding

**Slide 2: Executive Summary** (PLACEHOLDER - will finalize last)
- Three-part layout: (1) Firm overview, (2) Current challenges (3-5 bullets), (3) Proposed growth strategy (3-5 bullets)
- Leave placeholder until all analysis slides complete

**Slide 3: The Market**
- Competitor comparison table (client highlighted)
- Columns: Firm name, markets served, DR, monthly traffic, traffic value, Google reviews, star rating, years in business
- 3-4 positioning callouts below table

**Slide 4: Section Cover: Performance**
- Visual divider marking start of performance analysis
- Section title and one-line description

**Slide 5: Organic Performance**
- Five KPI tiles: DR, ranking keywords, monthly traffic, traffic value (USD), referring domains
- Dual-axis line chart: traffic (left) and traffic value (right) over 24 months
- Peak month annotated with red dot
- % decline callout from peak to current

After building each slide, update state:
```
proposal_update_state {
  "proposal_id": "{proposal-uuid}",
  "slide_updates": [{ "id": "the_market", "status": "completed", "data": {...} }]
}
```

---

## CHECKPOINT 4A: Context Slides Preview

**STOP and present to user:**

"Here's the preview of the context-setting slides (1-4):"

{Summarize each slide's content}

**Ask user:** "Any changes needed before I continue with the analysis slides?"

---

### Section B: Analysis Deep-Dive (Slides 6-18+)

Build based on data:

**Slide 6: Why Has Traffic Fallen?** (Optional - if ≥15% decline)
- Number of causes depends on what data reveals
- Cross-reference traffic history, top pages, Screaming Frog against Google algorithm update timeline
- Possible causes: algorithm updates, URL restructuring, content decay, AI Overview cannibalization, technical crawl blockers, backlink equity loss

**Slide 7: Marketing Funnel**
- Funnel diagram on left showing stages in order from top (widest) to bottom (narrowest):
  1. **Awareness** (top) - blue - informational queries
  2. **Consideration** - gold/amber - comparison queries
  3. **Decision** - red/green - high-intent local/service queries
  4. **Branded** (bottom) - purple - direct brand searches
- Four stage cards on right (same order: Awareness → Consideration → Decision → Branded)
- Each shows: % of traffic, visits/mo, page count, top 3 keywords, what stage delivers, growth opportunity

**Slide 8: GEO / AI Visibility**
- Four platform panels: Google AI Overview, ChatGPT, Perplexity, Gemini
- Each shows: query used, screenshot, status badge (Cited / Not Cited / Competitor Cited)
- Total citation count from Ahrefs Site Explorer Overview

**Slide 9: ChatGPT Detail**
- Full ChatGPT response screenshot for primary query
- Annotated: whether firm appears, at what position, which competitors cited instead

---

**LOCAL PERFORMANCE MODULE** (Skip entirely if `has_locations: false`)

> If the business has no physical locations, skip directly to "Top Pages" slide below.

**Slides 10+: Local Pack** (one per location)
- Local Falcon 5×5 heatmap grid (25 points, 5-mile radius)
- SoLV % displayed prominently
- Average Rank Position (ARP)
- Status badge: Critical (<10%), Partial (10-40%), Strong (>40%)

**Local Competitors: All Markets** (if 2+ locations)
- 2×2 grid - one card per market
- Each card: market name, top 3 Local Pack competitors by frequency
- Per competitor: review count, star rating, primary/secondary business category

**Location Pages** (one per location)
- Location card: total pages in hub, pages with ≥1 visit vs. zero-traffic, total monthly visits
- "Top Page" callout strip naming best-performing page and traffic

**Citation Review** (local businesses only)
- Total citation count headline metric
- Table of 14 directories with status badges

---

**CONTENT PERFORMANCE** (All proposals)

**Top Pages**
- Table of top 10 pages by traffic
- Columns: URL slug, monthly traffic, top keyword, search volume, traffic change (green/red), funnel stage
- Right panel: 3-5 key takeaways

**Slide 14: Practice Area & Blog Performance** (Optional)
- Same format as location pages for /practice-area/ and /blog/ URLs
- Table: section name, total pages, pages with traffic vs. zero-traffic, monthly visits, best page
- Key observations panel

**Slide 15: Competitor Content Gap** (Optional - if client lacks practice area pages)
- Table of top-performing competitor pages filtered to practice area and location URLs
- Columns: competitor domain, page URL, monthly traffic, top keyword, search volume
- Observations panel highlighting topics client lacks

**Slide 16: On-Site Content Optimisation** (Optional - if pages have ranking potential but need depth)
- Side-by-side comparison: client page vs. top 2-3 ranking competitors for same keyword
- Columns: URL, word count, FAQ section, internal links, images, schema markup, current position
- Observations panel noting specific gaps

**Slide 17: Backlink Profile: Competitive Comparison**
- Comparison table: client + 2 competitors as columns
- 7 quality metrics as rows: total RDs, dofollow, nofollow, DR=0, spam (flag if >20%), no-traffic (flag if >40%)
- DR and total backlinks from API, RD quality counts from CSV exports

**Slide 18: Citation Review**
- Total citation count headline metric
- Table of 14 directories: Avvo, Justia, FindLaw, Lawyers.com/Martindale-Hubbell, Super Lawyers, Best Lawyers, Nolo, HG.org, BBB, Yelp, Alignable, Expertise.com, Chamber of Commerce, Attorney Yellow Pages
- Each row: directory name, domain authority, status badge (Verified / Needs Improvement / Missing), profile URL

---

## CHECKPOINT 4B: Analysis Slides Preview

**STOP and present to user:**

"Here's the preview of the analysis slides:"

{Summarize each slide's content}

**Ask user:** "Any changes needed before I continue with findings and recommendations?"

---

### Section C: Findings & Recommendations (Slides 19-32)

**Slide 19: Technical SEO Audit** (Optional - if significant issues)
- Audit table with status per item (Pass / Improvement Needed / Fail)
- 17 items: missing/duplicate titles, missing/duplicate meta descriptions, missing/duplicate H1s, Core Web Vitals (desktop + mobile), HTTPS, robots.txt/sitemap, AI crawlability (GPTBot, ClaudeBot, PerplexityBot), 301 redirects, 404 errors, Attorney/Person schema, FAQ schema, Organization schema, image alt text

**Slide 20: Analysis Recap**
- Five-row summary table: Website Performance, GBP & Local Performance, Technical SEO, Content Performance, Backlinks & Citations
- Each row: status badge, 2-sentence summary with real figures, 3 key metric chips

**Slide 21: Section Cover: Planning** (Optional)
- Visual divider marking transition from audit to plan
- Section title "Plan of Attack" or similar

**Slide 22: Traffic Projection**
- Line chart with two trajectories over 12 months:
  - Current trajectory: average monthly change from last 3 months projected forward
  - Target trajectory: 5-10% monthly growth based on planned SEO work
- Dashed reference line at historical peak
- Both lines annotated at 12-month endpoint
- Note: projections are directional estimates, not guarantees

**Slide 23: Action Plan**
- Three time-boxed buckets with 6-8 specific tasks each:
  - Month 1-2: Technical Foundation (on-page fixes, schema, citation gaps)
  - Month 3-4: Content & Local (location pages, GBP review outreach, content depth)
  - Month 5-6: Authority & AI (link building, AI citation optimization, internal linking)
- Each task references specific audit finding

**Slide 24: Investment**
- Scoped retainer table with deliverables, monthly fee, timeline
- May include tiered options (from agency.json pricing_tiers)

**Slides 25-29: Case Studies (×3-5)** (Optional)
- Per case study: client name (or anonymized), practice area, market
- Organic traffic line chart with engagement start date annotated
- Key outcome metrics: traffic at start, traffic at end, % growth

**Slide 30: Social Proof: Client Logos** (Optional)
- Grid of 12-16 law firm client logos on clean background
- No copy beyond section title

**Slide 31: The Team**
- Four feature cards presenting agency differentiators
- Dedicated team member grid: Account Strategist, Technical SEO Specialist, Content Writer, Link Builder, Local SEO Specialist
- Each with role title, initials, one-line contribution description

**Slide 32: Next Steps**
- CTA button/text (from proposal_defaults.cta_text)
- Calendar link for scheduling
- Contact information
- Proposal expiry date (from proposal_defaults.expiry_days)

---

## CHECKPOINT 4C: Findings & Recommendations Preview

**STOP and present to user:**

"Here's the preview of the findings and recommendations slides:"

{Summarize each slide's content}

**Ask user:** "Any changes to pricing, projections, or recommendations before I finalize the summary slides?"

---

### Section D: Summary Slides (Built Last)

Now go back and finalize:

**Slide 2: Executive Summary**
- 4 key opportunities (from analysis)
- 4 key challenges (from analysis)
- Current metrics

**Analysis Recap**
- 4-5 challenges
- 4-5 opportunities
- Bottom line statement

---

## CHECKPOINT 4D: Summary Slides Preview

**STOP and present to user:**

"Here are the finalized summary slides:"

**Executive Summary:**
- Opportunities: {list}
- Challenges: {list}

**Analysis Recap:**
- Challenges: {list}
- Opportunities: {list}
- Bottom line: {statement}

**Ask user:** "Ready to generate the final HTML? Any last changes?"

---

## Phase 5: Final Assembly

**Goal:** Generate final HTML and verify.

### Step 5.1: Generate HTML

```
proposal_generate_html { "proposal_id": "{proposal-uuid}" }
```

This will:
- Compile all slide templates with Handlebars
- Inject Chart.js visualizations
- Apply CSS styling
- Save to `output/proposal.html`

### Step 5.2: Verify Output

Check the generated file for:
- All placeholders replaced
- Charts rendering correctly
- Correct slide count

---

## CHECKPOINT 5: Final Review

**STOP and present to user:**

"The proposal has been generated!"

**Output location:** `{output_path}`

**Slides included:** {list all slide IDs}

**Verification checklist:**
- [ ] Open in browser at 1280x720
- [ ] All client names correct (no placeholder text visible)
- [ ] Charts display correctly
- [ ] Print/PDF export works

**Next steps:**
1. Open the HTML file in your browser
2. Review each slide
3. Make any final edits directly in the HTML if needed
4. Export to PDF for sending

**Optional:** "Want a spreadsheet with the underlying data and calculations? Just ask and I'll export it."

**To update lead status:**
```
leads_transition {
  "id": "{lead-uuid}",
  "new_status": "proposal_sent",
  "note": "SEO & GEO proposal v1 generated"
}
```

---

## MCP Tools Reference

| Tool | Purpose |
|------|---------|
| `proposal_create` | Initialize workspace with configuration |
| `proposal_get_state` | Check progress and current slide |
| `proposal_update_state` | Update slide completion status and data |
| `proposal_list` | List proposals for a lead |
| `proposal_fetch_api_data` | Fetch data from APIs (Ahrefs, Local Falcon) |
| `proposal_parse_file` | Parse CSV data files (auto-saves inputs before parsing) |
| `proposal_classify_pages` | Classify pages into funnel stages |
| `proposal_generate_html` | Generate final HTML output |
| `proposal_get_citation_directories` | Get industry directory checklist |
| `file_save` | Save files (screenshots, assets) to workspace |

### Data Types for proposal_fetch_api_data

| Data Type | API Required | Description |
|-----------|--------------|-------------|
| `ahrefs_traffic` | `AHREFS_API_KEY` | 24-month traffic history with value |
| `ahrefs_pages` | `AHREFS_API_KEY` | Top pages by traffic |
| `ahrefs_domains` | `AHREFS_API_KEY` | Referring domains with DR distribution |
| `ahrefs_keywords` | `AHREFS_API_KEY` | Organic keyword rankings |
| `local_falcon` | `LOCALFALCON_API_KEY` | Local Pack grid data (requires `location_name`) |

### File Types for proposal_parse_file (CSV Mode)

| File Type | Source | Notes |
|-----------|--------|-------|
| `ahrefs_traffic_history` | Ahrefs > Site Explorer > Export History | UTF-16 |
| `ahrefs_top_pages` | Ahrefs > Top Pages > Export | UTF-16 |
| `ahrefs_referring_domains` | Ahrefs > Backlinks > Referring Domains | UTF-16 |
| `ahrefs_batch_analysis` | Ahrefs > Batch Analysis | UTF-16 |
| `ahrefs_organic_keywords` | Ahrefs > Organic Keywords > Export | UTF-16 |
| `local_falcon` | Local Falcon > Export Grid | Requires `location_name` |
| `screaming_frog_internal` | Screaming Frog > Internal > Export | UTF-8 |
| `screaming_frog_images` | Screaming Frog > Images > Export | UTF-8 |

---

## Slide Data Reference

When building slides, use these data structures for `proposal_update_state`.

**Note:** The following slides are auto-populated from agency.json if no custom data is provided:
- **The Team** - Uses `proposal_team_members` to filter team members
- **Investment** - Uses `pricing_tiers` and `proposal_defaults`
- **Action Plan** - Uses `action_plan_template`
- **Next Steps** - Uses `calendar_link`, `email`, and `proposal_defaults`

You can override any of these by providing custom slide data.

### Cover
```json
{
  "id": "cover",
  "status": "completed",
  "data": {
    "client_name": "Acme Corp",
    "address": "123 Main St, Sacramento, CA",
    "date": "April 24, 2026",
    "subtitle": "SEO & GEO Analysis",
    "agency_name": "Your Agency"
  }
}
```

### Executive Summary
```json
{
  "id": "executive_summary",
  "status": "completed",
  "data": {
    "firm_name": "Acme Corp",
    "num_attorneys": 12,
    "practice_areas": ["Personal Injury", "Car Accidents", "Workers Compensation"],
    "locations": ["Sacramento", "Oakland"],
    "challenges": [
      "Traffic has declined 35% from peak",
      "Local Pack visibility below 20% SoLV in all markets",
      "Missing LocalBusiness and Attorney schema",
      "Thin location pages with no unique content"
    ],
    "strategy": [
      "Technical foundation fixes in Month 1-2",
      "Location page expansion with unique content",
      "GBP optimization and review generation campaign",
      "Authority building through targeted link acquisition"
    ]
  }
}
```

### The Market
```json
{
  "id": "the_market",
  "status": "completed",
  "data": {
    "competitors": [
      {
        "name": "Acme Corp",
        "is_client": true,
        "markets": "Sacramento, Oakland",
        "dr": 45,
        "traffic": 15000,
        "traffic_value": 25000,
        "reviews": 127,
        "rating": 4.8,
        "years_in_business": 15
      },
      {
        "name": "Competitor Law",
        "is_client": false,
        "markets": "Sacramento",
        "dr": 52,
        "traffic": 28000,
        "traffic_value": 45000,
        "reviews": 312,
        "rating": 4.9,
        "years_in_business": 22
      }
    ],
    "callouts": [
      "Client has highest DR among Sacramento firms",
      "Review volume lags top competitor by 2.5x",
      "Traffic gap of 13,000 visits/mo vs. market leader"
    ]
  }
}
```

### Section Cover: Performance
```json
{
  "id": "section_cover_performance",
  "status": "completed",
  "data": {
    "title": "Website Performance",
    "description": "24-month organic traffic analysis and competitive positioning"
  }
}
```

### Organic Performance
```json
{
  "id": "organic_performance",
  "status": "completed",
  "data": {
    "dr": 45,
    "traffic": 15000,
    "traffic_value": 25000,
    "referring_domains": 350,
    "has_decline": true,
    "decline_percent": 35,
    "peak_date": "March 2025",
    "traffic_history": [
      { "date": "Apr 2025", "traffic": 20000, "traffic_value": 35000 },
      { "date": "May 2025", "traffic": 18000, "traffic_value": 30000 }
    ]
  }
}
```

### Marketing Funnel

**IMPORTANT: Funnel stage order (top to bottom):** Awareness → Consideration → Decision → Branded

The marketing funnel visual should always show stages in this order from widest (top) to narrowest (bottom):
1. **Awareness** (top of funnel) - informational queries, blog content, general research
2. **Consideration** - comparison queries, "best" searches, reviews
3. **Decision** - high-intent queries with location/service keywords, "near me", "hire", "attorney"
4. **Branded** (bottom) - direct brand searches, re-finds

```json
{
  "id": "marketing_funnel",
  "status": "completed",
  "data": {
    "awareness_traffic": 6000,
    "awareness_value": 3000,
    "awareness_percent": 40,
    "awareness_bar_width": 80,
    "consideration_traffic": 3000,
    "consideration_value": 5000,
    "consideration_percent": 20,
    "consideration_bar_width": 60,
    "decision_traffic": 5000,
    "decision_value": 15000,
    "decision_percent": 33,
    "decision_bar_width": 100,
    "branded_traffic": 1000,
    "branded_value": 2000,
    "branded_percent": 7,
    "branded_bar_width": 21,
    "insights": [
      "Strong decision-stage traffic indicates good conversion potential",
      "Awareness content drives volume but low value"
    ]
  }
}
```

### Local Pack
```json
{
  "id": "local_pack_0",
  "status": "completed",
  "data": {
    "location": "Sacramento",
    "keyword": "personal injury lawyer sacramento",
    "grid": [[1,2,3,0,0],[2,1,4,5,0],[3,2,1,2,3],[0,4,3,2,1],[0,0,5,4,2]],
    "solv_percent": 36,
    "arp": 2.4,
    "status_badge": "partial",
    "analysis": "Strong visibility in the city center, but weak in outer areas.",
    "top_competitors": [
      { "name": "Competitor A", "avg_rank": 1.8 },
      { "name": "Competitor B", "avg_rank": 2.1 }
    ]
  }
}
```

### Local Competitors: All Markets
```json
{
  "id": "local_competitors",
  "status": "completed",
  "data": {
    "markets": [
      {
        "name": "Sacramento",
        "competitors": [
          {
            "name": "Competitor Law",
            "reviews": 312,
            "rating": 4.9,
            "primary_category": "Personal Injury Attorney",
            "secondary_category": "Law Firm"
          },
          {
            "name": "Smith & Associates",
            "reviews": 187,
            "rating": 4.7,
            "primary_category": "Personal Injury Attorney",
            "secondary_category": "Lawyer"
          },
          {
            "name": "Johnson Legal",
            "reviews": 145,
            "rating": 4.8,
            "primary_category": "Personal Injury Attorney",
            "secondary_category": "Attorney"
          }
        ]
      },
      {
        "name": "Oakland",
        "competitors": [
          {
            "name": "Bay Area Injury Law",
            "reviews": 278,
            "rating": 4.8,
            "primary_category": "Personal Injury Attorney",
            "secondary_category": "Law Firm"
          }
        ]
      }
    ]
  }
}
```

### Investment
```json
{
  "id": "investment",
  "status": "completed",
  "data": {
    "tiers": [
      {
        "name": "Starter",
        "monthly": 2500,
        "features": ["Foundation SEO", "2 content pieces/mo", "Monthly reporting"]
      },
      {
        "name": "Growth",
        "monthly": 4500,
        "recommended": true,
        "features": ["Full sprints", "4 content pieces/mo", "Link building", "Bi-weekly calls"]
      },
      {
        "name": "Scale",
        "monthly": 7500,
        "features": ["Everything in Growth", "8 content pieces/mo", "Priority support", "Weekly calls"]
      }
    ],
    "contract_length": "6 months",
    "setup_fee": 1500,
    "payment_terms": "Net 15"
  }
}
```

### Why Has Traffic Fallen?
```json
{
  "id": "why_traffic_fallen",
  "status": "completed",
  "data": {
    "causes": [
      {
        "title": "March 2025 Core Update",
        "description": "Traffic dropped 18% within 2 weeks of the March core update rollout",
        "evidence": "Traffic history shows decline starting March 15, 2025"
      },
      {
        "title": "Content Decay",
        "description": "Top 5 pages lost average of 12 positions over 6 months",
        "evidence": "Top pages CSV shows negative traffic change for 8 of top 10 pages"
      }
    ],
    "recovery_actions": [
      "Update and expand decayed content",
      "Add fresh statistics and case results",
      "Improve internal linking to key pages"
    ]
  }
}
```

### GEO / AI Visibility
```json
{
  "id": "geo_ai_visibility",
  "status": "completed",
  "data": {
    "citation_count": 127,
    "platforms": [
      {
        "name": "Google AI Overview",
        "query": "best personal injury lawyer sacramento",
        "screenshot_path": "inputs/screenshots/google-ai-overview.png",
        "status": "not_cited"
      },
      {
        "name": "ChatGPT",
        "query": "best personal injury lawyer sacramento",
        "screenshot_path": "inputs/screenshots/chatgpt.png",
        "status": "competitor_cited",
        "competitor_name": "Competitor Law"
      },
      {
        "name": "Perplexity",
        "query": "best personal injury lawyer sacramento",
        "screenshot_path": "inputs/screenshots/perplexity.png",
        "status": "cited"
      },
      {
        "name": "Gemini",
        "query": "best personal injury lawyer sacramento",
        "screenshot_path": "inputs/screenshots/gemini.png",
        "status": "not_cited"
      }
    ]
  }
}
```

### ChatGPT Detail
```json
{
  "id": "chatgpt_detail",
  "status": "completed",
  "data": {
    "query": "best personal injury lawyer sacramento",
    "screenshot_path": "inputs/screenshots/chatgpt-full.png",
    "firm_appears": false,
    "firm_position": null,
    "competitors_cited": [
      { "name": "Competitor Law", "position": 1 },
      { "name": "Another Firm", "position": 2 },
      { "name": "Third Firm", "position": 3 }
    ],
    "analysis": "Client is not currently cited by ChatGPT for primary PI query. Top 3 cited competitors all have higher review counts and more comprehensive practice area content."
  }
}
```

### Top Pages
```json
{
  "id": "top_pages",
  "status": "completed",
  "data": {
    "pages": [
      {
        "url": "/car-accident-lawyer/",
        "traffic": 2500,
        "top_keyword": "car accident lawyer sacramento",
        "search_volume": 1900,
        "traffic_change": -15,
        "funnel_stage": "decision"
      },
      {
        "url": "/personal-injury/",
        "traffic": 1800,
        "top_keyword": "personal injury lawyer",
        "search_volume": 2400,
        "traffic_change": -8,
        "funnel_stage": "decision"
      }
    ],
    "takeaways": [
      "Decision-stage pages drive 65% of traffic value",
      "All top 5 pages show negative traffic change vs. prior period",
      "No blog content in top 10 - awareness funnel underserved"
    ]
  }
}
```

### Location Pages
```json
{
  "id": "location_pages_0",
  "status": "completed",
  "data": {
    "location": "Sacramento",
    "total_pages": 12,
    "pages_with_traffic": 4,
    "zero_traffic_pages": 8,
    "total_visits": 850,
    "top_page": {
      "url": "/sacramento/car-accident-lawyer/",
      "traffic": 450
    }
  }
}
```

### Practice Area & Blog Performance
```json
{
  "id": "practice_area_content",
  "status": "completed",
  "data": {
    "sections": [
      {
        "name": "Practice Areas",
        "total_pages": 15,
        "pages_with_traffic": 8,
        "zero_traffic_pages": 7,
        "total_visits": 3200,
        "top_page": { "url": "/car-accident-lawyer/", "traffic": 2500 }
      },
      {
        "name": "Blog",
        "total_pages": 42,
        "pages_with_traffic": 12,
        "zero_traffic_pages": 30,
        "total_visits": 890,
        "top_page": { "url": "/blog/what-to-do-after-car-accident/", "traffic": 220 }
      }
    ],
    "observations": [
      "71% of blog posts generate zero organic traffic",
      "Practice area pages outperform blog 3.5:1 on traffic value",
      "No FAQ schema on any practice area page"
    ]
  }
}
```

### Competitor Content Gap
```json
{
  "id": "competitor_content_gap",
  "status": "completed",
  "data": {
    "competitor_pages": [
      {
        "competitor": "competitorlaw.com",
        "url": "/truck-accident-lawyer/",
        "traffic": 1200,
        "top_keyword": "truck accident lawyer sacramento",
        "search_volume": 720
      },
      {
        "competitor": "competitorlaw.com",
        "url": "/motorcycle-accident/",
        "traffic": 890,
        "top_keyword": "motorcycle accident attorney",
        "search_volume": 590
      }
    ],
    "observations": [
      "Client missing dedicated truck accident page - competitor gets 1,200 visits/mo",
      "No motorcycle accident content vs. 3 competitor pages",
      "Wrongful death topic underserved - 2,100 monthly search volume available"
    ]
  }
}
```

### On-Site Content Optimisation
```json
{
  "id": "onsite_content_optimisation",
  "status": "completed",
  "data": {
    "comparisons": [
      {
        "keyword": "car accident lawyer sacramento",
        "client": {
          "url": "/car-accident-lawyer/",
          "word_count": 850,
          "has_faq": false,
          "internal_links": 3,
          "images": 1,
          "has_schema": false,
          "position": 8
        },
        "competitors": [
          {
            "url": "competitorlaw.com/car-accident-attorney/",
            "word_count": 2400,
            "has_faq": true,
            "internal_links": 12,
            "images": 5,
            "has_schema": true,
            "position": 2
          }
        ]
      }
    ],
    "observations": [
      "Client page is 65% thinner than top-ranking competitor",
      "Missing FAQ section that all top 3 competitors have",
      "No Attorney schema vs. 100% implementation by competitors"
    ]
  }
}
```

### Backlink Profile
```json
{
  "id": "backlink_profile",
  "status": "completed",
  "data": {
    "comparison": [
      {
        "domain": "client.com",
        "is_client": true,
        "total_rds": 350,
        "dofollow_rds": 280,
        "nofollow_rds": 70,
        "dr_zero_rds": 45,
        "spam_rds": 28,
        "spam_percent": 8,
        "no_traffic_rds": 120,
        "no_traffic_percent": 34
      },
      {
        "domain": "competitor.com",
        "is_client": false,
        "total_rds": 520,
        "dofollow_rds": 410,
        "nofollow_rds": 110,
        "dr_zero_rds": 65,
        "spam_rds": 125,
        "spam_percent": 24,
        "spam_flagged": true,
        "no_traffic_rds": 245,
        "no_traffic_percent": 47,
        "no_traffic_flagged": true
      }
    ]
  }
}
```

### Citation Review
```json
{
  "id": "citation_review",
  "status": "completed",
  "data": {
    "total_citations": 127,
    "directories": [
      { "name": "Avvo", "da": 93, "status": "verified", "url": "https://avvo.com/..." },
      { "name": "Justia", "da": 91, "status": "verified", "url": "https://justia.com/..." },
      { "name": "FindLaw", "da": 89, "status": "needs_improvement", "url": "https://findlaw.com/..." },
      { "name": "Lawyers.com", "da": 87, "status": "missing", "url": null },
      { "name": "Super Lawyers", "da": 85, "status": "verified", "url": "https://superlawyers.com/..." },
      { "name": "Best Lawyers", "da": 82, "status": "missing", "url": null },
      { "name": "Nolo", "da": 80, "status": "needs_improvement", "url": "https://nolo.com/..." },
      { "name": "HG.org", "da": 78, "status": "missing", "url": null },
      { "name": "BBB", "da": 95, "status": "verified", "url": "https://bbb.org/..." },
      { "name": "Yelp", "da": 94, "status": "verified", "url": "https://yelp.com/..." },
      { "name": "Alignable", "da": 72, "status": "missing", "url": null },
      { "name": "Expertise.com", "da": 70, "status": "verified", "url": "https://expertise.com/..." },
      { "name": "Chamber of Commerce", "da": 68, "status": "missing", "url": null },
      { "name": "Attorney Yellow Pages", "da": 55, "status": "missing", "url": null }
    ]
  }
}
```

### Technical SEO Audit
```json
{
  "id": "technical_audit",
  "status": "completed",
  "data": {
    "items": [
      { "name": "Missing title tags", "status": "pass", "count": 0 },
      { "name": "Duplicate title tags", "status": "improvement_needed", "count": 8 },
      { "name": "Missing meta descriptions", "status": "improvement_needed", "count": 12 },
      { "name": "Duplicate meta descriptions", "status": "fail", "count": 23 },
      { "name": "Missing H1s", "status": "pass", "count": 0 },
      { "name": "Duplicate H1s", "status": "improvement_needed", "count": 4 },
      { "name": "Core Web Vitals - Desktop", "status": "pass", "value": "Good" },
      { "name": "Core Web Vitals - Mobile", "status": "improvement_needed", "value": "Needs Improvement" },
      { "name": "HTTPS", "status": "pass", "value": "All secure" },
      { "name": "Robots.txt & Sitemap", "status": "pass", "value": "Valid" },
      { "name": "AI Crawlability", "status": "fail", "value": "GPTBot blocked" },
      { "name": "301 Redirect pages", "status": "improvement_needed", "count": 15 },
      { "name": "404 Error pages", "status": "fail", "count": 7 },
      { "name": "Attorney/Person schema", "status": "fail", "value": "Missing" },
      { "name": "FAQ schema", "status": "fail", "value": "Missing" },
      { "name": "Organization schema", "status": "improvement_needed", "value": "Incomplete" },
      { "name": "Image alt text", "status": "improvement_needed", "count": 34, "value": "34 missing" }
    ]
  }
}
```

### Analysis Recap
```json
{
  "id": "analysis_recap",
  "status": "completed",
  "data": {
    "rows": [
      {
        "category": "Website Performance",
        "status": "improvement_needed",
        "summary": "Traffic down 35% from March 2025 peak. DR 45 is competitive but traffic value lags market leader by $20K/mo.",
        "metrics": ["DR 45", "15K visits/mo", "-35% from peak"]
      },
      {
        "category": "GBP & Local Performance",
        "status": "failing",
        "summary": "SoLV below 20% in all markets. Review count (127) is 2.5x behind top competitor (312).",
        "metrics": ["18% SoLV", "127 reviews", "ARP 3.2"]
      },
      {
        "category": "Technical SEO",
        "status": "improvement_needed",
        "summary": "Core issues with duplicate meta descriptions and missing schema. AI crawlers currently blocked.",
        "metrics": ["23 dup metas", "0 schemas", "GPTBot blocked"]
      },
      {
        "category": "Content Performance",
        "status": "improvement_needed",
        "summary": "71% of blog content generates zero traffic. Missing key practice area pages vs. competitors.",
        "metrics": ["71% zero-traffic", "3 missing PAs", "850 avg words"]
      },
      {
        "category": "Backlinks & Citations",
        "status": "passing",
        "summary": "Clean backlink profile with only 8% spam. Citation coverage at 50% - 7 key directories missing.",
        "metrics": ["350 RDs", "8% spam", "7 missing dirs"]
      }
    ],
    "bottom_line": "Strong foundation with clean backlinks and good DR, but traffic decline, weak local visibility, and technical gaps are leaving significant revenue on the table."
  }
}
```

### Section Cover: Planning
```json
{
  "id": "section_cover_planning",
  "status": "completed",
  "data": {
    "title": "Plan of Attack",
    "description": "12-month roadmap to recover traffic, dominate local, and capture AI visibility"
  }
}
```

### Traffic Projection
```json
{
  "id": "traffic_projection",
  "status": "completed",
  "data": {
    "current_traffic": 15000,
    "peak_traffic": 23000,
    "peak_date": "March 2025",
    "current_trajectory": [
      { "month": 0, "traffic": 15000 },
      { "month": 6, "traffic": 12500 },
      { "month": 12, "traffic": 10000 }
    ],
    "target_trajectory": [
      { "month": 0, "traffic": 15000 },
      { "month": 6, "traffic": 21000 },
      { "month": 12, "traffic": 28000 }
    ],
    "monthly_growth_rate": 0.07,
    "disclaimer": "Projections are directional estimates based on historical data and planned work output — not a guarantee."
  }
}
```

### Action Plan
```json
{
  "id": "action_plan",
  "status": "completed",
  "data": {
    "phases": [
      {
        "title": "Technical Foundation",
        "period": "Month 1-2",
        "tasks": [
          "Fix 23 duplicate meta descriptions",
          "Implement Attorney, FAQ, and Organization schema",
          "Unblock AI crawlers in robots.txt",
          "Resolve 7 broken pages (404s)",
          "Optimize Core Web Vitals for mobile",
          "Complete 7 missing directory citations"
        ]
      },
      {
        "title": "Content & Local",
        "period": "Month 3-4",
        "tasks": [
          "Build out 3 missing practice area pages",
          "Expand top 5 pages to competitive word count",
          "Add FAQ sections to all practice area pages",
          "Launch GBP review generation campaign",
          "Create unique content for 8 thin location pages",
          "Internal linking audit and optimization"
        ]
      },
      {
        "title": "Authority & AI",
        "period": "Month 5-6",
        "tasks": [
          "Targeted link building campaign (10 links/mo)",
          "AI citation optimization and monitoring",
          "Guest posting on legal publications",
          "Local PR and news coverage outreach",
          "Ongoing content refresh program",
          "Performance reporting and strategy adjustment"
        ]
      }
    ]
  }
}
```

### Case Studies
```json
{
  "id": "case_study_0",
  "status": "completed",
  "data": {
    "client_name": "Sacramento Injury Law",
    "anonymized": false,
    "practice_area": "Personal Injury",
    "market": "Sacramento, CA",
    "engagement_start": "January 2025",
    "traffic_start": 8500,
    "traffic_end": 24000,
    "growth_percent": 182,
    "traffic_history": [
      { "date": "Jan 2025", "traffic": 8500 },
      { "date": "Apr 2025", "traffic": 12000 },
      { "date": "Jul 2025", "traffic": 18000 },
      { "date": "Oct 2025", "traffic": 24000 }
    ],
    "key_wins": [
      "Recovered from algorithm penalty in 3 months",
      "Local Pack visibility improved from 12% to 58% SoLV",
      "Added to ChatGPT recommendations for 4 core queries"
    ]
  }
}
```

### Social Proof: Client Logos
```json
{
  "id": "social_proof_logos",
  "status": "completed",
  "data": {
    "logos": [
      { "name": "Smith & Associates", "logo_path": "assets/logos/smith.png" },
      { "name": "Johnson Law Group", "logo_path": "assets/logos/johnson.png" },
      { "name": "Pacific Legal", "logo_path": "assets/logos/pacific.png" }
    ]
  }
}
```

### The Team
```json
{
  "id": "the_team",
  "status": "completed",
  "data": {
    "differentiators": [
      { "title": "50+ Years Combined SEO Experience", "description": "Deep expertise across technical, content, and local SEO" },
      { "title": "Over-Communicators by Design", "description": "Bi-weekly calls, Slack access, monthly reports" },
      { "title": "Full-Stack In-House Execution", "description": "No outsourcing - your team works directly on your account" },
      { "title": "Transparent Reporting", "description": "Real-time dashboard access and honest performance updates" }
    ],
    "team_members": [
      { "role": "Account Strategist", "initials": "JS", "contribution": "Overall strategy and client communication" },
      { "role": "Technical SEO Specialist", "initials": "MK", "contribution": "Site audits, schema, and technical fixes" },
      { "role": "Content Writer", "initials": "AL", "contribution": "Practice area pages and blog content" },
      { "role": "Link Builder", "initials": "TR", "contribution": "Outreach and authority building" },
      { "role": "Local SEO Specialist", "initials": "CP", "contribution": "GBP optimization and citations" }
    ]
  }
}
```

### Next Steps
```json
{
  "id": "next_steps",
  "status": "completed",
  "data": {
    "cta_text": "Schedule Your Strategy Call",
    "calendar_link": "https://calendly.com/agency/strategy-call",
    "contact_email": "hello@agency.com",
    "contact_phone": "(555) 123-4567",
    "expiry_date": "May 24, 2026",
    "expiry_days": 30
  }
}
```

---

## Common Errors

| Error | Cause | Fix |
|-------|-------|-----|
| Traffic value shows millions | org_cost in cents | Parser auto-divides by 100 |
| CSV parse fails | UTF-16 encoding | Tool handles automatically |
| `{{placeholder}}` visible in output | Slide data missing | Check `proposal_update_state` data |
| Chart not rendering | Missing traffic_history array | Ensure array format is correct |
| SoLV% is 0 | Business name mismatch | Check target_business parameter |

---

*Agency OS v1.2 - Part of the Blueprint Training One-Person Agency program*
