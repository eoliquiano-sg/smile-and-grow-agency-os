---
name: bpt-doctor
description: Diagnose Agency OS workspace setup issues. Checks version tracking, data files, API configuration, and MCP connectivity.
---

# Doctor Diagnostic Skill

Comprehensive diagnostic tool for Agency OS workspaces. Identifies configuration issues and provides actionable fixes.

## When to Use

- Something isn't working as expected
- After updating Agency OS
- Before starting a WQA audit
- When MCP tools return errors
- First time using a workspace

## What It Checks

```
1. Workspace Version    → .agency-os/version.json exists, up-to-date
2. Data Files           → All JSON files exist and are valid
3. Directory Structure  → Required folders present
4. MCP Connectivity     → Tools respond correctly
5. API Configuration    → Ahrefs/Windsor keys configured (for WQA)
6. Agency Profile       → Agency name and owner configured
7. Support Bundle       → Generate a paste-able snapshot for support requests
```

## Step 1: Check Workspace Version

First, check if this workspace has version tracking:

**Look for:** `.agency-os/version.json`

If it exists, read it and check:
- `schemaVersion` - Current workspace schema version
- `installedAt` - When workspace was initialized
- `lastUpdated` - When last migration ran
- `migrationsRun` - List of migrations that have run

**Expected:** File exists with a valid `schemaVersion`.

**If missing:** This is an older workspace. The MCP server will create this file on next startup. Try restarting the MCP server.

**How to check:**
```bash
cat .agency-os/version.json
```

Or ask: "Read .agency-os/version.json"

## Step 2: Validate Data Files

Check that all required JSON files exist and contain valid JSON:

**Files to check:**
```
data/agency.json      → Should be {} or have agency profile
data/team.json        → Should be [] or have team members
data/leads.json       → Should be [] or have leads
data/clients.json     → Should be [] or have clients
data/projects.json    → Should be [] or have projects
data/sprints.json     → Should be [] or have sprints
data/deliverables.json → Should be [] or have deliverables
data/followups.json   → Should be [] or have follow-ups
```

**For each file:**
1. Check file exists
2. Read it and verify it's valid JSON
3. Check it contains expected structure (array for most, object for agency)

**Common issues:**
- Empty file (not valid JSON) → Write `[]` or `{}`
- Syntax error → Find and fix the JSON error
- Missing file → MCP server should create on startup

**How to check:**
```bash
for f in agency team leads clients projects sprints deliverables followups; do
  echo "=== $f.json ==="
  cat data/$f.json | head -5
done
```

## Step 3: Check Directory Structure

Verify required directories exist:

**Required directories:**
```
data/               → JSON data files
clients/            → Per-client folders
exports/            → Generated documents
templates/          → Document templates
.agency-os/         → Workspace metadata
```

**Optional (created when needed):**
```
clients/{slug}/crawls/    → Screaming Frog exports
clients/{slug}/exports/   → Client-specific exports
clients/{slug}/wqa/       → WQA runs and results
```

**How to check:**
```bash
ls -la data/ clients/ exports/ templates/ .agency-os/
```

**If missing:** Create them:
```bash
mkdir -p data clients exports templates .agency-os
```

## Step 4: Test MCP Connectivity

Test that MCP tools respond correctly.

**Test 1: List leads**
Ask: "List all leads"

- **Expected:** Returns array (possibly empty `[]`)
- **If error:** MCP server not connected. Check:
  - Is the server running?
  - Is `.mcp.json` configured correctly?
  - Are paths absolute, not relative?

**Test 2: Pipeline summary**
Ask: "Show pipeline summary"

- **Expected:** Returns object with stage counts
- **If error:** Same troubleshooting as above

**Test 3: List clients**
Ask: "List all clients"

- **Expected:** Returns array (possibly empty `[]`)
- **If error:** Same troubleshooting as above

**Test 4: Get agency profile**
Ask: "Show agency profile"

- **Expected:** Returns object with agency details (or empty `{}`)
- **If error:** Same troubleshooting as above

## Step 5: Check API Configuration

For WQA audits, Ahrefs and Windsor API keys are required.

**Check environment variables are set:**
- `AHREFS_API_KEY` - Required for domain metrics, keywords, backlinks
- `WINDSOR_API_KEY` - Required for GA4, GSC, Meta Ads data

**How to check (in MCP config):**
Look at your `.mcp.json` or Claude Desktop config for the `env` section:

```json
{
  "mcpServers": {
    "bpt-agency-os": {
      "env": {
        "AHREFS_API_KEY": "...",
        "WINDSOR_API_KEY": "..."
      }
    }
  }
}
```

