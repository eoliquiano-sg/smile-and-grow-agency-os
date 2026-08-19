---
name: bpt-client-onboarding
description: Full client onboarding with Windsor access capture, Google Drive folder creation, onboarding email draft, and project/sprint/deliverables.
---

# Client Onboarding

Complete client onboarding workflow: creates the client record, captures platform access from Windsor, creates the Google Drive folder, drafts the onboarding email, and sets up the project/sprint/deliverables.

## When to Use

- Immediately after lead status changes to `closed_won`
- When starting work with a new client
- After a signed proposal/contract

## Prerequisites

- Lead record with `closed_won` status (or client info from user)
- **Google Integration (optional but recommended):**
  - **Claude Desktop:** Enable Google Drive and Gmail in Settings → Integrations
  - **Claude Code:** Add the Google Drive and Gmail MCP servers to your project's `.mcp.json` or global config

  Without Google integration, the skill will still create the local client record, capture Windsor access, and set up the project/sprint/deliverables - just without Drive folders or email drafts.

## Workflow

This is an **interactive workflow** with 9 steps. Guide the user through each step, confirming progress.

### Step 1: Get Client Info

**From lead:**
```
leads_get { "id": "{lead-uuid}" }
```

**Or ask user for:**
- Company name
- Contact name
- Email
- Website

### Step 2: Check & Configure Google Integration

Get agency profile and check for required config:

```
agency_get {}
```

**If `google_config.client_work_folder_id` is missing:**

> "I notice Google Drive isn't configured yet. To create a Drive folder for this client, I need your parent folder ID.
>
> Go to your client folders location in Google Drive - the folder ID is in the URL after `/folders/`
>
> Paste the folder ID, or type 'skip' to continue without Google Drive:"

If they provide a folder ID, attempt to save it:
```
agency_update { "google_config": { "client_work_folder_id": "{folder_id}" } }
```

**Confirm the scheduling link before it goes into any client email (REQUIRED checkpoint).**

The kickoff link in the email must be the link the client should actually book on. Resolve it in this order: **owner's `calendar_link` first, then `agency.calendar_link`.** Never silently use whatever is on file — the agency link is often a shared/legacy link that doesn't match the person signing the email.

Always confirm with the user before drafting:

> "The kickoff email will use this scheduling link: {resolved_calendar_link}.
>
> Is that the right calendar for this client's kickoff, or do you want to use a different link?"

If they give a different link, use it for this onboarding. If the owner profile has no `calendar_link` yet and they give you theirs, also save it for next time:
```
team_update { "id": "{owner-id}", "calendar_link": "{link}" }
```

**If `google_config.access_checklist_id` is missing**, default the email's access link to the standard access-instructions doc:
`https://docs.google.com/document/d/1z31ipKIVDJ_idybNzmroMV5Uz_CEDxHsq62X4G9dgaQ/edit`
(Override with a per-agency doc if the user has one.)

**If config exists, confirm:**

> "I'll use your existing settings:
> - Drive folder: [folder_id]
> - Scheduling link: [resolved per owner-first rule above]
>
> Continue with these, or would you like to update them?"

### Step 3: Create Local Client Record

Use the `clients_create` MCP tool:

```json
{
  "lead_id": "{lead-uuid}",
  "company_name": "Acme Corp",
  "contact_name": "John Smith",
  "email": "john@acme.com",
  "website": "https://acme.com",
  "service_type": "seo_sprint",
  "monthly_retainer": 4500,
  "contract_start_date": "2024-04-01"
}
```

This will:
- Create the client with `onboarding` status
- Set `onboarded_at` timestamp
- Link to the original lead
- Create local client folder in `clients/{client-slug}/`

### Step 4: Capture Platform Access from Windsor (DEFAULT — do not skip)

**The downstream WQA halts at pre-flight unless the client record carries the analytics identifiers. Capture them now — and check Windsor, do NOT assume the record already has them.** A freshly created client record will have none of this; Windsor almost always does.

1. List connected accounts:
   ```
   windsor_list_accounts {}
   ```
