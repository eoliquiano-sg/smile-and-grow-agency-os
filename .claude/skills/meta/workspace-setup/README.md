# Workspace Setup

Interactive onboarding for new Agency OS users. Sets up your agency profile, adds you as the owner, and introduces you to the dashboard.

## What It Does

This skill guides you through a conversational setup to:
- Create your agency profile (name, email, website, services)
- Add yourself as the owner/first team member
- Optionally import data from an existing sales deck
- Import existing leads or clients
- Show you the web dashboard

## Prerequisites

| Requirement | Notes |
|-------------|-------|
| Agency OS MCP server | Must be connected and running |
| Workspace initialized | Run `npx @bpt-agency-os/mcp-server init` first |

## Inputs

No files required. The skill asks questions conversationally.

### Information You'll Provide

| Field | Example | Required |
|-------|---------|----------|
| Agency name | "Acme Digital Marketing" | Yes |
| Agency email | "hello@acme.com" | Yes |
| Agency website | "https://acme.com" | No |
| Services offered | "SEO, Content Marketing, Meta Ads" | No |
| Your name | "Jane Smith" | Yes |
| Your email | "jane@acme.com" | Yes |

### Optional: Import from Sales Deck

If you have an existing sales deck, the skill can import:
- Pricing tiers and packages
- Team member info
- Implementation process/phases
- Case studies and results
- Testimonials

**Supported formats:**
- PDF file (provide file path)
- Canva link (public or shared)
- Google Slides link (public or shared)
- Any website URL with agency info

## Outputs

After setup completes:

| Output | Location |
|--------|----------|
| Agency profile | `data/agency.json` |
| Team members | `data/team.json` |
| Imported leads (optional) | `data/leads.json` |

## Workflow

The skill runs as an interactive conversation:

| Step | What Happens |
|------|--------------|
| 1. Welcome | Verifies MCP connection |
| 2. Agency Profile | Asks for name, email, website, services |
| 3. Add Owner | Creates your team member record |
| 4. Import Deck | (Optional) Extracts data from existing presentation |
| 5. Show Dashboard | Introduces http://localhost:3000 |
| 6. Import Data | (Optional) Add existing leads/clients |
| 7. Summary | Recap and suggested next actions |

## After Setup

Once complete, you can:

| Action | How |
|--------|-----|
| View dashboard | http://localhost:3000 |
| Create a lead | "Create a lead for [company], contact [name] at [email]" |
| Create a client | "Create a client for [company] with [service] service" |
| Check pipeline | "Show my pipeline summary" |
| Generate proposal | `/bpt-proposal-generator` |
| Run diagnostics | `/bpt-doctor` |

## Troubleshooting

| Issue | Cause | Fix |
|-------|-------|-----|
| "Can't connect to server" | MCP not configured | Check Settings → MCP Servers |
| Tools return errors | Server not running | Restart Claude Code/Desktop |
| Dashboard not loading | Port conflict | Check server logs for actual port |

## Data Storage

All data is stored locally in your workspace:

```
your-agency/
├── data/
│   ├── agency.json       ← Agency profile
│   ├── team.json         ← Team members (including you)
│   ├── leads.json        ← Sales pipeline
│   └── clients.json      ← Active clients
└── .agency-os/
    └── version.json      ← Workspace version tracking
```

---

*Part of Agency OS v1.0 - Blueprint Training One-Person Agency program*
