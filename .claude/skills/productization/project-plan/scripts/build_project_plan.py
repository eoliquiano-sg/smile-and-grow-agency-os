#!/usr/bin/env python3
"""Build a detailed project plan from WQA approvals.

Reads {slug}-approvals.json (+ its embedded target-pages) from a WQA audit folder
and generates a structured project-plan.json that the Agency OS MCP server can
bulk-import via the `project_plan_import` tool to create:
  - One project
  - Sprints 1 (Kickoff), 2 (Technical), 3 (Local SEO), 4 (Content), 5 (Links),
    6 (Reporting)
  - All deliverables — one per approved/edited recommendation (grouped + batched),
    one per link slot per target page, plus kickoff + monthly-report deliverables —
    each with assignee, due_date, status, priority, scheduled_month, and source
    metadata.

Scheduling model (12-month engagement):
  - Month 1: Sprint 2 Technical + Analytics Audit (Sprint 1 wraps as Kickoff)
  - Months 2-5: production — content batches drafted by Claude, reviewed by team
  - Months 6-12: stabilize + iterate
  - Link slots distributed M4 → end (LINKS_PER_MONTH/mo)

Assignment routing (generalized — no hardcoded team):
  Reads the agency's team from --team-json (data/team.json). Builds routing pools
  by matching each member's `skills` to the skill a task needs (technical_seo,
  content_writing, copywriting, link_building, strategy, ...). Round-robins within
  each pool to load-balance. Falls back to the owner / any active member for solo
  agencies or unmatched skills. Emits `assigned_to_email`; the MCP import tool
  resolves emails to team-member IDs.

Usage:
  python3 build_project_plan.py \
    --audit-dir /path/to/clients/{slug}/wqa/audits/{audit_id} \
    --client-slug webris \
    --client-id <uuid> \
    --team-json data/team.json \
    --start-date 2026-06-08 \
    --output /path/to/project-plan.json
"""

import argparse
import json
import os
import re
import sys
from collections import defaultdict
from datetime import date, timedelta


# ============ CLI ============

parser = argparse.ArgumentParser()
parser.add_argument("--audit-dir", required=True, help="The audit folder containing approvals.json")
parser.add_argument("--client-slug", required=True, help="File prefix for the approvals JSON")
parser.add_argument("--client-id", help="Agency OS client UUID (used in project record)")
parser.add_argument("--team-json", help="Path to data/team.json for assignment routing (optional)")
parser.add_argument("--project-name", help="Project name (defaults to 'WQA Implementation — {Month Year}')")
parser.add_argument("--start-date", help="Project start date YYYY-MM-DD (defaults to today)")
parser.add_argument("--engagement-months", type=int, default=12, help="Total engagement length in months (default 12)")
parser.add_argument("--batch-size", type=int, default=8, help="Pages per month for heavy content batches (default 8)")
parser.add_argument("--links-per-month", type=int, default=6, help="Link slots per production month (default 6)")
parser.add_argument("--vertical", default="local_service",
                    help="Client vertical. When != 'local_service', Sprint 3 Local SEO placeholders are auto-suppressed and Sprint 4 content production shifts up one month. Pass client.custom_fields.vertical. (default: local_service)")
parser.add_argument("--output", help="Where to write project-plan.json (defaults to audit folder)")
args = parser.parse_args()

# Vertical-aware behavior — non-local clients (SaaS, e-comm, B2B, etc.) skip
# Sprint 3 entirely and let content production start a month earlier.
IS_LOCAL = (args.vertical or "").strip().lower() == "local_service"

# ============ Load inputs ============

approvals_path = os.path.join(args.audit_dir, f"{args.client_slug}-approvals.json")
if not os.path.exists(approvals_path):
    sys.exit(f"ERROR: approvals.json not found at {approvals_path}. Run parse_approvals.py first.")
approvals = json.load(open(approvals_path))

# Active = Approved + Edit
active_recs = (approvals.get("buckets", {}).get("Approved") or []) + \
              (approvals.get("buckets", {}).get("Edit") or [])

tp_buckets = approvals.get("target_pages", {}).get("buckets", {})
active_tp = (tp_buckets.get("Approved") or []) + (tp_buckets.get("Edit") or [])


# ============ Team + assignment routing (generalized) ============
# Pools are built from the agency's own team.json. Each member contributes their
# email to every skill pool their `skills` match. Round-robin within a pool
# load-balances across people who can do the work.

def normalize_skill(s):
    """Lowercase + collapse non-alphanumerics to underscores so 'Technical SEO',
    'technical-seo' and 'technical_seo' all match."""
    return re.sub(r"[^a-z0-9]+", "_", (s or "").lower()).strip("_")


def load_team(team_json_path):
    """Return (members, owner_email). Active members only."""
    if not team_json_path or not os.path.exists(team_json_path):
        return [], None
    try:
        raw = json.load(open(team_json_path))
    except Exception as e:
        print(f"  ⚠ Could not read team.json ({e}); proceeding with no assignments", file=sys.stderr)
        return [], None
    members = [m for m in raw if m.get("active", True) and m.get("email")]
    owner = next((m["email"] for m in members if m.get("role") == "owner"), None)
    return members, owner


TEAM_MEMBERS, OWNER_EMAIL = load_team(args.team_json)

# email -> display name (for the summary printout)
TEAM = {m["email"]: {"name": m.get("name", m["email"]), "role": m.get("role", "member")}
        for m in TEAM_MEMBERS}

ALL_EMAILS = [m["email"] for m in TEAM_MEMBERS]