**Test API connectivity:**

For Ahrefs (if key is set):
Ask: "Get domain overview for example.com using Ahrefs"

For Windsor (if key is set):
Ask: "List Windsor accounts"

**Note:** Basic CRM features (leads, clients, projects, documents) work WITHOUT API keys. Only WQA audits require them.

## Step 6: Verify Agency Profile

Check that agency profile and owner are configured:

**Agency profile:**
Ask: "Show agency profile"

Should have at minimum:
- `name` - Your agency name
- `email` - Contact email
- `website` - Agency website

**Owner:**
Ask: "List team members"

Should have at least one member with `role: "owner"`.

**If not configured:**
- "Update agency with name '[Your Agency]', email '[email]', website '[url]'"
- "Add team member: [Name], email [email], role owner"

## Step 7: Generate a Support Bundle

After running the checks above, offer to produce a **support bundle** the user can paste into a support thread. This is the fastest way for the support team to debug a co-work session they can't see.

**Call:** `support_diagnostic_export` (no arguments). It returns a single JSON object containing server version, workspace schema, env-var **presence** (booleans only — never values), data-file health, directory layout, agency profile completeness, and a list of detected issues with suggested fixes.

**Save a copy to disk** so the user has it after the session ends. Use `file_save`:

```
context_type: "export"
context_id: "support"
subfolder: "support"
filename: "support-bundle-{YYYY-MM-DD-HHMM}.txt"
content: <the JSON returned by support_diagnostic_export>
```

This writes to `exports/support/support-bundle-{timestamp}.txt`.

**Present in chat** as a paste-able block:

````
Agency OS support bundle — paste this in your support thread.

```json
{
  ... JSON from support_diagnostic_export ...
}
```

Also saved at `exports/support/support-bundle-{timestamp}.txt`.
````

**Privacy note for the user:** No env-var values, no data-file contents, no file paths outside `AGENCY_ROOT` are included. Safe to paste into Slack/email/GitHub.

If `support_diagnostic_export` is "unknown tool", the MCP server is on an older build. Ask the user to update Agency OS (Claude Desktop: reinstall `dist/bpt-agency-os.mcpb`; Claude Code: `npx @bpt-agency-os/mcp-server` will pull the latest).

## Diagnostic Report Format

After running all checks, summarize:

```
## Agency OS Diagnostic Report

### Workspace
- Version: 1.0.0 ✓
- Last Updated: 2026-04-07 ✓

### Data Files
- agency.json: ✓ Valid
- team.json: ✓ Valid (2 members)
- leads.json: ✓ Valid (5 leads)
- clients.json: ✓ Valid (3 clients)
- projects.json: ✓ Valid
- sprints.json: ✓ Valid
- deliverables.json: ✓ Valid
- followups.json: ✓ Valid

### Directories
- data/: ✓
- clients/: ✓
- exports/: ✓
- templates/: ✓
- .agency-os/: ✓

### MCP Connectivity
- leads_list: ✓
- pipeline_summary: ✓
- clients_list: ✓
- agency_get: ✓

### API Keys
- Ahrefs: ✓ Configured
- Windsor: ✓ Configured

### Agency Profile
- Name: [Agency Name] ✓
- Owner: [Owner Name] ✓

### Status: All checks passed ✓
```

## Common Issues and Fixes

### "Unknown tool" errors
**Cause:** MCP server not connected
**Fix:**
1. Check `.mcp.json` has correct path to `mcp-server/dist/index.js`
2. Ensure path is absolute
3. Restart Claude Code/Desktop

### Empty or invalid JSON files
**Cause:** File corruption or incomplete write
**Fix:** Replace with minimal valid JSON:
```bash
echo "[]" > data/leads.json
echo "{}" > data/agency.json
```

### Missing .agency-os/version.json
**Cause:** Old workspace or first startup
**Fix:** Restart MCP server - migrations will create it automatically

### WQA tools failing
**Cause:** Missing API keys
**Fix:** Add `AHREFS_API_KEY` and `WINDSOR_API_KEY` to MCP config env

### "File not found" errors
**Cause:** Missing directories
**Fix:** Create them:
```bash
mkdir -p data clients exports templates .agency-os
```

## Output

After running diagnostics:
- ✅ All checks passing - Workspace healthy
- ⚠️ Warnings - Some optional features unavailable
- ❌ Errors - Issues that need fixing

For any ❌ errors, follow the fix instructions above.
