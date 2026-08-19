# Agency OS Workspace

Welcome to Agency OS! This is your local-first agency management system.

## On Conversation Start

At the beginning of every new conversation, do the following:

1. **Check setup status**: Read `data/agency.json` and `data/team.json`. If the agency profile is empty (`{}`) or has no `name`, or if there are no team members with `role: "owner"`, proactively let the user know and suggest running the setup wizard (`/agency-os-meta-workspace-setup`).
2. **Mention the dashboard**: Remind the user that their visual dashboard is available at http://localhost:3001 for managing their pipeline, clients, and projects.
3. **If already set up**: Greet the user by agency name and give a brief status snapshot (e.g., number of active leads, clients, and any follow-ups due today).

## Getting Started

**New here?** Run the setup wizard:

```
/agency-os-meta-workspace-setup
```

This will help you:
- Set up your agency profile
- Add yourself as the owner
- Learn the basic commands

## Dashboard

**Your visual dashboard is at: http://localhost:3001**

Open it in your browser to:
- View and manage your sales pipeline
- Track clients and projects
- Edit data with a visual interface

The dashboard runs automatically when the MCP server is connected.

## Quick Commands

**Sales Pipeline:**
- "Show my pipeline summary"
- "Create a lead for [company], contact [name] at [email]"
- "List follow-ups due today"
- "Move lead [id] to qualified"

**Clients & Projects:**
- "List my active clients"
- "Create a client for [company] with [service] service"
- "Create a sprint for project [id]"
- "Show active sprints"

**Agency Profile:**
- "Show my agency profile"
- "Update agency with [field]: [value]"
- "List team members"

**Client Onboarding:**
- "Generate a proposal for lead [id]"
- "Onboard new client from lead [id]"
- "Create a project plan for [client]"

## Skills

| Skill | Description |
|-------|-------------|
| `/agency-os-meta-workspace-setup` | First-time setup wizard |
| `/agency-os-meta-doctor` | Diagnose connection issues |
| `/agency-os-sales-proposal-generator` | Generate proposals with competitive analysis |
| `/agency-os-delivery-client-onboarding` | 24-hour client onboarding workflow |
| `/agency-os-delivery-website-quality-audit` | Strategic website quality audit (xlsx → approvals → report → plan) |
| `/agency-os-productization-project-plan` | Generate a 12-month project plan from a completed WQA (or a template) |

## Data Storage

All your data is stored locally in this folder:

```
data/
├── agency.json       ← Agency profile
├── team.json         ← Team members
├── leads.json        ← Sales pipeline
├── clients.json      ← Active clients
├── projects.json     ← Client projects
├── sprints.json      ← Sprint tracking
└── deliverables.json ← Deliverable tracking

clients/
└── {client-slug}/    ← Per-client files
```

## Troubleshooting

**Tools not working?**
Run `/agency-os-meta-doctor` to diagnose issues.

**Dashboard not loading?**
- Check that the MCP server is connected (Settings → MCP Servers)
- Try http://localhost:3001 in your browser
- If port is in use, check server logs for the actual port

## Need Help?

- Run `/agency-os-meta-doctor` for diagnostics
- Check the documentation at https://github.com/The-Blueprint-Training/bpt-agency-os

---
*Agency OS v1.5.0*