2. Match this client by **name and/or domain** against the returned accounts. For example, a `googleanalytics4__Cutter Law - GA4` account → GA4 property `309447460`; a `searchconsole__https://cutterlaw.com/` account → that GSC property; any `google_my_business__... <Company>` entries → the client's GMB location(s), which may be multiple.
3. Write what you found onto the client record:
   ```
   clients_update {
     "id": "{client-uuid}",
     "ga4_property_id": "{ga4_property_number}",
     "gsc_property": "{gsc_url_or_sc-domain}",
     "custom_fields": {
       "vertical": "{local_service | saas_education | ...}",
       "ahrefs_target": "{client website, e.g. https://acme.com/}",
       "windsor_accounts": {
         "ga4": "googleanalytics4__{id}",
         "gsc": "searchconsole__{property}",
         "gmb": "google_my_business__locations/{primary}"
       },
       "gmb_location_ids": ["locations/{...}", "locations/{...}"]
     }
   }
   ```
   (Merge with any existing `custom_fields` — `clients_update` replaces the whole object, so include fields already present.)
4. **If a platform isn't wired in Windsor, prompt the user with exactly what to connect and where it lands**, e.g.:
   > "I don't see {GA4 / GSC / GMB} for {Company} in Windsor. Connect it in Windsor (it'll show up as `{datasource}__{id}`), then tell me and I'll write it to the client record's `windsor_accounts`. Competitors and `vertical` aren't auto-discoverable — want me to research 5 competitors, or will you provide them?"

Only flag something as missing **after** checking Windsor.

### Step 5: Create Google Drive Folder Structure

**Skip this step if user chose to skip Google Drive in Step 2.**

Use Claude's native Google Drive MCP tool:

**Create client folder:**
```
mcp__claude_ai_Google_Drive__create_file
- name: "{Company Name}"
- mimeType: "application/vnd.google-apps.folder"
- parent: "{client_work_folder_id}"
```

Capture the returned folder ID.

**Create Client Assets subfolder:**
```
mcp__claude_ai_Google_Drive__create_file
- name: "Client Assets"
- mimeType: "application/vnd.google-apps.folder"
- parent: "{new_client_folder_id}"
```

**Copy templates (if configured):**

If `google_config.onboarding_questionnaire_id` exists:
```
mcp__claude_ai_Google_Drive__copy_file
- fileId: "{onboarding_questionnaire_id}"
- name: "{Company Name} - Onboarding Questionnaire"
- parent: "{new_client_folder_id}"
```

If `google_config.access_checklist_id` exists:

**First, validate the template has been customized:**
```
mcp__claude_ai_Google_Drive__read_file_content
- fileId: "{access_checklist_id}"
```

Check if the content still contains `[ENTER EMAIL]`:

If placeholder still exists, STOP and warn:
> "Your Access Checklist template still has the placeholder `[ENTER EMAIL]` in it.
>
> Please open the template and replace it with your agency email before we send this to a client: [template_link]
>
> Let me know when you've updated it."

Wait for confirmation, then re-validate.

If template is customized (no placeholder), copy it:
```
mcp__claude_ai_Google_Drive__copy_file
- fileId: "{access_checklist_id}"
- name: "{Company Name} - Access Checklist"
- parent: "{new_client_folder_id}"
```

Confirm to user:

> "Created Google Drive folder for {Company Name}:
> - Client folder: [link]
> - Assets subfolder: [link]
> - Onboarding Questionnaire: [link] (if copied)
> - Access Checklist: [link] (if copied)
>
> **Action needed:** Please share the client folder with {client_email}:
> 1. Click the folder link above
> 2. Click 'Share' → Add {client_email} as Editor
>
> This lets the client access their folder and upload assets."

### Step 6: Update Client Record with Drive Folder

**Skip if no Drive folder was created.**

