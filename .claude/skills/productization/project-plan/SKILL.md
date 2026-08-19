---
name: bpt-project-plan
description: Create project plans from templates or WQA findings, generating sprints and deliverables for a client.
---

# Project Plan Builder

Create project plans from templates or WQA (Website Quality Audit) findings, generating sprints and deliverables for a client project. Optionally export to CSV/XLSX for ClickUp import.

## When to Use

- After completing `/bpt-website-quality-audit` - creates sprints based on identified issues
- Setting up a new client project after onboarding
- Applying a standard service template to a specific client
- Creating a structured project with sprints and deliverables
- Exporting tasks to external PM tools (ClickUp, Asana, etc.)

## Prerequisites

- Existing client record in `data/clients.json`
- Existing project record in `data/projects.json`
- Either:
  - Completed WQA audit for the client, OR
  - Project plan template in `templates/project-plans/`

## Templates Available

Read templates from `templates/project-plans/`:

| Template | File | Service Type |
|----------|------|--------------|
| SEO Sprint | `seo-sprint.json` | Full SEO engagement |
| Meta Ads | `meta-ads.json` | Paid advertising |

## Two kinds of "project plan"

Keep these distinct:

- **`data/projects.json`** holds the high-level **project shell** (name, type,
  dates, goal) — one record per engagement.
- The **detailed plan** is the set of **sprints + deliverables** attached to that
  project. That's what this skill generates and what the web UI's Projects view
  renders. "Project plan" in this skill means the detailed plan.

## Workflow

### Step 0: Check for WQA Results

```
wqa_list_audits { "client_id": "{client-uuid}" }
```

- **Completed audit exists → WQA-Driven Workflow** (below). This is the primary
  path: it turns the approved recommendations into a full 12-month plan.
- **No audit → Template-Based Workflow** (further down) for standard engagements.

---

## WQA-Driven Workflow

Generates a detailed 12-month plan from the WQA approvals: 6 sprints (Kickoff /
Technical / Local SEO / Content / Links / Reporting), with technical fixes grouped
by action type, content batched 6-10 pages/month by priority, monthly link slots
distributed across target pages, recurring monthly reports, and team-routed
assignees. This is the **same mechanism** `/bpt-website-quality-audit` runs at its
Checkpoint 3 — one code path, idempotent, so the plan is never created twice.

### Step 1: Locate the audit

