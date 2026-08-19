---
name: bpt-workspace-setup
description: Interactive onboarding for new Agency OS users. Sets up agency profile, adds owner, and shows the dashboard.
---

# Workspace Setup

Welcome new users to Agency OS with an interactive setup conversation.

## When to Use

- First time using Agency OS after installation
- When `agency.json` is empty
- User asks to set up their agency

## Prerequisites

- Agency OS MCP server connected
- Workspace initialized (data files exist)

## Conversation Flow

This is an **interactive conversation**, not a checklist. Guide the user naturally through each step, asking questions and confirming before moving on.

### Step 1: Welcome

Start with a warm welcome:

> "Welcome to Agency OS! I'll help you set up your agency in just a few minutes.
>
> First, let me check that everything is connected..."

Call `agency_get` to verify the MCP connection works. If it fails, tell them to check their MCP server configuration.

### Step 2: Agency Profile

Ask for their agency information conversationally:

> "What's your agency name?"

After they respond:

> "Great! What's the best email for [agency name]? And do you have a website?"

Then ask about services:

> "What services do you offer? For example: SEO, Content Marketing, Meta Ads, Web Development..."

Use `agency_update` to save:
- name
- email
- website (if provided)
- services (as an array)

Confirm what was saved:

> "Perfect! I've set up [Agency Name]. You can always update this later."

### Step 3: Add Owner

Add them as the first team member:

> "Now let's add you as the owner. What's your name?"

After name:

> "And your email? (This is just for the CRM, not for login - Agency OS is local-first)"

Use `team_create` with:
- name: their name
- email: their email
- role: "owner"
- active: true

Confirm:

> "Added you as the owner of [Agency Name]."

### Step 4: Google Integration Setup (Optional)

Ask if they want to connect Google Drive and Gmail for client onboarding automation:

> "Do you want to set up Google Drive integration? This allows automatic folder creation and email drafts when onboarding new clients."

If yes, first check if Google MCP tools are available. If not:

> "Before we configure this, you'll need to enable Google integrations:
>
> **Claude Desktop:** Go to Settings → Integrations and enable Google Drive and Gmail
>
> **Claude Code:** Add the Google Drive and Gmail MCP servers to your `.mcp.json` config
>
> Once that's done, let me know and we'll continue."

Once Google tools are available (or if they already were):

> "I'll need a few things from your Google Drive:
>
> 1. **Client Work Parent Folder ID** - Go to your client folders location in Google Drive, the folder ID is in the URL after `/folders/`
>
> 2. **Onboarding Questionnaire Template** (optional) - If you have a Google Doc template for client questionnaires, paste the Doc ID
>
> 3. **Access Checklist Template** (optional) - If you have a Google Sheet checklist template, paste the Sheet ID"

After they provide the folder ID:

> "And what's your Calendly or scheduling link for kickoff calls? (e.g., https://calendly.com/your-agency/kickoff)"

Use `agency_update` to save:
- `google_config.client_work_folder_id` - The Drive folder ID
- `google_config.onboarding_questionnaire_id` - Optional questionnaire template ID
- `google_config.access_checklist_id` - Optional checklist template ID
- `calendly_link` - Scheduling link

Confirm what was saved:

> "Google integration configured! When you use `/bpt-client-onboarding`, I'll automatically:
> - Create a client folder in your Drive
> - Copy your templates
> - Draft an onboarding email in Gmail"

If they skip Google setup:

> "No problem! You can set this up later by running `/bpt-workspace-setup` again or by updating your agency profile."

### Step 5: Import from Existing Deck (Optional)

If they have a sales deck or pitch presentation, offer to import agency data from it:

> "Do you have an existing sales deck or pitch presentation? I can import your pricing, team info, process, and case studies automatically."

If yes, ask for the file or link:

> "Great! Share the file path (for a PDF) or a link (Canva, Google Slides, or website)."

**To import from a deck:**

1. **Read the content:**
   - For PDF: Use the `Read` tool with the file path
   - For URLs: Use `WebFetch` to retrieve the content

2. **Extract structured data:**
   - Pricing tiers and packages
   - Team members (names, titles, bios)
   - Implementation process/phases
   - Case studies and results
   - Testimonials
   - Agency differentiators

3. **Present for confirmation:**
   > "Here's what I found in your deck:
   >
   > **Pricing:** 3 tiers (Starter $2,500, Growth $4,500, Scale $7,500)
   > **Team:** 4 members (Jane Smith - CEO, John Doe - SEO Director, ...)
   > **Process:** 4 phases (Foundation, Content, Authority, Scale)
   > **Case Studies:** 2 (Client A - 150% traffic increase, ...)
   >
   > Does this look right? I can adjust anything before saving."

4. **Save extracted data:**
   - Use `agency_update` for pricing, process, case studies, testimonials, differentiators
   - Use `team_create` for each team member
   - Update `proposal_team_members` with created team IDs

If they don't have a deck:

> "No problem! You can set these up later when you're ready to create your first proposal. Just run the proposal generator skill and it'll guide you through it."

### Step 6: Show the Dashboard

Tell them about the Web UI:

> "**Your dashboard is ready at http://localhost:3000**
>
> You can use it to:
> - View and manage your pipeline
> - Track clients and projects
> - Edit data with a visual interface
>
> The dashboard runs automatically whenever the MCP server is connected."

### Step 7: Import Existing Data (Optional)

Ask if they have existing data:

> "Do you have existing leads or clients you'd like to import?"

If yes, explain their options:
- **Manual entry**: "Just tell me about them and I'll add them"
- **Bulk import**: "You can edit the JSON files directly in `data/leads.json` and `data/clients.json`"

If they want to add a few manually, help them:

> "Tell me about your first lead - company name, contact person, and their email."

Use `leads_create` for each one.

### Step 8: Summary & Next Steps

Wrap up with a summary:

> "You're all set! Here's what we created:
>
> **Agency:** [Name] - [Website]
> **Owner:** [Their Name]
> **Dashboard:** http://localhost:3000
>
> **What you can do now:**
> - Create leads: *'Create a lead for [company], contact [name] at [email]'*
> - Create clients: *'Create a client for [company] with [service] service'*
> - Check pipeline: *'Show my pipeline summary'*
> - Generate a proposal: */bpt-proposal-generator*
> - Run diagnostics: */bpt-doctor*
>
> What would you like to do first?"

## Error Handling

### MCP Not Connected
If `agency_get` fails:
> "I can't connect to the Agency OS server. Make sure the MCP server is configured correctly. Check Settings → MCP Servers in Claude Desktop."

### Empty Responses
If user gives minimal info, that's okay - use what they provide:
> "I'll leave that blank for now. You can always update it later with 'Update my agency profile'."

## Output

After successful setup:
- Agency profile configured
- Owner added to team
- User knows about dashboard
- User knows basic commands
- Ready to start using Agency OS