# Build skill -> [emails] pools (team-order preserved).
POOLS = defaultdict(list)
for _m in TEAM_MEMBERS:
    for _sk in (_m.get("skills") or []):
        POOLS[normalize_skill(_sk)].append(_m["email"])

# Action type -> required skill mapping
ACTION_TO_SKILL = {
    # Technical actions
    "Fix 404":             "technical_seo",
    "Noindex":             "technical_seo",
    "301 redirect":        "technical_seo",
    "Evaluate redirect":   "technical_seo",
    "Add canonical":       "technical_seo",
    "Add schema":          "technical_seo",
    "Update robots":       "technical_seo",
    "Indexability fix":    "technical_seo",
    "Sitemap fix":         "technical_seo",
    # Content body actions (full writing)
    "Rewrite":             "content_writing",
    "Expand content":      "content_writing",
    "Refresh content":     "content_writing",
    "Consolidate":         "content_writing",
    # Content meta-level actions
    "Rewrite title/meta":  "copywriting",
    "Update onpage":       "content_writing",
    # Strategy decisions
    "Evaluate":            "strategy",
}

# Per-skill fallback chains — if nobody has the exact skill, degrade sensibly.
SKILL_FALLBACKS = {
    "technical_seo":    ["technical_seo", "strategy"],
    "content_writing":  ["content_writing", "copywriting", "strategy"],
    "copywriting":      ["copywriting", "content_writing", "strategy"],
    "content_strategy": ["content_strategy", "content_writing", "strategy"],
    "link_building":    ["link_building", "strategy"],
    "analytics":        ["analytics", "technical_seo", "strategy"],
    "strategy":         ["strategy"],
}

_rr_counters = defaultdict(int)


def pool_for(skill):
    """Resolve the candidate email pool for a skill, with fallbacks."""
    for key in SKILL_FALLBACKS.get(skill, [skill, "strategy"]):
        if POOLS.get(key):
            return POOLS[key]
    if OWNER_EMAIL:
        return [OWNER_EMAIL]
    if ALL_EMAILS:
        return ALL_EMAILS
    return [None]  # solo / no team → unassigned (import leaves it blank)


def lead_for(skill):
    """First (preferred) person in a skill's pool — used for sprint leads."""
    return pool_for(skill)[0]


def assign_for(action_type):
    """Round-robin assign within the pool matching this action type's skill."""
    skill = ACTION_TO_SKILL.get(action_type, "strategy")
    pool = pool_for(skill)
    idx = _rr_counters[skill] % len(pool)
    _rr_counters[skill] += 1
    return pool[idx]


# ============ Scheduling — 12-month engagement, M1 = Tech only, M2-M5 = production ============

start_date = date.fromisoformat(args.start_date) if args.start_date else date.today()
def month_end(month_n):
    """Last day of month_n (1-indexed)."""
    from calendar import monthrange
    target = start_date.replace(day=1)
    for _ in range(month_n - 1):
        if target.month == 12:
            target = target.replace(year=target.year + 1, month=1)
        else:
            target = target.replace(month=target.month + 1)
    last = monthrange(target.year, target.month)[1]
    return target.replace(day=last)


def month_start(month_n):
    """First day a deliverable scheduled for `month_n` can actually start."""
    if month_n <= 1:
        return start_date
    return month_end(month_n - 1) + timedelta(days=1)


QUICK_TASK_DAYS = 7
def compute_task_dates(month_n, *, kind):
    """Return (start_date, due_date) for a deliverable.
    kind: 'heavy' (month-long) | 'quick' (1 week) | 'report' (last week)."""
    ms = month_start(month_n)
    me = month_end(month_n)
    if kind == "heavy":
        return ms, me
    if kind == "report":
        start = me - timedelta(days=QUICK_TASK_DAYS - 1)
        if start < ms:
            start = ms
        return start, me
    due = ms + timedelta(days=QUICK_TASK_DAYS)
    if due > me:
        due = me
    return ms, due

# Engagement end = start + N months
end_date = month_end(args.engagement_months)


# ============ Build the project + sprint shells ============

project = {
    "client_id": args.client_id,
    "name": args.project_name or f"WQA Implementation — {start_date.strftime('%B %Y')}",
    "project_type": "seo_sprint",
    "primary_goal": "Kickoff (WQA + report + plan, M1), technical fixes (M1), analytics setup (M1), content production (M3+), link building (M4+), monthly reporting throughout.",
    "start_date": start_date.isoformat(),
    "target_end_date": end_date.isoformat(),
}

# ===== Kickoff date math (Sprint 1 + Sprint 6 Analytics audit) =====
# Waterfall: everything downstream (Project Plan, Technical fixes, Analytics
# Audit) starts on the WQA close date — nothing kicks off before the audit lands.
WQA_START          = start_date
WQA_END            = start_date + timedelta(days=7)
WQA_REPORT_START   = WQA_END + timedelta(days=1)
WQA_REPORT_END     = WQA_REPORT_START + timedelta(days=3)   # WQA "close date"
PROJECT_PLAN_START = WQA_REPORT_END                         # 1-day deliverable, starts at close
PROJECT_PLAN_END   = PROJECT_PLAN_START + timedelta(days=1)
ANALYTICS_AUDIT_START = WQA_REPORT_END                      # waterfalls off WQA close
ANALYTICS_AUDIT_END   = ANALYTICS_AUDIT_START + timedelta(days=10)