From `wqa_list_audits`, get the `audit_id` and the client slug. The approvals file
is at `clients/{slug}/wqa/audits/{audit_id}/{slug}-approvals.json` (produced by
the WQA's `parse_approvals.py`). If it's missing, the WQA isn't far enough along —
finish `/bpt-website-quality-audit` first.

### Step 2: Generate the plan JSON

Shell out to the planner (ships with this skill). It reads `data/team.json` and
round-robins assignees by skill, falling back to the owner / a single assignee for
solo agencies. Run from the workspace root (so the data/ + clients/ paths resolve):

```bash
python3 .claude/skills/productization/project-plan/scripts/build_project_plan.py \
  --audit-dir clients/{slug}/wqa/audits/{audit_id} \
  --client-slug {slug} \
  --client-id {client-uuid} \
  --team-json data/team.json \
  --vertical {client.custom_fields.vertical or "local_service"} \
  --start-date {YYYY-MM-DD}
```

**`--vertical`** drives Sprint 3 Local SEO: pass `local_service` to include it;
any other value (`saas_education`, `ecommerce`, `b2b`, `legal`, `medical`,
`home_services`, …) suppresses Sprint 3 and shifts content production up to Month 2.
Read it from `clients_get → custom_fields.vertical` (default `local_service`).

Optional flags: `--engagement-months` (default 12), `--batch-size` (content
pages/month, default 8), `--links-per-month` (default 6).

It writes `{slug}-project-plan.json` into the audit dir and prints a summary
(by sprint / by month / by assignee). The base plan is 6 sprints: Kickoff (2 items:
WQA + Project Plan), Technical, Local SEO (local only), Content, Links, and Reporting
(Analytics Audit M1 + monthly Client Check-ins M2-M12 + WQA Refreshes at M6/M12).

### Step 3: Review with the user (Checkpoint 2.5)

Present the plan **as a month-by-month markdown table in chat** — group deliverables
by `scheduled_month`, showing name / sprint / owner / due. Let the user adjust
cadence, add/remove/reject items, reassign, or change vertical / start date / batch
size / links velocity, then re-run Step 2. **Wait for an explicit "looks good"
before importing.**

### Step 4: Import into Agency OS

Load the whole plan in one call. `replace_existing: true` makes regeneration
idempotent — it clears the project's prior sprints/deliverables first, so
re-running never duplicates:

```
project_plan_import {
  client_id: "{client-uuid}",
  replace_existing: true,
  plan: <contents of {slug}-project-plan.json>
}
```

The tool creates the project (or reuses the same-named one), all sprints, and all
deliverables — resolving each `assigned_to_email` to a team member. It returns a
summary (created counts, by_sprint, by_assignee).

### Step 5: Regenerate the agency dashboard (REQUIRED — do not skip)

**The canonical deliverable is `{AGENCY_ROOT}/agency-dashboard.html`** (the "WEBRIS — Dashboard"). It is a generated snapshot, so the newly-planned client will NOT appear until you rebuild it. As soon as the plan is imported, regenerate the dashboard so the client record, its 12-month project plan, and its analytics tracking all show up:

```bash
python3 .claude/skills/productization/project-plan/scripts/build_agency_dashboard.py \
  --workspace-root {AGENCY_ROOT} \
  --output {AGENCY_ROOT}/agency-dashboard.html
```

Then confirm the client now appears in the dashboard (grep the output for the client name). If `data/agency.json → publishing.target` is not `local`, also run `publish_dashboard.py` to ship it to the configured target.

### Step 6: Point the user to the plan

> "{Client}'s 12-month project plan is built and live on the agency dashboard.
>
> - {N} deliverables across 6 sprints (Kickoff, Technical, Local SEO, Content, Links, Reporting), {start} → {end}.
> - `agency-dashboard.html` now shows {Client} with the full plan + analytics tracking.
>
> **Want to adjust anything before we move on?** I can reprioritize deliverables or move
> them between months, change sprint dates/cadence, reassign owners/rebalance workload,
> or add/remove deliverables. Tell me what to change and I'll update the plan and refresh
> the dashboard.
>
> **When the plan looks right, the next step is the Local SEO audit** — GBP health,
> citations/NAP, reviews, and map-grid rank tracking across {Client}'s service areas
> (this fills in Sprint 3 with real findings). Say \"run the Local SEO audit for {Client}\"
> and I'll kick it off."

**Handling "adjust the plan":** apply the change, then re-sync both the data and the dashboard:
- Small edits (reprioritize, move month, reassign, add/remove a few) → `deliverables_update` / `sprints_update` / `deliverables_create` directly.
- Larger re-scopes (different batch size, engagement length, links/month) → re-run `build_project_plan.py` with new flags, then `project_plan_import { replace_existing: true }`.
- **Always regenerate the dashboard after any change** (`build_agency_dashboard.py`) so it stays current.

**Local-SEO hand-off applies to `local_service` clients** (those with GBP locations). For non-local verticals (SaaS, e-comm), skip the Local SEO line and close with the plan review.

### Step 7: (Optional) Export to a PM tool

If the user wants the plan in ClickUp / Asana / Monday, run the exporter against the
generated plan JSON:

```bash
python3 .claude/skills/productization/project-plan/scripts/export_project_plan.py \
  --plan clients/{slug}/wqa/audits/{audit_id}/{slug}-project-plan.json \
  --format clickup    # or: asana | monday (XLSX) | generic
```

Output lands in `exports/project-plans/`. Each format uses that tool's native column
names + status enums.

---

## Paid Media / Multi-Service Workflow

A client can carry multiple **service lines** (`clients_get → custom_fields.service_lines[]`:
SEO / PPC / LSA / Social Ads). Each service line is its own project + plan.

- **SEO** lines use the WQA-Driven Workflow above.
- **Paid lines** (ppc / lsa / social_ads) use the paid-media planner (no WQA needed):

```bash
python3 .claude/skills/productization/project-plan/scripts/build_paid_media_plan.py \
  --workspace-root . --client-slug {slug} --service-type ppc \
  --client-id {client-uuid} --team-json data/team.json --start-date {YYYY-MM-DD}
```

Then `project_plan_import` the resulting `{service_type}-project-plan.json` the same way
(it's the same plan shape; `project_type` is the service type). Repeat per service line.
When a client has `service_lines[]`, offer to generate each service's plan; the Projects
view shows one project per service.

*(Out of scope for now: paid-media performance/reporting — that's a future analytics update.)*

---

## Template-Based Workflow

Use this when no WQA exists or for standard engagements.

### Step 1: Load Context

1. Get the client and project using MCP tools:
   ```
   clients_get { "id": "{client-uuid}" }
   projects_get { "id": "{project-uuid}" }
   ```

2. Read the appropriate template:
   ```
   Read templates/project-plans/seo-sprint.json
   ```

### Step 2: Review Template with User

Present the template structure to the user:
- List of sprints with durations
- Key deliverables per sprint
- Milestones and target dates
- Total estimated hours

Ask if they want to customize before applying.

### Step 3: Calculate Dates

Based on project start date, calculate actual dates for each sprint and deliverable:

```
Sprint 1 (Onboarding): Apr 1-3
  - Access Collection: Apr 2
  - Kickoff Call: Apr 3

Sprint 2 (Foundational): Apr 4-17
  - Site Crawl: Apr 4
  - Technical Audit: Apr 6
  ...
```

### Step 4: Create Sprints

Use `sprints_create` MCP tool for each sprint in the template:

```json
{
  "project_id": "{project-uuid}",
  "sprint_number": 1,
  "sprint_type": "onboarding",
  "scheduled_start": "2024-04-01",
  "scheduled_end": "2024-04-03"
}
```

Capture the returned sprint IDs for linking deliverables.

### Step 5: Create Deliverables

Use `deliverables_create` MCP tool for each deliverable:

```json
{
  "sprint_id": "{sprint-uuid}",
  "name": "Access Collection",
  "description": "Collect GA4, GSC, CMS access from client",
  "deliverable_type": "setup",
  "estimated_hours": 1,
  "due_date": "2024-04-02"
}
```

### Step 6: Assign Team Members (Optional)

If team members are available, assign deliverables:

```
team_list {}
deliverables_update { "id": "{deliverable-uuid}", "assigned_to": "{team-member-id}" }
```

### Step 7: Activate First Sprint

Set the first sprint to active:

```
sprints_update { "id": "{sprint-uuid}", "status": "active" }
```

### Step 8: Export to CSV/XLSX (Optional)

If user wants to import into ClickUp or other PM tool:

1. Generate CSV using Claude's native document generation
2. Format for target tool (ClickUp, Asana, Monday, etc.)
3. Save to `exports/project-plans/{project-slug}-clickup.csv`

**ClickUp CSV Format:**
```csv
Task Name,Task Content,Assignee,Due Date,Priority,Status,Tags,Time Estimate,Parent Task
"Onboarding","Sprint 1 - Initial setup","","2024-04-03","Normal","to do","sprint-1",,
"Access Collection","Collect GA4, GSC, CMS access","Account Lead","2024-04-02","High","to do","setup",60,"Onboarding"
```

## Output

**Primary Output (JSON - Source of Truth):**
- `data/sprints.json` - Sprint records created via MCP tools
- `data/deliverables.json` - Deliverable records created via MCP tools

**Optional Export:**
- `exports/project-plans/{slug}-clickup.csv` - ClickUp import file
- `exports/project-plans/{slug}-plan.xlsx` - Excel workbook

## MCP Tools Used

| Tool | Purpose |
|------|---------|
| `wqa_list_audits` | Find a completed WQA (primary path) before falling back to template |
| `project_plan_import` | **WQA-driven:** bulk-import the generated plan (project + sprints + deliverables) in one idempotent call |
| `clients_get` | Get client info |
| `projects_list` | Find client's project |
| `team_list` | Get available team members |
| `sprints_create` | Create sprint records (template-based path) |
| `sprints_update` | Activate sprints (template-based path) |
| `deliverables_create` | Create deliverable records (template-based path) |
| `deliverables_update` | Assign team members (template-based path) |

## Decision Points

**Custom start date:**
→ Recalculate all dates relative to new start

**Skip certain sprints:**
→ Only create selected sprints from template
→ Adjust sprint numbers accordingly

**Solo agency (no team):**
→ Skip assignment step
→ All deliverables assigned to owner by default

**Recurring sprints (Content, Link, Reporting):**
→ Create first instance
→ Note that these repeat monthly

## Example

**Input:**
- Client: Acme Corp
- Project: SEO Sprint 2024
- Template: seo-sprint.json
- Start Date: April 1, 2024

**Output:**
```
Created 5 sprints:
1. Onboarding (Apr 1-3) - 3 deliverables
2. Foundational (Apr 4-17) - 8 deliverables
3. Content (Apr 18 - May 15) - 8 deliverables
4. Link Building (Apr 18 - May 15) - 6 deliverables
5. Reporting (May 16-22) - 4 deliverables

Total: 29 deliverables, ~85 estimated hours

First sprint activated. Agency dashboard regenerated — open `agency-dashboard.html`.
```

## Tips

- Review template with client before applying
- Adjust dates for holidays/client availability
- Content and Link sprints often run in parallel
- Add buffer between phases for unexpected work
- Use recurring flag to note monthly sprints

## Sprint 1 Flow (Planning Module)

This skill is part of the Sprint 1 Planning workflow:

1. `/bpt-client-onboarding` - Creates client, Drive folder, email draft, onboarding sprint
2. (Client provides access)
3. `/bpt-website-quality-audit` - Analyzes site health and identifies issues
4. **`/bpt-project-plan`** - Creates work sprints based on WQA findings

After this skill completes, the client has a full project plan with:
- Onboarding sprint (already created by client-setup)
- Technical sprint (if WQA found indexability/error issues)
- Content sprint (if WQA found thin/stale content)
- Links sprint (if WQA found authority gaps)
- Local sprint (if local business with GBP)
