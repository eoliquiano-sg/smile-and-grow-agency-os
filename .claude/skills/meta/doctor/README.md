# Doctor Diagnostic

Comprehensive diagnostic tool for Agency OS workspaces. Identifies configuration issues and provides actionable fixes.

## What It Does

Runs a full health check on your Agency OS workspace:
- Verifies workspace version and migrations
- Validates all data files (JSON syntax and structure)
- Checks directory structure
- Tests MCP tool connectivity
- Verifies API key configuration
- Confirms agency profile and owner exist

## When to Use

| Scenario | Why Run Doctor |
|----------|----------------|
| Something isn't working | Identify the root cause |
| After updating Agency OS | Verify migrations ran correctly |
| Before starting a WQA audit | Confirm API keys are configured |
| MCP tools return errors | Check connectivity and file integrity |
| First time in a workspace | Baseline health check |

## Prerequisites

| Requirement | Notes |
|-------------|-------|
| Agency OS MCP server | Must be connected |
| Workspace initialized | Should have `data/` folder with JSON files |

## Inputs

None required. The skill reads your workspace configuration automatically.

## Outputs

A diagnostic report showing the status of each check:

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
- Windsor: ⚠️ Not configured

### Agency Profile
- Name: Acme Agency ✓
- Owner: Jane Smith ✓

### Status: All checks passed ✓
```

### Status Indicators

| Icon | Meaning |
|------|---------|
| ✓ | Check passed |
| ⚠️ | Warning - optional feature unavailable |
| ❌ | Error - needs fixing |

## What Gets Checked

### 1. Workspace Version
- File: `.agency-os/version.json`
- Verifies schema version and migration history

### 2. Data Files
| File | Expected Content |
|------|------------------|
| `data/agency.json` | `{}` or agency profile object |
| `data/team.json` | `[]` or array of team members |
| `data/leads.json` | `[]` or array of leads |
| `data/clients.json` | `[]` or array of clients |
| `data/projects.json` | `[]` or array of projects |
| `data/sprints.json` | `[]` or array of sprints |
| `data/deliverables.json` | `[]` or array of deliverables |
| `data/followups.json` | `[]` or array of follow-ups |

### 3. Directory Structure
| Directory | Purpose |
|-----------|---------|
| `data/` | JSON data files |
| `clients/` | Per-client folders |
| `exports/` | Generated documents |
| `templates/` | Document templates |
| `.agency-os/` | Workspace metadata |

### 4. MCP Connectivity
Tests these tools respond correctly:
- `leads_list`
- `pipeline_summary`
- `clients_list`
- `agency_get`

### 5. API Configuration
| Key | Required For |
|-----|--------------|
| `AHREFS_API_KEY` | Domain metrics, keywords, backlinks, WQA |
| `WINDSOR_API_KEY` | GA4, GSC, Meta Ads data |

**Note:** Basic CRM features work without API keys. Only WQA audits and analytics integrations require them.

### 6. Agency Profile
- Agency name configured
- At least one team member with `role: "owner"`

## Common Issues and Fixes

### "Unknown tool" errors
**Cause:** MCP server not connected

**Fix:**
1. Check your MCP config has the correct path
2. Ensure paths are absolute (not relative)
3. Restart Claude Code/Desktop

### Empty or invalid JSON files
**Cause:** File corruption or incomplete write

**Fix:**
```bash
echo "[]" > data/leads.json
echo "{}" > data/agency.json
```

### Missing .agency-os/version.json
**Cause:** Old workspace or first startup

**Fix:** Restart MCP server - migrations create it automatically

### WQA tools failing
**Cause:** Missing API keys

**Fix:** Add to your MCP config:
```json
{
  "env": {
    "AHREFS_API_KEY": "your-key",
    "WINDSOR_API_KEY": "your-key"
  }
}
```

### Missing directories
**Cause:** Incomplete initialization

**Fix:**
```bash
mkdir -p data clients exports templates .agency-os
```

## Related Skills

| Skill | When to Use |
|-------|-------------|
| `/bpt-workspace-setup` | First-time setup |
| `/bpt-proposal-generator` | Create proposals |

---

*Part of Agency OS v1.0 - Blueprint Training One-Person Agency program*