# Sprint leads, resolved from the agency's own team
LEAD_STRATEGY  = lead_for("strategy")
LEAD_TECHNICAL = lead_for("technical_seo")
LEAD_CONTENT   = lead_for("content_writing")
LEAD_LINKS     = lead_for("link_building")
LEAD_ANALYTICS = lead_for("analytics")

sprints = [
    {
        "sprint_number": 1, "sprint_type": "onboarding", "name": "Sprint 1 (Kickoff)",
        "scheduled_start": start_date.isoformat(),
        "scheduled_end":   PROJECT_PLAN_END.isoformat(),
        "status": "active",
        "lead_email": LEAD_STRATEGY,
        "notes": "Kickoff phase: WQA → WQA Report → Project Plan. Auto-tracked deliverables flip to completed as each artifact lands."
    },
    {
        "sprint_number": 2, "sprint_type": "foundational", "name": "Sprint 2 (Technical)",
        "scheduled_start": (start_date + timedelta(days=1)).isoformat(),
        "scheduled_end": month_end(1).isoformat(),
        "status": "active",
        "lead_email": LEAD_TECHNICAL,
        "notes": "Technical fixes — 404s, redirects, indexability. Month 1. Grouped by action type."
    },
    {
        "sprint_number": 3, "sprint_type": "foundational", "name": "Sprint 3 (Local SEO)",
        "scheduled_start": (month_end(1) + timedelta(days=1)).isoformat(),
        "scheduled_end": month_end(2).isoformat(),
        "status": "pending",
        "lead_email": LEAD_TECHNICAL,
        "notes": "Local SEO foundation — GBP audit, citation cleanup, review velocity. Month 2 placeholders; expand on deep-dive."
    },
    {
        "sprint_number": 4, "sprint_type": "content", "name": "Sprint 4 (Content)",
        "scheduled_start": (month_end(2) + timedelta(days=1)).isoformat(),
        "scheduled_end": end_date.isoformat(),
        "status": "pending",
        "lead_email": LEAD_CONTENT,
        "notes": "Content production Months 3+. Strategy/gap analysis first, then grouped metadata work + batched heavy rewrites by priority."
    },
    {
        "sprint_number": 5, "sprint_type": "link", "name": "Sprint 5 (Links)",
        "scheduled_start": (month_end(1) + timedelta(days=1)).isoformat(),
        "scheduled_end": end_date.isoformat(),
        "status": "pending",
        "lead_email": LEAD_LINKS,
        "notes": "Link building. Month 3 = strategy + plan. Months 4+ = monthly batches (URLs in description)."
    },
    {
        "sprint_number": 6, "sprint_type": "reporting", "name": "Sprint 6 (Reporting)",
        "scheduled_start": start_date.isoformat(),
        "scheduled_end": end_date.isoformat(),
        "status": "pending",
        "lead_email": LEAD_ANALYTICS,
        "notes": "Recurring monthly performance report sent to client at the end of each month. Serves as visual month-break in the Tasks view."
    },
]


# ============ Schedule deliverables into months — GROUPED layout ============

PRIO_ORDER = {"P1": 0, "P2": 1, "P3": 2, "": 9}
BATCH_SIZE = args.batch_size  # pages per month for heavy content actions

UPDATED_CONTENT_ACTIONS = {"Rewrite", "Refresh content", "Expand content", "Consolidate"}
NEW_CONTENT_ACTIONS     = {"New content", "Create new page", "New page", "Create"}
HEAVY_CONTENT_ACTIONS   = UPDATED_CONTENT_ACTIONS | NEW_CONTENT_ACTIONS
METADATA_CONTENT_ACTIONS = {"Rewrite title/meta", "Update onpage", "Evaluate"}

tech_recs    = [r for r in active_recs if (r.get("category") or "").lower() == "technical"]
content_recs = [r for r in active_recs if (r.get("category") or "").lower() == "content"]


def _urls_block(recs, max_show=None):
    """Format a list of recs into a readable URL+next-step block for description."""
    lines = []
    for i, r in enumerate(recs, 1):
        if max_show and i > max_show:
            lines.append(f"  … and {len(recs) - max_show} more")
            break
        addr = r.get("page_address") or "—"
        prio = r.get("priority") or ""
        next_step = (r.get("specific_next_step") or "").strip()
        preview = next_step.split("\n")[0][:120]
        if preview:
            lines.append(f"  {i:>3}. [{prio}] {addr} — {preview}")
        else:
            lines.append(f"  {i:>3}. [{prio}] {addr}")
    return "\n".join(lines)


deliverables = []

import datetime as _dt
_RUN_TS = _dt.datetime.now(_dt.timezone.utc).isoformat(timespec="seconds")