Update the client with Drive folder URLs (merge with the `custom_fields` written in Step 4 — include them so they aren't overwritten):

```
clients_update {
  "id": "{client-uuid}",
  "drive_folder": "https://drive.google.com/drive/folders/{folder_id}",
  "custom_fields": {
    "assets_folder": "https://drive.google.com/drive/folders/{assets_folder_id}",
    "access_checklist_doc": "https://docs.google.com/document/d/{checklist_doc_id}/edit"
  }
}
```

### Step 7: Generate Onboarding Email Draft

Read the email template:
```
Read templates/emails/onboarding-email-template.md
```

Get agency profile for merge fields:
```
agency_get {}
```

Get owner info:
```
team_list { "role": "owner" }
```

**Resolve branding colors (with fallback):**

If `agency.branding` is missing or incomplete, use defaults:

- `primary_color` → `agency.branding.primary_color` OR `#2563eb`
- `secondary_color` → `agency.branding.secondary_color` OR `#1e40af`

Do not throw or block on missing branding — fall back silently.

**Fill in merge fields:**

- `{{agency.name}}` → Agency name
- `{{agency.email}}` → Agency email
- `{{agency.website}}` → Agency website URL
- `{{client.company_name}}` → Client company
- `{{client.contact_name}}` → Contact first name
- `{{owner.name}}` → Owner's name
- `{{owner.title}}` → Owner's title (e.g., "Managing Partner")
- `{{drive_folder_link}}` → Link to client folder (or remove section if skipped)
- `{{assets_folder_link}}` → Link to assets subfolder (or remove if skipped)
- `{{access_checklist_link}}` → Access-instructions doc. Use `google_config.access_checklist_id` if configured, else the standard doc from Step 2.
- `{{scheduling_link}}` → **the link confirmed in Step 2 (owner's `calendar_link` first, then `agency.calendar_link`)** — never blindly use `agency.calendar_link`.
- `{{primary_color}}` → Resolved per branding fallback above
- `{{secondary_color}}` → Resolved per branding fallback above

**Formatting requirements (do not deviate):**

- All body text MUST render at a uniform 16px font size.
- No h1/h2 visual hierarchy. Section headers are bolded inline only — do not increase their font size.
- No "Welcome to {{agency.name}}!" salutation. Open with `Hi {{client.contact_name}},` then dive into the body.
- Opening line MUST read exactly: "We're excited to kick off your campaign." (Do NOT substitute service-specific phrasing like "SEO Sprint engagement".)
- Use inline links with `{{primary_color}}` — no CTA buttons with background fills.

**Before creating a new draft, check for an existing one.** There is no Gmail update/delete-draft tool, so re-running this step or revising the email **stacks duplicate drafts**. Run `list_drafts { query: "subject:Let's Get Started" }` first; if a draft to this client already exists, tell the user it's there and that any revision will create a second draft they'll need to delete manually.

**Create Gmail draft (HTML formatted):**

Use Claude's native Gmail MCP tool with `htmlBody`:

```
mcp__claude_ai_Gmail__create_draft
- to: ["{client_email}"]
- subject: "{Agency Name} — Let's Get Started!"
- htmlBody: "{styled_html_email}"
```

Confirm to user:

> "Created email draft in Gmail. Please review before sending:
> - To: {client_email}
> - Subject: {Agency Name} — Let's Get Started!
>
> The draft includes:
> - Drive folder link (if configured)
> - Access-instructions doc
> - Scheduling link for kickoff call (confirmed in Step 2)"

### Step 8: Create Project + Onboarding Sprint

**Create project.** The engagement runs **12 months** — set `target_end_date` to `start_date + 12 months`. (There is no `projects_update` tool, so the dates cannot be edited after creation — set them correctly now.)

```json
{
  "client_id": "{client-uuid}",
  "name": "{Client} — {Service} Campaign",
  "project_type": "seo_sprint",
  "primary_goal": "Increase organic traffic and local visibility",
  "start_date": "2024-04-01",
  "target_end_date": "2025-04-01"
}
```

**Create onboarding sprint (3 days):**

```json
{
  "project_id": "{project-uuid}",
  "sprint_number": 1,
  "sprint_type": "onboarding",
  "scheduled_start": "2024-04-01",
  "scheduled_end": "2024-04-03",
  "status": "active"
}
```

### Step 9: Create Onboarding Deliverables (then refresh the dashboard)

Create 3 deliverables for the onboarding sprint:

**1. Access Collection (Day 1):**
```json
{
  "sprint_id": "{sprint-uuid}",
  "name": "Access Collection",
  "description": "Collect GA4, GSC, CMS, and Google Business Profile access from client",
  "deliverable_type": "setup",
  "due_date": "{start_date + 1 day}"
}
```

**2. Kickoff Call (Day 2):**
```json
{
  "sprint_id": "{sprint-uuid}",
  "name": "Kickoff Strategy Call",
  "description": "Initial strategy discussion - review goals, timeline, and priorities",
  "deliverable_type": "meeting",
  "due_date": "{start_date + 2 days}"
}
```

**3. Project Timeline Document (Day 3):**
```json
{
  "sprint_id": "{sprint-uuid}",
  "name": "Project Timeline Document",
  "description": "Create project timeline with sprint breakdown and key milestones",
  "deliverable_type": "document",
  "due_date": "{start_date + 3 days}"
}
```

**Then regenerate the agency dashboard** so the new client appears on it immediately (the canonical dashboard `{AGENCY_ROOT}/agency-dashboard.html` is a snapshot):

```bash
python3 .claude/skills/productization/project-plan/scripts/build_agency_dashboard.py \
  --workspace-root {AGENCY_ROOT} \
  --output {AGENCY_ROOT}/agency-dashboard.html
```

(The dashboard is refreshed again — with the full plan + analytics — at the end of `/bpt-project-plan` once the WQA is done.)

## Summary Output

After completing all steps, summarize:

> "Client onboarding complete for {Company Name}!
>
> **Google Drive:** (if configured)
> - Client folder: [link]
> - Assets folder: [link]
> - Questionnaire: [link]
>
> **Platform access (from Windsor):**
> - GA4: [property] · GSC: [property] · GMB: [location(s)]
> - (Anything not wired is flagged above for you to connect.)
>
> **Email:**
> - Draft ready in Gmail - review and send
>
> **Project:**
> - {Project Name} created (12-month engagement)
> - Onboarding sprint active ({start_date} - {end_date})
> - 3 deliverables scheduled
>
> **Here's what comes next:**
> 1. The next step is the **Website Quality Audit (WQA)** — a comprehensive website audit we'll use to build their **12-month project plan**.
> 2. To run the WQA, we need the client to grant access to:
>    - Google Analytics 4
>    - Google Search Console
>    - The CMS
>    - Google Business Profile
> 3. The WQA also needs a **Screaming Frog crawl** of the site (CSV export dropped in `clients/{slug}/crawls/`).
>
> Review and send the onboarding email, then confirm with me once access is granted. You can leave this thread open and come back whenever — hours, days, or weeks — or start a new thread and say \"run the WQA for {Company}\" and I'll kick it off."

## MCP Tools Used

| Tool | Purpose |
|------|---------|
| `leads_get` | Retrieve lead information |
| `agency_get` | Get agency profile and Google config |
| `agency_update` | Save Google config (google_config parameter) |
| `team_list` | Get owner info for email |
| `team_update` | Save owner's calendar link (if newly provided) |
| `clients_create` | Create client record |
| `windsor_list_accounts` | Find the client's GA4/GSC/GMB account IDs to capture access |
| `clients_update` | Write platform access + Drive folder URLs to the client |
| `projects_create` | Create first project (set 12-month target_end_date — no projects_update exists) |
| `sprints_create` | Create onboarding sprint |
| `deliverables_create` | Create deliverables |
| `mcp__claude_ai_Google_Drive__create_file` | Create Drive folders |
| `mcp__claude_ai_Google_Drive__copy_file` | Copy template documents |
| `mcp__claude_ai_Google_Drive__read_file_content` | Validate template is customized |
| `mcp__claude_ai_Gmail__list_drafts` | Check for an existing draft before creating a new one |
| `mcp__claude_ai_Gmail__create_draft` | Create HTML email draft |

## Error Handling

### Google MCP Tools Not Available
If Google Drive or Gmail MCP tools aren't connected:
> "I can't access Google Drive/Gmail. To enable this:
>
> **Claude Desktop:** Go to Settings → Integrations and enable Google Drive and Gmail
>
> **Claude Code:** Add the Google Drive and Gmail MCP servers to your `.mcp.json` config
>
> I can still create the local client record, capture Windsor access, and set up the project without Google integration. Want to continue without Drive/Gmail, or set those up first?"

### Template Not Found
If `templates/emails/onboarding-email-template.md` is missing (e.g. the packaged plugin dropped it), fall back to composing the email inline using the same merge fields and formatting requirements specified in Step 7. The template ships in this skill's `templates/emails/` folder — confirm the bundler includes it.

### Manual Step Required: Share Folder with Client
The Google Drive MCP cannot share folders (no set_permissions tool). After creating the folder:

> "**Manual step:** Please share the client folder with {client_email}:
> 1. Open the folder: [link]
> 2. Click 'Share' button
> 3. Add {client_email} as Editor
>
> This gives the client access to upload assets and view documents."

### Duplicate Email Drafts
There is no Gmail update/delete-draft tool. Every revision creates a new draft. Always `list_drafts` before creating, and tell the user when prior drafts exist so they can delete the stale ones.

## Decision Points

**Lead already has client record:**
- Check `data/clients.json` for existing client linked to lead
- If exists, offer to update rather than create new

**Different service type:**
- Adjust project type and sprint templates based on service
- SEO Sprint → onboarding, foundational, content, link, reporting
- Meta Ads → onboarding, account_setup, audience_building, creative_production, campaign_launch

**Client provides access during call:**
- Mark Access Collection deliverable as complete

**Windsor access not found:**
- Don't assume it's missing until you've run `windsor_list_accounts` and matched by name/domain.
- If genuinely not connected, tell the user exactly which platform to connect and that it lands in `custom_fields.windsor_accounts` once available.
