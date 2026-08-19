# SEO & GEO Proposal Generator

Generate professional, data-driven SEO proposals with competitive analysis, traffic trends, local visibility grids, and pricing recommendations.

## What It Does

This skill guides you through creating a visual HTML proposal presentation (15-25 slides) with:
- Competitor comparison tables
- Traffic trend charts (Chart.js)
- Marketing funnel analysis
- Local Pack visibility grids (if applicable)
- Pricing tiers and action plan
- Professional formatting at 1280x720 (presentation-ready)

## Prerequisites

### Required Tools & Accounts

| Tool | What You Need | Where to Export |
|------|---------------|-----------------|
| **Ahrefs** | Standard+ subscription | Site Explorer exports |
| **Local Falcon** | Account (if local SEO) | Grid exports per keyword/location |

### One-Time Agency Setup

Before your first proposal, configure agency-level defaults:
- **Pricing tiers** - Your standard packages and monthly rates
- **Action plan template** - Your implementation phases
- **Team members** - Who appears on proposals
- **Proposal defaults** - Contract terms, setup fees, CTA text

Run `/bpt-proposal-generator` and it will guide you through this setup, or import from an existing sales deck (PDF, Canva, Google Slides).

## Inputs

### Required Files

| File | Source | How to Get It |
|------|--------|---------------|
| Traffic history CSV | Ahrefs | Site Explorer → Overview → Export (select "History") |
| Top pages CSV | Ahrefs | Site Explorer → Top Pages → Export |

### Optional Files (Recommended)

| File | Source | When to Include |
|------|--------|-----------------|
| Referring domains CSV | Ahrefs | For backlink analysis slide |
| Local Falcon grid CSV | Local Falcon | For local pack visibility (one per keyword/location) |
| Screaming Frog internal CSV | Screaming Frog | For technical audit slide |
| AI tool screenshots | ChatGPT/Perplexity/Gemini | For GEO visibility slide |

### File Format Notes

- **Ahrefs CSVs**: UTF-16 LE encoding (default export format) - the parser handles this automatically
- **Local Falcon**: Export the grid as CSV, include one file per keyword/location combination
- **Screenshots**: PNG/JPG, place in `inputs/screenshots/`

## Outputs

### Primary Output

**`output/proposal.html`** - Single HTML file containing:
- All slides with embedded CSS
- Chart.js visualizations (traffic trends, competitor comparisons)
- Local Pack grids rendered as colored tables
- Print-ready at 1280x720 dimensions

### How to Use the Output

1. Open in browser to present or review
2. Print to PDF (Cmd/Ctrl+P → Save as PDF)
3. Edit HTML directly for final tweaks if needed

## Workflow Overview

The skill runs an interactive 5-phase workflow with checkpoints where you review and approve before continuing:

| Phase | What Happens | Checkpoint |
|-------|--------------|------------|
| **1. Discovery** | Create workspace, upload files, parse data | Review data summary |
| **2. Analysis** | Identify trends, gaps, strategic angles | Choose narrative angle |
| **3. Outline** | Determine which slides to include | Approve slide structure |
| **4. Building** | Generate each slide section | Review slides in batches |
| **5. Assembly** | Generate final HTML | Verify output |

## Customization

### Business Types

The skill automatically adjusts funnel classification and citation directories based on business type:

| Type | Example Keywords | Local Module |
|------|------------------|--------------|
| `law_firm` | attorney, lawyer, hire | Yes |
| `local_services` | services, quote, emergency | Yes |
| `healthcare` | appointment, book, doctor | Yes |
| `ecommerce` | product, buy, shop | No |
| `saas` | pricing, demo, trial | No |

### Slide Modules

- **Core slides** (always included): Cover, Executive Summary, Market, Performance, Funnel, Top Pages, Projections, Investment, Team, Next Steps
- **Traffic Decline slide**: Auto-included if traffic dropped ≥15% from peak
- **Local SEO module**: Included when `has_locations: true` - adds GEO Visibility, Local Pack grids, Location Pages, Citation Review
- **Technical Audit slide**: Included when Screaming Frog data is provided

### Overriding Agency Defaults

Each proposal auto-populates team, pricing, and action plan from your agency settings. To customize for a specific proposal, provide override data when the skill prompts you.

## Workspace Structure

When you create a proposal, it generates this structure:

```
leads/{lead-slug}/proposals/{proposal-id}/
├── proposal-state.json    # Tracks progress and slide data
├── inputs/                # Your uploaded files
│   ├── ahrefs/           # Traffic, pages, keywords CSVs
│   ├── local-falcon/     # Grid CSVs per location
│   ├── screaming-frog/   # Technical audit data
│   └── screenshots/      # AI tools, PageSpeed, etc.
├── parsed/               # Auto-generated JSON from CSVs
└── output/               # Final HTML proposal
```

## Troubleshooting

| Issue | Cause | Fix |
|-------|-------|-----|
| Traffic values show millions | Ahrefs reports cents | Parser auto-converts; re-parse if needed |
| `{{placeholder}}` visible | Slide data missing | Check that all required files were parsed |
| Charts not rendering | Missing data array | Verify traffic history CSV was uploaded |
| Local Pack grid empty | Business name mismatch | Verify GBP name matches Local Falcon export |
| Wrong slide count | Configuration issue | Re-run outline checkpoint |

## Related Tools

These MCP tools power the proposal workflow:

| Tool | Purpose |
|------|---------|
| `proposal_create` | Initialize workspace |
| `proposal_parse_file` | Parse CSV data files |
| `proposal_classify_pages` | Categorize pages into funnel |
| `proposal_generate_html` | Create final output |
| `proposal_get_state` | Check progress |

---

*Part of Agency OS v1.1 - Blueprint Training One-Person Agency program*