# ---------- Sprint 1 (Kickoff) — WQA, Project Plan (2 deliverables) ----------
# WQA + WQA Report merged into ONE deliverable: its two outputs (the xlsx audit
# spreadsheet + the client-facing HTML report) are produced in the same Sprint 1
# work stream. Auto-completes only when BOTH artifacts exist on disk.
_wqa_done = (
    os.path.exists(os.path.join(args.audit_dir, f"{args.client_slug}-approvals.json"))
    and os.path.exists(os.path.join(args.audit_dir, f"{args.client_slug}-wqa-report.html"))
)
deliverables.append({
    "sprint_number": 1,
    "name": "WQA — Website Quality Audit",
    "description": (
        "Strategic audit of the website covering technical SEO, content quality, "
        "and link foundation.\n"
        "  · Run Screaming Frog crawl + Ahrefs site explorer pull\n"
        "  · Classify every page (Keep / Improve / Consolidate / Remove)\n"
        "  · Tag specific actions per page (Fix 404 / Rewrite / etc.)\n"
        "  · Capture target pages + their backlink gaps\n"
        "  · Strategist approval pass on every recommendation\n"
        "Two outputs (same work stream):\n"
        "  1. {slug}-wqa-data.xlsx — audit spreadsheet (4 tabs)\n"
        "  2. {slug}-wqa-report.html — client-facing HTML deck (5 sections)\n"
        "Auto-completes when BOTH the approvals JSON + HTML report exist on disk."
    ),
    "deliverable_type": "Kickoff",
    "priority": "P1",
    "assigned_to_email": LEAD_STRATEGY,
    "start_date": WQA_START.isoformat(),
    "due_date":   WQA_REPORT_END.isoformat(),   # spans the whole xlsx → report window
    "scheduled_month": 1,
    "ai_assisted": True,
    "auto_tracked": True,
    "auto_complete_artifacts": [
        f"{args.client_slug}-approvals.json",
        f"{args.client_slug}-wqa-report.html",
    ],
    "status": "completed" if _wqa_done else "pending",
    "completed_at": _RUN_TS if _wqa_done else None,
    "source": {
        "category": "Kickoff",
        "action_type": "WQA",
        "notes": "Outputs xlsx audit spreadsheet + HTML client report.",
    },
})

deliverables.append({
    "sprint_number": 1,
    "name": "Project Plan (12-month engagement)",
    "description": (
        "Build the structured project plan from the WQA approvals + target pages. "
        "Generates sprints + monthly deliverable schedule for the full engagement.\n"
        "  · Sprints 2-6 (Technical / Local / Content / Links / Reporting)\n"
        "  · Monthly batches + client check-ins\n"
        "  · Per-deliverable owners, due dates, priorities\n"
        "Output: {slug}-project-plan.json (exportable to ClickUp/Asana/Monday via "
        "export_project_plan.py). Auto-completed by build_project_plan.py."
    ),
    "deliverable_type": "Kickoff",
    "priority": "P1",
    "assigned_to_email": OWNER_EMAIL or LEAD_STRATEGY,
    "start_date": PROJECT_PLAN_START.isoformat(),
    "due_date":   PROJECT_PLAN_END.isoformat(),
    "scheduled_month": 1,
    "ai_assisted": True,
    "auto_tracked": True,
    "auto_complete_artifact": f"{args.client_slug}-project-plan.json",
    "status": "completed",            # we are writing the plan right now
    "source": {
        "category": "Kickoff",
        "action_type": "Project Plan",
        "notes": "Auto-completed by build_project_plan.py on every regeneration.",
    },
})


# ---------- Sprint 2 (Technical) — Month 1, grouped by action type ----------
tech_by_action = defaultdict(list)
for r in tech_recs:
    tech_by_action[r.get("action_type") or "Other"].append(r)

TECH_ACTION_ORDER = [
    "Fix 404", "Indexability fix", "Noindex", "Add canonical",
    "301 redirect", "Evaluate redirect", "Add schema",
    "Update robots", "Sitemap fix", "Other",
]

for action in TECH_ACTION_ORDER:
    bucket = tech_by_action.get(action, [])
    if not bucket:
        continue
    bucket_sorted = sorted(bucket, key=lambda r: (PRIO_ORDER.get(r.get("priority"), 9), r.get("page_address") or ""))
    n = len(bucket_sorted)
    # Waterfall: technical work can't start before the WQA is delivered.
    s = WQA_REPORT_END
    due = s + timedelta(days=QUICK_TASK_DAYS)
    if due > month_end(1):
        due = month_end(1)
    deliverables.append({
        "sprint_number": 2,
        "name": f"{action} — {n} URL{'s' if n != 1 else ''}",
        "description": (
            f"Technical action: {action}\n"
            f"URLs ({n}):\n"
            f"{_urls_block(bucket_sorted)}"
        ),
        "deliverable_type": "Technical",
        "priority": min((r.get("priority") for r in bucket_sorted), key=lambda p: PRIO_ORDER.get(p, 9)),
        "assigned_to_email": assign_for(action),
        "start_date": s.isoformat(),
        "due_date": due.isoformat(),
        "scheduled_month": 1,
        "ai_assisted": False,
        "source": {
            "category": "Technical",
            "action_type": action,
            "grouped_count": n,
            "approvals_rows": [r.get("row") for r in bucket_sorted],
            "urls": [r.get("url") for r in bucket_sorted],
        },
    })


# ---------- Sprint 3 (Local SEO) — mirrors the /bpt-local-seo-audit sub-process ----------
# These map 1:1 to the Local SEO + GEO process (run via /bpt-local-seo-audit). The audit
# is Claude-produced (one workbook); everything after it is MANUAL execution —
# claiming/updating live profiles + citations — which Claude can't do (permissioned).
# Flagged manual + pointed at the Local SEO Audit workbook; recommend Loganix for the grind.
local_seo_placeholders = [
    {
        "name": "Local SEO Audit (workbook)",
        "description": (
            "Full Local SEO + GEO audit via /bpt-local-seo-audit — one workbook:\n"
            "  · NAP Info (all verified locations)\n"
            "  · Competitive research + baseline (Maps pack, competitors)\n"
            "  · Keyword Performance (volume + organic + Maps rank)\n"
            "  · GBP Optimization change-set + Products + practice-area graphics\n"
            "  · Aggregator Optimization set + Citations tracker\n"
            "Basis for every execution deliverable below."
        ),
        "assigned_skill": "strategy",
        "ai_assisted": True,
        "manual": False,
    },
    {
        "name": "Update GBP listings (all locations)",
        "description": (
            "MANUAL — apply the GBP Optimization change-set per office:\n"
            "  · Localized keyword+GEO descriptions, primary/secondary categories\n"
            "  · Services, attributes, hours, service areas\n"
            "  · FIX: true local NAP phone (not CallRail tracking), localized Posts\n"
            "Apply in business.google.com from the Local SEO Audit workbook."
        ),
        "assigned_skill": "technical_seo",
        "manual": True,
    },
    {
        "name": "GBP Products + practice-area graphics",
        "description": (
            "MANUAL — add GBP Products (one per practice area, full descriptions) and\n"
            "upload the branded practice-area graphics + office/team photos per office.\n"
            "Source: Products (GBP) tab + gbp-images/ in the Local SEO Audit workbook."
        ),
        "assigned_skill": "technical_seo",
        "manual": True,
    },
    {
        "name": "Aggregator profile optimization",
        "description": (
            "MANUAL — claim + build out the niche-aligned aggregator profiles\n"
            "(universal core: Apple, Bing, Yelp, BBB, Facebook, LinkedIn, etc. + vertical add-ons).\n"
            "Fix any NAP mismatches on live profiles; load description/services/photos/links.\n"
            "Source: Aggregator Optimization tab. Recommend Loganix if outsourcing."
        ),
        "assigned_skill": "technical_seo",
        "manual": True,
    },
    {
        "name": "Citation cleanup + building",
        "description": (
            "MANUAL — work the full Citations tracker (fix-first → claim Tier-1 free →\n"
            "data aggregators (Data Axle/Neustar/Foursquare) → build the rest), NAP identical everywhere.\n"
            "Track status per directory. Recommend Loganix / WhiteSpark for the volume."
        ),
        "assigned_skill": "technical_seo",
        "manual": True,
    },
    {
        "name": "Review generation + response system",
        "description": (
            "MANUAL — stand up the review engine:\n"
            "  · NPS/review automation (happy → public Google review, unhappy → private feedback)\n"
            "  · Compliant SMS/messaging registration; human-reviewed response templates\n"
            "  · Ongoing weekly review monitoring + responses"
        ),
        "assigned_skill": "strategy",
        "manual": True,
    },
]
# Vertical-aware: only emit Sprint 3 Local SEO placeholders for local-business
# clients. Non-local verticals (SaaS, e-comm, B2B) skip them entirely (and gain
# a month of content production — see HEAVY_START_MONTH below).
if not IS_LOCAL:
    local_seo_placeholders = []

for p in local_seo_placeholders:
    skill = p.pop("assigned_skill", "technical_seo")
    is_manual = p.get("manual", False)
    pool = pool_for(skill)
    idx = _rr_counters[f"sprint3:{skill}"] % len(pool)
    _rr_counters[f"sprint3:{skill}"] += 1
    deliverables.append({
        "sprint_number": 3,
        "name": p["name"],
        "description": p["description"],
        "deliverable_type": "Local",
        "priority": "P2",
        "assigned_to_email": pool[idx],
        "start_date": compute_task_dates(2, kind="quick")[0].isoformat(),
        "due_date":   compute_task_dates(2, kind="quick")[1].isoformat(),
        "scheduled_month": 2,
        "ai_assisted": p.get("ai_assisted", False),
        "is_placeholder": False,
        "source": {
            "category": "Local",
            "action_type": "Local SEO process step (manual execution)" if is_manual else "Local SEO process step",
            "notes": (
                "MANUAL — apply from the Local SEO Audit workbook; not live until updated by a person or a service (Loganix recommended)."
                if is_manual else
                "Produced by /bpt-local-seo-audit. Source of truth for the manual execution steps below."
            ),
        },
    })


# ---------- Sprint 4 (Content) — strategy first, then grouped + batched ----------

deliverables.append({
    "sprint_number": 4,
    "name": "Content Strategy + gap analysis",
    "description": (
        "Sprint 4 strategic foundation. Locks in the content roadmap that every "
        "subsequent monthly batch consumes:\n"
        "  · Review the full list of content actions tagged in the WQA\n"
        "  · Categorize by content silo (service pages, blog topics, hub pages)\n"
        "  · Identify content gaps (topics we should cover but don't)\n"
        "  · Split queue into Refresh/Rewrite (existing) vs Create New (greenfield)\n"
        "  · Lock in priority order for batched rewrites + new pages Months 3+\n"
        "  · Populate the client's content workbook with the queue\n"
        "All subsequent content batches depend on the priority order set here."
    ),
    "deliverable_type": "Content",
    "content_subtype": "strategy",
    "priority": "P1",
    "assigned_to_email": LEAD_CONTENT,
    "start_date": compute_task_dates(2, kind="quick")[0].isoformat(),
    "due_date":   compute_task_dates(2, kind="quick")[1].isoformat(),
    "scheduled_month": 2,
    "ai_assisted": False,
    "is_strategy": True,
    "source": {
        "category": "Content",
        "action_type": "Content Strategy",
        "notes": "Core deliverable, not a placeholder. Runs Month 2, content batches start Month 3.",
    },
})

# Local clients: heavy content starts Month 3 (Month 2 is busy with Sprint 3
# Local SEO). Non-local: Sprint 3 was suppressed, so content starts Month 2 —
# an extra month of production at the front.
HEAVY_START_MONTH = 3 if IS_LOCAL else 2
HEAVY_LAST_MONTH = args.engagement_months
heavy_months = list(range(HEAVY_START_MONTH, HEAVY_LAST_MONTH + 1))


def _build_heavy_batches(recs_in_stream, *, stream_label, content_subtype, batch_size):
    """Batch a stream of content recs by month."""
    if not recs_in_stream:
        return
    sorted_recs = sorted(recs_in_stream, key=lambda r: (
        PRIO_ORDER.get(r.get("priority"), 9),
        r.get("action_type") or "",
        r.get("page_address") or "",
    ))
    for batch_idx in range(0, len(sorted_recs), batch_size):
        batch = sorted_recs[batch_idx: batch_idx + batch_size]
        month_offset = batch_idx // batch_size
        if month_offset < len(heavy_months):
            target_month = heavy_months[month_offset]
        else:
            target_month = heavy_months[-1] if heavy_months else HEAVY_START_MONTH
        actions_in_batch = sorted({r.get("action_type") or "?" for r in batch})
        action_label = " / ".join(actions_in_batch) if len(actions_in_batch) > 1 else actions_in_batch[0]
        deliverables.append({
            "sprint_number": 4,
            "name": f"{stream_label} {len(batch)} pages — Month {target_month}",
            "description": (
                f"{stream_label} batch — Month {target_month} ({len(batch)} pages, priority order):\n"
                f"Actions in this batch: {action_label}\n\n"
                f"{_urls_block(batch)}\n\n"
                f"Capacity assumption: ~{batch_size} pages/month. "
                f"Claude drafts → team reviews + publishes. "
                f"Specific next steps are on each page row in the WQA approvals."
            ),
            "deliverable_type": "Content",
            "content_subtype": content_subtype,
            "priority": min((r.get("priority") for r in batch), key=lambda p: PRIO_ORDER.get(p, 9)),
            "assigned_to_email": assign_for(actions_in_batch[0] if actions_in_batch else "Rewrite"),
            "start_date": compute_task_dates(target_month, kind="heavy")[0].isoformat(),
            "due_date":   compute_task_dates(target_month, kind="heavy")[1].isoformat(),
            "scheduled_month": target_month,
            "ai_assisted": True,
            "is_heavy_batch": True,
            "source": {
                "category": "Content",
                "action_type": "Content batch",
                "content_subtype": content_subtype,
                "actions_in_batch": list(actions_in_batch),
                "grouped_count": len(batch),
                "approvals_rows": [r.get("row") for r in batch],
                "urls": [r.get("url") for r in batch],
            },
        })


updated_recs = [r for r in content_recs if r.get("action_type") in UPDATED_CONTENT_ACTIONS]
new_recs     = [r for r in content_recs if r.get("action_type") in NEW_CONTENT_ACTIONS]

_build_heavy_batches(updated_recs, stream_label="Rewrite/refresh", content_subtype="updated", batch_size=BATCH_SIZE)
_build_heavy_batches(new_recs,     stream_label="Create new",       content_subtype="new",     batch_size=BATCH_SIZE)

# Metadata-level content actions — grouped by action_type. Scheduled the same
# month heavy content starts (M3 local / M2 non-local) so content launches together.
META_SWEEP_MONTH = HEAVY_START_MONTH
meta_by_action = defaultdict(list)
for r in content_recs:
    if r.get("action_type") in METADATA_CONTENT_ACTIONS:
        meta_by_action[r.get("action_type") or "Other"].append(r)

for action in ("Rewrite title/meta", "Update onpage", "Evaluate"):
    bucket = meta_by_action.get(action, [])
    if not bucket:
        continue
    bucket_sorted = sorted(bucket, key=lambda r: (PRIO_ORDER.get(r.get("priority"), 9), r.get("page_address") or ""))
    n = len(bucket_sorted)
    label = {"Rewrite title/meta": "Update titles + metas",
             "Update onpage": "Update onpage elements",
             "Evaluate": "Strategist eval"}[action]
    deliverables.append({
        "sprint_number": 4,
        "name": f"{label} — {n} URL{'s' if n != 1 else ''}",
        "description": (
            f"Bulk metadata work — {action} across {n} URLs.\n"
            f"Quick wins; batch in Month {META_SWEEP_MONTH} then sweep the next month for tail items.\n\n"
            f"{_urls_block(bucket_sorted)}"
        ),
        "deliverable_type": "Content",
        "priority": min((r.get("priority") for r in bucket_sorted), key=lambda p: PRIO_ORDER.get(p, 9)),
        "assigned_to_email": assign_for(action),
        "start_date": compute_task_dates(META_SWEEP_MONTH, kind="quick")[0].isoformat(),
        "due_date":   compute_task_dates(META_SWEEP_MONTH, kind="quick")[1].isoformat(),
        "scheduled_month": META_SWEEP_MONTH,
        "ai_assisted": True,
        "source": {
            "category": "Content",
            "action_type": action,
            "grouped_count": n,
            "approvals_rows": [r.get("row") for r in bucket_sorted],
            "urls": [r.get("url") for r in bucket_sorted],
        },
    })


# ---------- Sprint 5 (Links) — strategy + plan, then monthly batches ----------

link_strategy_tasks = [
    {
        "name": "Link Strategy",
        "description": (
            "Sprint 5 strategic foundation. Locks in how we acquire links:\n"
            "  · Target DR range for prospect domains\n"
            "  · Mix of link types (guest post / sponsored / NOBS / resource / relationship / podcast)\n"
            "  · Monthly velocity assumption\n"
            "  · Niche relevance bar\n"
            "  · Outreach platform (email, LinkedIn, partnerships)\n"
            "  · Budget per link tier"
        ),
        "link_subtype": "strategy",
    },
    {
        "name": "Link plan + initial prospecting",
        "description": (
            "Translate strategy into an initial target list.\n"
            "  · Seed 30-50 prospect domains aligned with strategy\n"
            "  · Score by DR, relevance, traffic, ease-of-acquisition\n"
            "  · Distribute target pages across the prospects\n"
            "  · Populate the central link DB with initial 'Reply Pending' rows\n"
            "  · Hand off to Months 4+ for outreach + acquisition"
        ),
        "link_subtype": "prospecting",
    },
]
for p in link_strategy_tasks:
    deliverables.append({
        "sprint_number": 5,
        "name": p["name"],
        "description": p["description"],
        "deliverable_type": "Link",
        "link_subtype": p["link_subtype"],
        "priority": "P1",
        "assigned_to_email": LEAD_LINKS,
        "start_date": compute_task_dates(3, kind="quick")[0].isoformat(),
        "due_date":   compute_task_dates(3, kind="quick")[1].isoformat(),
        "scheduled_month": 3,
        "ai_assisted": False,
        "is_strategy": True,
        "source": {
            "category": "Link",
            "action_type": "Link Strategy",
            "link_subtype": p["link_subtype"],
            "notes": "Core deliverable. Month 3 strategy + plan, monthly link batches start Month 4.",
        },
    })

LINKS_PER_MONTH = args.links_per_month
LINK_PRODUCTION_MONTHS = list(range(4, args.engagement_months + 1))
total_link_slots = LINKS_PER_MONTH * len(LINK_PRODUCTION_MONTHS)

if active_tp and total_link_slots > 0:
    n_pages = len(active_tp)
    flat_slots = []
    base = total_link_slots // n_pages
    extras = total_link_slots % n_pages
    for i, tp in enumerate(active_tp):
        n_slots = base + (1 if i < extras else 0)
        flat_slots.extend([tp] * n_slots)

    for m_idx, m in enumerate(LINK_PRODUCTION_MONTHS):
        month_targets = flat_slots[m_idx * LINKS_PER_MONTH: (m_idx + 1) * LINKS_PER_MONTH]
        if not month_targets:
            continue
        target_lines = []
        for i, tp in enumerate(month_targets, 1):
            addr = tp.get("page_address") or "—"
            kw = tp.get("target_keyword") or ""
            pos = tp.get("current_position") or "?"
            rd = tp.get("ref_domains") or 0
            target_lines.append(f"  {i}. {addr}  ·  '{kw}' (pos {pos}, {rd} ref domains)")
        deliverables.append({
            "sprint_number": 5,
            "name": f"Build {len(month_targets)} links — Month {m}",
            "description": (
                f"Acquire {len(month_targets)} links this month, distributed across target pages:\n\n"
                + "\n".join(target_lines)
                + "\n\nTactics to mix: digital PR, niche-edit / link insertion outreach, podcast appearances, "
                  "guest posts, sponsored placements. Track every outcome in the central link DB."
            ),
            "deliverable_type": "Link",
            "priority": "P2",
            "assigned_to_email": LEAD_LINKS,
            "start_date": compute_task_dates(m, kind="heavy")[0].isoformat(),
            "due_date":   compute_task_dates(m, kind="heavy")[1].isoformat(),
            "scheduled_month": m,
            "ai_assisted": False,
            "is_heavy_batch": True,
            "source": {
                "category": "Link",
                "action_type": "Link batch",
                "grouped_count": len(month_targets),
                "target_pages": [tp.get("url") for tp in month_targets],
                "month_index": m_idx + 1,
            },
        })


# ---------- Sprint 6 (Reporting) — Analytics Audit + recurring monthly reports ----------

deliverables.append({
    "sprint_number": 6,
    "name": "Analytics Audit — conversion tracking + measurement setup",
    "description": (
        "Foundational analytics audit — verify the measurement layer is trustworthy "
        "before any monthly reporting is meaningful. Focus on conversion plumbing:\n"
        "  · GA4 conversion events — firing reliably, flagged as conversions\n"
        "  · Call-tracking integrations (WhatConverts / CallRail): DNI, attribution, event push-through\n"
        "  · Form tracking — submission events, lead source attribution\n"
        "  · CRM integration (HubSpot / Salesforce / Pipedrive) — sources tagged correctly\n"
        "  · GA4 ↔ GSC link active\n"
        "  · Cross-domain / subdomain tracking gaps\n"
        "  · GBP Insights accessibility\n"
        "  · Note any tracking holes that would invalidate monthly reports.\n\n"
        "Output: short Loom + written summary of what's wired, what's broken, "
        "and what needs fixing before Month 1 reporting."
    ),
    "deliverable_type": "Reporting",
    "priority": "P1",
    "assigned_to_email": LEAD_ANALYTICS,
    "start_date": ANALYTICS_AUDIT_START.isoformat(),
    "due_date":   ANALYTICS_AUDIT_END.isoformat(),
    "scheduled_month": 1,
    "ai_assisted": False,
    "is_analytics_audit": True,
    "source": {
        "category": "Reporting",
        "action_type": "Analytics Audit",
        "notes": "Runs Month 1 right after the WQA. 10-day duration.",
    },
})

# WQA Refresh — mid-engagement audit at M6 + end-of-engagement audit at M12.
# P1 strategic checkpoints to recalibrate the plan / inform the next 6 months.
for refresh_m, label in [(6, "Mid-engagement Audit"), (12, "End-of-engagement Audit")]:
    if refresh_m > args.engagement_months:
        continue
    deliverables.append({
        "sprint_number": 6,
        "name": f"WQA Refresh — {label} (Month {refresh_m})",
        "description": (
            f"Re-run a mini-WQA to recalibrate the plan at Month {refresh_m}.\n"
            f"  · Fresh SF crawl + Ahrefs pull\n"
            f"  · Compare current performance vs the initial WQA baseline\n"
            f"  · Score what's working (content/links/technical) and what's not\n"
            f"  · Update the next-6-months roadmap (or close-out report at M12)\n"
            f"  · Strategist-approval pass on any new recommendations\n"
            f"Output: WQA Refresh deck + revised plan (mid) or final close-out (end)."
        ),
        "deliverable_type": "Reporting",
        "priority": "P1",
        "assigned_to_email": LEAD_ANALYTICS,
        "start_date": compute_task_dates(refresh_m, kind="heavy")[0].isoformat(),
        "due_date":   compute_task_dates(refresh_m, kind="heavy")[1].isoformat(),
        "scheduled_month": refresh_m,
        "ai_assisted": True,
        "is_wqa_refresh": True,
        "source": {
            "category": "Reporting",
            "action_type": "WQA Refresh",
            "month": refresh_m,
        },
    })

# Client Check-ins — one per month starting Month 2 (no check-in for Month 1,
# the WQA is the M1 client interaction). Runs the first 7 days of the month and
# reports on the PRIOR month. Bundles report + analysis + optional call. Replaces
# the legacy end-of-month "Monthly Report" (carries is_monthly_report for compat).
def _first_week_of(month_n):
    ms = month_start(month_n)
    return ms, ms + timedelta(days=6)

for m in range(2, args.engagement_months + 1):
    prior_month = m - 1
    cs, cd = _first_week_of(m)
    deliverables.append({
        "sprint_number": 6,
        "name": f"Client Check-in — Month {m} (covers Month {prior_month} performance)",
        "description": (
            f"Monthly check-in with the client. Three components:\n\n"
            f"  1. Monthly Report (covering Month {prior_month}): GA4 organic + total "
            f"traffic, GSC clicks/impressions/position deltas, GBP (if local), "
            f"deliverables completed vs scheduled, live content + links shipped.\n"
            f"  2. Analysis writeup: what moved and why, what to double down on, "
            f"recommendations for next month's focus.\n"
            f"  3. Optional client call: offer a 30-min walkthrough; if declined, "
            f"send the deck + analysis by email.\n\n"
            f"Scheduled the first 7 days of Month {m} so the prior month's data has settled."
        ),
        "deliverable_type": "Client Check-in",
        "priority": "P1",
        "assigned_to_email": LEAD_ANALYTICS,
        "start_date": cs.isoformat(),
        "due_date":   cd.isoformat(),
        "scheduled_month": m,
        "ai_assisted": True,
        "is_monthly_report": True,    # backward-compat with dashboard gray-row styling
        "is_client_checkin": True,
        "source": {
            "category": "Reporting",
            "action_type": "Client Check-in",
            "covers_month": prior_month,
        },
    })


# ============ Build the final plan ============

plan = {
    "client_id": args.client_id,
    "client_slug": args.client_slug,
    "source_audit_id": approvals.get("audit_id"),
    "source_approvals_path": approvals_path,
    "project": project,
    "sprints": sprints,
    "deliverables": deliverables,
    "summary": {
        "total_deliverables": len(deliverables),
        "by_sprint": {f"Sprint {n}": sum(1 for d in deliverables if d["sprint_number"] == n) for n in (1, 2, 3, 4, 5, 6)},
        "by_month": {f"Month {m}": sum(1 for d in deliverables if d.get("scheduled_month") == m) for m in range(1, args.engagement_months + 1)},
        "by_assignee": {},
        "ai_assisted_count": sum(1 for d in deliverables if d.get("ai_assisted")),
        "placeholder_count": sum(1 for d in deliverables if d.get("is_placeholder")),
    },
}
for d in deliverables:
    email = d.get("assigned_to_email")
    if not email:
        continue
    plan["summary"]["by_assignee"][email] = plan["summary"]["by_assignee"].get(email, 0) + 1


# ============ Write output ============

output_path = args.output or os.path.join(args.audit_dir, f"{args.client_slug}-project-plan.json")
with open(output_path, "w") as f:
    json.dump(plan, f, indent=2)

print(f"\nProject plan written to: {output_path}")
print(f"\nSummary:")
print(f"  Project:            {project['name']}")
print(f"  Engagement:         {start_date} → {end_date} ({args.engagement_months} months)")
print(f"  Total deliverables: {plan['summary']['total_deliverables']}")
print(f"  AI-assisted:        {plan['summary']['ai_assisted_count']}")
if not TEAM_MEMBERS:
    print(f"  ⚠ No team loaded — deliverables left unassigned (pass --team-json data/team.json)")
print(f"\n  By sprint:")
for sprint, n in plan["summary"]["by_sprint"].items():
    print(f"    {sprint}: {n}")
print(f"\n  By month:")
for month, n in plan["summary"]["by_month"].items():
    print(f"    {month}: {n}")
print(f"\n  By assignee:")
for email, n in sorted(plan["summary"]["by_assignee"].items(), key=lambda x: -x[1]):
    name = TEAM.get(email, {}).get("name", email)
    print(f"    {name:<22} ({email}): {n}")
