#!/usr/bin/env python3
"""Build the agency-wide HTML dashboard (v2: task-oriented with Kanban).

Single self-contained HTML with:
  - Fixed left sidebar nav (Clients / Reporting / Admin)
  - Clients grid (default) with status-circle cards
      green  = client.status == 'active' AND has an active/planning project
      yellow = client.status == 'onboarding'
      red    = client.status in (paused, churned) OR no project
  - Per-client detail view with three project views:
      List   — tasks grouped by STATUS (TO DO / IN PROGRESS / REVIEW / DELAYED / COMPLETED / BLOCKED)
              with subtasks indented under each parent task
      Kanban — columns by status, cards are parent tasks
      By Person — each team member's queue
  - Reporting + Admin placeholders
  - Hash-based routing: #clients | #client/{slug} | #reporting | #admin

Tasks are derived by grouping deliverables on (sprint, action_type, scheduled_month).
A group of 1 → atomic task. A group of >1 → parent task with subtasks.

Usage:
  python3 build_agency_dashboard.py --workspace-root . --output agency-dashboard.html
"""

import argparse
import json
import os
import re
import sys
from collections import defaultdict, Counter
from datetime import date

# sheets_sync lives alongside this script; ensure it's importable.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import sheets_sync  # noqa: E402


parser = argparse.ArgumentParser()
parser.add_argument("--workspace-root", default=".", help="Path to the agency-os workspace root")
parser.add_argument("--output", required=True, help="Output HTML path")
parser.add_argument("--primary-color", default="#2563EB", help="Brand accent")
args = parser.parse_args()

ROOT = os.path.abspath(args.workspace_root)
PRIMARY = args.primary_color
TODAY = date.today().isoformat()


def esc(s):
    if s is None: return ""
    return str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")

def slugify(s):
    s = re.sub(r"[^a-z0-9-]+", "-", (s or "").lower())
    return re.sub(r"-+", "-", s).strip("-")


# ============ Load workspace data ============

agency  = json.load(open(os.path.join(ROOT, "data", "agency.json")))
clients = json.load(open(os.path.join(ROOT, "data", "clients.json")))
projects = json.load(open(os.path.join(ROOT, "data", "projects.json")))
team = json.load(open(os.path.join(ROOT, "data", "team.json"))) if os.path.exists(os.path.join(ROOT, "data", "team.json")) else []

projects_by_client = defaultdict(list)
for p in projects:
    projects_by_client[p.get("client_id")].append(p)


def find_project_plan(client):
    slug = client.get("custom_fields", {}).get("slug") or slugify(client.get("company_name", ""))
    client_dir = os.path.join(ROOT, "clients", slug)
    if not os.path.isdir(client_dir):
        return None
    wqa_audits = os.path.join(client_dir, "wqa", "audits")
    if not os.path.isdir(wqa_audits):
        return None
    candidates_found = []
    for audit_id in os.listdir(wqa_audits):
        audit_dir = os.path.join(wqa_audits, audit_id)
        if not os.path.isdir(audit_dir): continue
        for fn in os.listdir(audit_dir):
            if fn.endswith("-project-plan.json"):
                candidates_found.append((os.path.getmtime(os.path.join(audit_dir, fn)),
                                         os.path.join(audit_dir, fn),
                                         audit_id))
    if not candidates_found:
        return None
    candidates_found.sort(reverse=True)
    mtime, path, audit_id = candidates_found[0]
    return {"plan": json.load(open(path)), "slug": slug, "audit_id": audit_id, "path": path}


_KNOWN_STATUS_KEYS = {"scheduled", "assigned", "working", "review_needed", "update_needed",
                       "re_assigned", "delayed", "late", "approved", "completed"}

def default_status(d):
    """Derive default status for a deliverable.

    - 'delayed' is auto-set when due_date has passed and not yet completed.
    - Otherwise 'scheduled' for fresh items (or map from raw status if any).
    """
    raw = (d.get("status") or "").lower()
    raw_map = {
        "pending": "scheduled", "in_progress": "working", "review": "review_needed",
        "completed": "completed", "blocked": "delayed",
    }
    s = raw_map.get(raw, raw if raw in _KNOWN_STATUS_KEYS else "scheduled")
    if s == "completed" or s == "approved":
        return s
    due = d.get("due_date")
    if due and due < TODAY:
        return "delayed"
    return s


def status_for(client, plan_info=None):
    cstatus = (client.get("status") or "").lower()
    has_active_project = False
    has_any_project = False
    for p in projects_by_client.get(client["id"], []):
        has_any_project = True
        if (p.get("status") or "").lower() in ("active", "in_progress", "planning"):
            has_active_project = True

    # If the legacy projects.json doesn't have a project but a WQA-generated
    # project plan exists on disk (plan_info), treat it as an active project.
    # Bridges file-based plans to the legacy projects.json signal.
    if plan_info and not has_any_project:
        has_any_project = True
        has_active_project = True

    # Check for "needs attention" — at least 1 delayed task
    needs_attention = False
    if plan_info:
        for d in plan_info["plan"]["deliverables"]:
            if default_status(d) == "delayed":
                needs_attention = True
                break

    if cstatus in ("paused", "churned") or not has_any_project:
        return ("inactive", "#ef4444")
    if needs_attention:
        return ("needs_attention", "#ea580c")
    if cstatus == "active" and has_active_project:
        return ("active", "#10b981")
    if cstatus == "onboarding":
        return ("onboarding", "#f59e0b")
    return ("unknown", "#94a3b8")


def derive_service_lines(client):
    """Return the list of service_lines for a client. Backward compatibility:
    if a client has no explicit `custom_fields.service_lines`, synthesize a
    single SEO service line from the legacy top-level fields. This keeps the
    dashboard rendering for pre-multi-service clients without forcing every
    record to be migrated.
    """
    cf = client.get("custom_fields") or {}
    lines = cf.get("service_lines")
    if lines:
        return lines
    # Legacy path — infer one SEO line.
    return [{
        "type": "seo",
        "status": "active",
        "started_at": client.get("contract_start_date"),
        "engagement_months": 12,
        "monthly_retainer": client.get("monthly_retainer"),
        "custom_fields": {
            "ga4_property_id": client.get("ga4_property_id"),
            "gsc_property":    client.get("gsc_property"),
            "content_workbook_id": cf.get("content_workbook_id"),
        },
    }]


# Service-type metadata. Used for labels, stage progression, and per-service
# rendering decisions. PPC/LSA/Social each get their own stage menu so the
# Campaign Stage card reads correctly for the service.
SERVICE_META = {
    "seo": {
        "label": "SEO",
        "color": "#F59E0B",
        "icon": "🔎",
        "stages_by_month": {
            1: "Technical Foundations", 2: "Local SEO", 3: "Content Strategy",
            4: "Content Production", 5: "Content Production", 6: "Content Production",
            7: "Optimization + Iteration", 8: "Optimization + Iteration",
            9: "Optimization + Iteration", 10: "Stabilize + Scale",
            11: "Stabilize + Scale", 12: "Stabilize + Scale",
        },
    },
    "ppc": {
        "label": "PPC",
        "color": "#9333EA",
        "icon": "💰",
        "stages_by_month": {
            1: "Account Setup + Audit", 2: "Campaign Build", 3: "Initial Optimization",
            4: "Scale Winners", 5: "Test + Iterate", 6: "Test + Iterate",
            7: "Test + Iterate", 8: "Test + Iterate", 9: "Test + Iterate",
            10: "Optimize for LTV", 11: "Optimize for LTV", 12: "Annual Review",
        },
    },
    "lsa": {
        "label": "LSA",
        "color": "#0EA5E9",
        "icon": "📞",
        "stages_by_month": {
            1: "Profile Setup + Verification", 2: "Initial Bidding",
            3: "Lead Dispute Cadence", 4: "Optimization", 5: "Optimization",
            6: "Optimization", 7: "Optimization", 8: "Optimization",
            9: "Optimization", 10: "Optimization", 11: "Optimization",
            12: "Optimization",
        },
    },
    "social_ads": {
        "label": "Social Ads",
        "color": "#2563EB",
        "icon": "📱",
        "stages_by_month": {
            1: "Account Audit + Creative Strategy", 2: "Campaign Launch",
            3: "Initial Optimization", 4: "Scale + Iterate", 5: "Scale + Iterate",
            6: "Scale + Iterate", 7: "Refresh Creative", 8: "Scale + Iterate",
            9: "Scale + Iterate", 10: "Refresh Creative", 11: "Scale + Iterate",
            12: "Annual Review",
        },
    },
}


def service_label(service_type):
    return SERVICE_META.get(service_type, {}).get("label", service_type.title())


def service_color(service_type):
    return SERVICE_META.get(service_type, {}).get("color", "#64748B")


def service_icon(service_type):
    return SERVICE_META.get(service_type, {}).get("icon", "•")


def stage_for_service(service_type, month):
    """Return the stage label for a given service-type + month."""
    stages = SERVICE_META.get(service_type, {}).get("stages_by_month", {})
    return stages.get(month, "Ongoing")


client_data = []
for c in clients:
    plan_info = find_project_plan(c)
    status, color = status_for(c, plan_info)
    slug = (plan_info and plan_info["slug"]) or slugify(c.get("company_name", ""))
    client_projects = projects_by_client.get(c["id"], [])
    active_project = next((p for p in client_projects if (p.get("status") or "").lower() in ("active", "planning")), None) or (client_projects[0] if client_projects else None)
    cf_ = (c.get("custom_fields") or {})
    content_cache = (sheets_sync.load_content_workbook_cache(ROOT, slug)
                     if cf_.get("content_workbook_id") else None)
    links_cache   = (sheets_sync.load_link_db_cache(ROOT, slug)
                     if cf_.get("link_db_client_name") else None)
    service_lines = derive_service_lines(c)
    client_data.append({
        "client": c, "slug": slug, "status": status, "color": color,
        "plan_info": plan_info, "projects": client_projects, "active_project": active_project,
        "content_cache": content_cache, "links_cache": links_cache,
        "service_lines": service_lines,
    })


# ============ Task model ============

SPRINT_LABEL = {1: "Sprint 1", 2: "Sprint 2 · Technical", 3: "Sprint 3 · Local",
                4: "Sprint 4 · Content", 5: "Sprint 5 · Links", 6: "Sprint 6 · Reporting"}
SPRINT_COLOR = {1: "#7c3aed", 2: "#2563eb", 3: "#16a34a", 4: "#db2777", 5: "#ea580c", 6: "#64748b"}
# Bucket label (column header value) — friendly name per sprint
BUCKET_LABEL = {1: "Planning", 2: "Technical", 3: "Local", 4: "Content", 5: "Links", 6: "Reporting"}
# Bucket cell background colors (Sheets-style, soft)
BUCKET_BG = {
    1: ("#ede9fe", "#5b21b6"),  # purple
    2: ("#dbeafe", "#1e40af"),  # blue
    3: ("#dcfce7", "#15803d"),  # green
    4: ("#fce7f3", "#9f1239"),  # pink
    5: ("#fed7aa", "#9a3412"),  # orange
    6: ("#e2e8f0", "#475569"),  # slate (reporting — neutral)
}
PRIO_COLOR = {"P1": "#dc2626", "P2": "#ea580c", "P3": "#ca8a04"}
PRIO_ORDER = {"P1": 0, "P2": 1, "P3": 2, "": 9, None: 9}

# Expanded status options — matches the user's spreadsheet metaphor.
# Order matters: this is the display order in the dropdown.
STATUS_OPTIONS = [
    ("scheduled",     "Scheduled",     "#cffafe", "#155e75"),  # cyan — not yet started
    ("assigned",      "Assigned",      "#bfdbfe", "#1e40af"),  # blue — assigned to someone
    ("working",       "Working",       "#fde68a", "#92400e"),  # gold — actively in progress
    ("review_needed", "Review Needed", "#fef08a", "#854d0e"),  # bright yellow
    ("update_needed", "Update Needed", "#fed7aa", "#9a3412"),  # orange
    ("re_assigned",   "Re-Assigned",   "#fbcfe8", "#9f1239"),  # pink
    ("delayed",       "Delayed",       "#fecaca", "#991b1b"),  # light red (auto-derived)
    ("late",          "Late",          "#fca5a5", "#7f1d1d"),  # darker red
    ("approved",      "Approved",      "#bbf7d0", "#14532d"),  # mint
    ("completed",     "Completed",     "#22c55e", "#ffffff"),  # solid green
]
STATUS_LOOKUP = {k: (label, bg, fg) for k, label, bg, fg in STATUS_OPTIONS}
STATUS_KEYS = [k for k, _, _, _ in STATUS_OPTIONS]

# Status set for DELIVERABLES tab (things sent to client)
DELIVERABLE_STATUS_OPTIONS = [
    ("scheduled",       "Scheduled",       "#cffafe", "#155e75"),
    ("waiting_to_send", "Waiting to Send", "#fde68a", "#92400e"),
    ("sent",            "Sent",            "#22c55e", "#ffffff"),
    ("review_needed",   "Review Needed",   "#fef08a", "#854d0e"),
    ("not_completed",   "Not Completed",   "#fecaca", "#991b1b"),
]
DELIVERABLE_STATUS_LOOKUP = {k: (label, bg, fg) for k, label, bg, fg in DELIVERABLE_STATUS_OPTIONS}

# Status set for CONTENT tab (content workflow)
CONTENT_STATUS_OPTIONS = [
    ("ready_for_outline",    "1. Ready for Outline",    "#bfdbfe", "#1e40af"),
    ("ready_for_draft",      "2. Ready for Draft",      "#bfdbfe", "#1e40af"),
    ("draft_being_written",  "3. Draft Being Written",  "#fde68a", "#92400e"),
    ("draft_sent_to_client", "4. Draft Sent to Client", "#a7f3d0", "#065f46"),
    ("waiting_approval",     "5. Waiting Client Approval", "#fde68a", "#92400e"),
    ("editing_draft",        "6. Editing Draft",        "#fed7aa", "#9a3412"),
    ("ready_for_images",     "7. Ready for Images",     "#fed7aa", "#9a3412"),
    ("waiting_to_go_live",   "8. Waiting to go Live",   "#bbf7d0", "#14532d"),
    ("scheduled_to_go_live", "9. Scheduled to go Live", "#bbf7d0", "#14532d"),
    ("content_live",         "10. Content Live",        "#22c55e", "#ffffff"),
    ("update_needed",        "0. Update Needed",        "#fed7aa", "#9a3412"),
    ("rejected",             "z. Rejected",             "#fca5a5", "#7f1d1d"),
]
CONTENT_STATUS_LOOKUP = {k: (label, bg, fg) for k, label, bg, fg in CONTENT_STATUS_OPTIONS}

# Team roster for PEOPLE tab — name, email, title, specialty, monthly task capacity
# monthly_capacity = max tasks/items that person can comfortably own per engagement month.
# Tunable per person. Used by the workload bar to compute utilization.
TEAM_ROSTER = [
    {"email": m["email"], "name": m.get("name", m["email"]),
     "title": m.get("title") or (m.get("role") or "Member").replace("_", " ").title(),
     "skills": m.get("skills") or [],
     "monthly_capacity": m.get("monthly_capacity") or 40}
    for m in team if m.get("active", True) and m.get("email")
] or [
    {"email": "ryan@webris.org",          "name": "Ryan Stewart",   "title": "Owner / Managing Partner",
     "skills": ["Strategy", "Client Relations", "Business Development"],
     "monthly_capacity": 10},
    {"email": "cesar@webris.org",         "name": "Cesar Cobo",     "title": "Head of SEO",
     "skills": ["Technical SEO", "Analytics", "Strategy"],
     "monthly_capacity": 40},
    {"email": "anete@webris.org",         "name": "Anete Lazdina",  "title": "SEO Specialist",
     "skills": ["Technical SEO", "Onpage Optimization"],
     "monthly_capacity": 50},
    {"email": "andrew@webris.org",        "name": "Andrew Sunil",   "title": "SEO Specialist",
     "skills": ["Onpage", "Content QA", "Mixed Skills"],
     "monthly_capacity": 50},
    {"email": "chris.mcdonald@webris.org","name": "Chris McDonald", "title": "Content Lead",
     "skills": ["Content Writing", "Copywriting", "Editorial"],
     "monthly_capacity": 60},
    {"email": "rinor@webris.org",         "name": "Rinor Zeja",     "title": "Link Building Lead",
     "skills": ["Link Building", "Outreach", "Digital PR"],
     "monthly_capacity": 40},
]  # falls back to placeholder roster only if data/team.json has no active members
TEAM_BY_EMAIL = {p["email"]: p for p in TEAM_ROSTER}

PERSON_DISPLAY = {
    "ryan@webris.org": "Ryan Stewart", "cesar@webris.org": "Cesar Cobo",
    "anete@webris.org": "Anete Lazdina", "andrew@webris.org": "Andrew Sunil",
    "chris.mcdonald@webris.org": "Chris McDonald", "rinor@webris.org": "Rinor Zeja",
    "unassigned": "Unassigned",
}


def deliverable_id(client_slug, d, idx):
    """Stable-ish ID for a deliverable, used for localStorage key."""
    src = d.get("source") or {}
    url = src.get("url") or ""
    return f'{client_slug}::{idx}::{(d.get("name") or "")[:40]}'


# ============ Render row + subrow ============

def avatar(email):
    name = PERSON_DISPLAY.get(email, email or "?")
    initial = (name or "?")[0].upper()
    return f'<span class="avatar" title="{esc(name)}">{esc(initial)}</span>'


def format_date_mmddyy(iso):
    """Convert YYYY-MM-DD to MM/DD/YY."""
    if not iso or len(iso) < 10:
        return iso or "—"
    return f"{iso[5:7]}/{iso[8:10]}/{iso[2:4]}"


def deliverable_for(d):
    """Map a task → the client-facing deliverable it rolls up to.

    Sprint 1 kickoff tasks differentiate by action_type so the WQA task
    rolls up to "WQA Report" (the actual artifact: xlsx + HTML report)
    and the Project Plan task rolls up to "Project Plan" (the task-list
    artifact).
    """
    sn = d.get("sprint_number")
    action = ((d.get("source") or {}).get("action_type") or "").lower()
    if sn == 1:
        if "wqa" in action:
            return "WQA Report"
        if "project plan" in action:
            return "Project Plan"
        return "Project Plan & Audit"   # fallback for legacy kickoff items
    if sn == 2:
        return "Technical SEO Matrix"
    if sn == 3:
        return "Local SEO Matrix"
    if sn == 4:
        if "title" in action or "meta" in action:
            return "Title & Meta Matrix"
        return "Published Content"
    if sn == 5:
        return "Live Links"
    if sn == 6:
        if "wqa refresh" in action:
            return "WQA Refresh"
        if "analytics" in action:
            return "Analytics Audit"
        if "check-in" in action or "monthly report" in action:
            return "Client Check-in"
        return "Reporting"
    return "—"


# Pill colors per deliverable type (for chip in Tasks view)
DELIVERABLE_PILL = {
    "WQA Report":            ("#fce7f3", "#9f1239"),   # pink — WQA artifact
    "Project Plan":          ("#ede9fe", "#5b21b6"),   # purple — the plan itself
    "Project Plan & Audit":  ("#ede9fe", "#5b21b6"),
    "Technical SEO Matrix":  ("#dbeafe", "#1e40af"),
    "Local SEO Matrix":      ("#dcfce7", "#15803d"),
    "Title & Meta Matrix":   ("#fce7f3", "#9f1239"),
    "Published Content":     ("#fef3c7", "#854d0e"),
    "WQA Refresh":           ("#fae8ff", "#86198f"),   # magenta — strategic checkpoint
    "Analytics Audit":       ("#cffafe", "#0e7490"),   # teal
    "Client Check-in":       ("#e2e8f0", "#475569"),   # slate — recurring
    "Live Links":            ("#fed7aa", "#9a3412"),
}


def compute_start_date(d):
    """Resolve a deliverable's start date.

    Order of preference:
    1. Explicit `start_date` field on the deliverable (planner writes this
       based on the deliverable's scheduled_month; Month 1 is clamped to the
       project start date so we never pre-date the engagement).
    2. Fallback: due_date - 28 days. Used only for legacy plans built
       before the planner wrote explicit start dates.
    """
    explicit = d.get("start_date")
    if explicit:
        return explicit
    from datetime import date as date_cls, timedelta
    due = d.get("due_date")
    if not due:
        return None
    try:
        return (date_cls.fromisoformat(due) - timedelta(days=28)).isoformat()
    except Exception:
        return None


def date_pill(d, status):
    if not d: return '<span class="date-empty">—</span>'
    is_overdue = (d < TODAY and status not in ("completed", "approved"))
    cls = "date-pill" + (" overdue" if is_overdue else "")
    return f'<span class="{cls}">{esc(format_date_mmddyy(d))}</span>'


def status_pill_editable(initial_status, deliverable_id, is_auto_derived):
    """Render an editable status pill with full options."""
    label, bg, fg = STATUS_LOOKUP.get(initial_status, STATUS_LOOKUP["scheduled"])
    auto = ' data-auto="1"' if is_auto_derived else ''
    return (
        f'<span class="status-pill editable" data-id="{esc(deliverable_id)}" '
        f'data-status="{initial_status}"{auto} style="background:{bg};color:{fg}">'
        f'<span class="pill-label">{label}</span><span class="pill-caret">▾</span></span>'
    )


def render_row(d, client_slug, idx):
    """Render a single flat row for a deliverable."""
    sn = d.get("sprint_number")
    bucket_label = BUCKET_LABEL.get(sn, "—")
    b_bg, b_fg = BUCKET_BG.get(sn, ("#f1f5f9", "#475569"))

    status = default_status(d)
    is_auto = status == "delayed"
    src = d.get("source") or {}
    desc = d.get("description") or ""
    draft = d.get("draft_prompt_hint") or ""
    ai_html = '<span class="ai-tag">✨</span>' if d.get("ai_assisted") else ''

    owner_email = d.get("assigned_to_email") or "unassigned"
    owner_name = PERSON_DISPLAY.get(owner_email, owner_email)
    owner_initial = (owner_name or "?")[0].upper()

    notes_inline_parts = []
    if src.get("url"):
        url_short = src["url"].replace("https://", "").replace("http://", "")
        notes_inline_parts.append(f'<a href="{esc(src["url"])}" target="_blank" onclick="event.stopPropagation()">{esc(url_short[:50])}</a>')
    if desc:
        notes_inline_parts.append(f'<span class="muted">{esc(desc[:50] + "…" if len(desc) > 50 else desc)}</span>')
    notes_inline = " · ".join(notes_inline_parts) or '<span class="date-empty">—</span>'

    expanded_block_parts = []
    if desc:
        expanded_block_parts.append(
            f'<div class="row-detail"><div class="row-detail-label">Description</div><div>{esc(desc)}</div></div>'
        )
    if draft:
        expanded_block_parts.append(
            f'<div class="row-detail"><div class="row-detail-label">Draft prompt (for Claude)</div><div class="sub-prompt">{esc(draft)}</div></div>'
        )
    if src.get("url"):
        expanded_block_parts.append(
            f'<div class="row-detail"><div class="row-detail-label">Attachment / link</div>'
            f'<a href="{esc(src["url"])}" target="_blank">{esc(src["url"])}</a></div>'
        )

    did = deliverable_id(client_slug, d, idx)
    due_date = d.get("due_date") or ""
    start_date = compute_start_date(d) or ""
    sort_due = due_date or "9999-99-99"
    sort_start = start_date or "9999-99-99"
    deliv_name = deliverable_for(d)
    d_bg, d_fg = DELIVERABLE_PILL.get(deliv_name, ("#f1f5f9", "#475569"))

    # Monthly report rows get a special class so they render as a gray
    # visual month-break in the Tasks tab.
    row_extra_class = " row-monthly-report" if d.get("is_monthly_report") else ""

    return (
        f'<details class="row{row_extra_class}" '
        f'data-status="{status}" data-assignee="{esc(owner_email)}" '
        f'data-sprint="{sn}" data-ai="{"1" if d.get("ai_assisted") else "0"}" '
        f'data-due="{sort_due}" data-start="{sort_start}" '
        f'data-deliverable="{esc(deliv_name)}" '
        f'data-name="{esc((d.get("name") or "").lower())}" '
        f'data-search="{esc((d.get("name") or "").lower() + " " + desc.lower())}">'
          f'<summary>'
            f'<div class="cell cell-start"><input type="date" class="date-edit" data-id="{esc(did)}" data-field="start" value="{esc(start_date)}" title="Editable — saved in your browser" onclick="event.stopPropagation()"></div>'
            f'<div class="cell cell-due"><input type="date" class="date-edit{" overdue" if (due_date and due_date < TODAY and status not in ("completed", "approved")) else ""}" data-id="{esc(did)}" data-field="due" value="{esc(due_date)}" title="Editable — saved in your browser" onclick="event.stopPropagation()"></div>'
            f'<div class="cell cell-status">{status_pill_editable(status, did, is_auto)}</div>'
            f'<div class="cell cell-owner"><span class="avatar" title="{esc(owner_name)}">{esc(owner_initial)}</span><span class="owner-name">{esc(owner_name.split()[0] if owner_name else "—")}</span></div>'
            f'<div class="cell cell-bucket"><span class="bucket-pill" style="background:{b_bg};color:{b_fg}">{esc(bucket_label)}</span></div>'
            f'<div class="cell cell-task">{ai_html}<span class="row-name">{esc(d.get("name") or "")}</span></div>'
            f'<div class="cell cell-deliverable"><span class="deliverable-pill" style="background:{d_bg};color:{d_fg}">{esc(deliv_name)}</span></div>'
            f'<div class="cell cell-notes">{notes_inline}</div>'
          f'</summary>'
          f'<div class="row-body">'
            + "".join(expanded_block_parts) +
          f'</div>'
        f'</details>'
    )


# ============ Render the per-client view ============

def render_client_view(cd):
    client = cd["client"]
    plan_info = cd["plan_info"]
    company = client.get("company_name", "")
    slug = cd["slug"]

    if not plan_info:
        return (
            '<div class="empty-state">'
              '<h2 style="font-family:var(--display);font-size:36px;text-transform:uppercase;font-weight:400;margin:0 0 12px;">' + esc(company) + '</h2>'
              '<div class="empty-msg">'
                '<div class="empty-icon">📋</div>'
                '<h3>No project plan yet</h3>'
                '<p>Once you run <code>/bpt-website-quality-audit</code> followed by <code>/bpt-project-plan</code> for this client, the plan will appear here automatically.</p>'
              '</div>'
            '</div>'
        )

    plan = plan_info["plan"]
    project = plan["project"]
    deliverables = plan["deliverables"]

    # Sort deliverables by due_date (chronological cascade)
    sorted_deliverables = sorted(
        deliverables,
        key=lambda d: d.get("due_date") or "9999-99-99"
    )

    # Hero
    hero = (
        '<header class="client-hero">'
          '<div class="sub">Project Dashboard</div>'
          '<h2>' + esc(company) + '</h2>'
          '<div class="meta">' + esc(project.get("name", "")) + ' · ' + esc(format_date_mmddyy(project.get("start_date", ""))) + ' → ' + esc(format_date_mmddyy(project.get("target_end_date", ""))) + '</div>'
        '</header>'
    )

    # KPI strip
    total = len(deliverables)
    ai_count = sum(1 for d in deliverables if d.get("ai_assisted"))
    delayed_count = sum(1 for d in deliverables if default_status(d) == "delayed")
    completed_count = sum(1 for d in deliverables if default_status(d) in ("completed", "approved"))
    kpi_strip = (
        '<div class="kpi-grid">'
          '<div class="kpi"><div class="kpi-label">Deliverables</div><div class="kpi-value">' + str(total) + '</div></div>'
          '<div class="kpi"><div class="kpi-label">Delayed</div><div class="kpi-value" style="color:#dc2626">' + str(delayed_count) + '</div><div class="kpi-sub">past due date</div></div>'
          '<div class="kpi"><div class="kpi-label">Completed</div><div class="kpi-value" style="color:#16a34a">' + str(completed_count) + '</div></div>'
          '<div class="kpi"><div class="kpi-label">AI-assisted</div><div class="kpi-value">' + str(ai_count) + '</div><div class="kpi-sub">drafted by Claude</div></div>'
        '</div>'
    )

    # View tabs (5 tabs) — Reporting lives on its own top-level page, not here
    tabs_html = (
        f'<div class="view-tabs" data-client="{esc(slug)}">'
          f'<button class="view-tab active" data-view="tasks">Tasks</button>'
          f'<button class="view-tab" data-view="timeline">Timeline</button>'
          f'<button class="view-tab" data-view="deliverables">Deliverables</button>'
          f'<button class="view-tab" data-view="people">People</button>'
          f'<button class="view-tab" data-view="content">Content</button>'
          f'<button class="view-tab" data-view="links">Links</button>'
        f'</div>'
    )

    # Filters (sprint, assignee, status, ai, search)
    assignee_options = ''.join(f'<option value="{esc(e)}">{esc(PERSON_DISPLAY.get(e, e))}</option>'
                               for e in PERSON_DISPLAY if e != "unassigned")
    status_options = ''.join(f'<option value="{esc(k)}">{esc(label)}</option>' for k, label, _, _ in STATUS_OPTIONS)
    filters_html = (
        f'<div class="filters" data-client="{esc(slug)}">'
          f'<label>Filter:</label>'
          f'<select class="f-sprint"><option value="">All buckets</option>'
            f'<option value="2">Technical</option>'
            f'<option value="3">Local</option>'
            f'<option value="4">Content</option>'
            f'<option value="5">Links</option>'
            f'<option value="6">Reporting</option></select>'
          f'<select class="f-assignee"><option value="">All owners</option>{assignee_options}</select>'
          f'<select class="f-status"><option value="">All statuses</option>{status_options}</select>'
          f'<span class="filter-pill f-ai" data-active="0">✨ AI-assisted only</span>'
          f'<input type="text" class="f-search" placeholder="Search…" style="margin-left:auto;width:240px;">'
        f'</div>'
    )

    # Table header (sortable columns with resize handles)
    # Order: Start · Due · Status · Owner · Bucket · Task · Deliverable · Notes (flex)
    table_header = (
        '<div class="table-header">'
          '<div class="cell cell-start sortable" data-sort="start">Start <span class="sort-ind"></span><span class="resize-handle" data-col="start"></span></div>'
          '<div class="cell cell-due sortable" data-sort="due">Due <span class="sort-ind"></span><span class="resize-handle" data-col="due"></span></div>'
          '<div class="cell cell-status sortable" data-sort="status">Status <span class="sort-ind"></span><span class="resize-handle" data-col="status"></span></div>'
          '<div class="cell cell-owner sortable" data-sort="owner">Owner <span class="sort-ind"></span><span class="resize-handle" data-col="owner"></span></div>'
          '<div class="cell cell-bucket sortable" data-sort="bucket">Bucket <span class="sort-ind"></span><span class="resize-handle" data-col="bucket"></span></div>'
          '<div class="cell cell-task sortable" data-sort="task">Task <span class="sort-ind"></span><span class="resize-handle" data-col="task"></span></div>'
          '<div class="cell cell-deliverable sortable" data-sort="deliverable">Deliverable <span class="sort-ind"></span><span class="resize-handle" data-col="deliverable"></span></div>'
          '<div class="cell cell-notes">Notes</div>'
        '</div>'
    )

    # ----- Generate a single generic CSV export for this client's plan -----
    # One CSV with every field exposed — customer maps columns when
    # importing to ClickUp / Asana / Monday / whatever. The multi-format
    # exporters (ClickUp-specific column names, Monday XLSX, etc.) are
    # still available via the export_project_plan.py CLI for anyone who
    # wants tool-native formatting, but the dashboard surfaces just one
    # button since the column differences are minor.
    exports_dir = os.path.join(ROOT, "exports", "project-plans")
    os.makedirs(exports_dir, exist_ok=True)
    export_path = None
    plan_for_export = cd.get("plan_info", {}).get("plan") if cd.get("plan_info") else None
    if plan_for_export:
        try:
            import importlib.util
            _spec = importlib.util.spec_from_file_location(
                "export_project_plan",
                os.path.join(os.path.dirname(__file__), "export_project_plan.py"),
            )
            _exp = importlib.util.module_from_spec(_spec)
            _spec.loader.exec_module(_exp)
            fname = f"{slug}-tasks.csv"
            fpath = os.path.join(exports_dir, fname)
            try:
                _exp.export_generic(plan_for_export, fpath)
                export_path = os.path.relpath(fpath, ROOT)
            except Exception as e:
                print(f"  ⚠ Export failed for {slug}: {e!r}")
        except Exception as e:
            print(f"  ⚠ Could not load export_project_plan.py: {e!r}")

    # ----- Export button — top of Tasks view -----
    # Single button. Downloads the generic CSV with every field exposed.
    # The customer maps columns when importing to ClickUp / Asana / Monday
    # / any tool. Power users wanting tool-native CSV formatting can run
    # `python3 scripts/export_project_plan.py --format clickup` (or asana
    # / monday) from the CLI.
    if export_path:
        export_strip = (
            f'<div class="task-export-strip">'
              f'<a class="export-btn" href="{esc(export_path)}" download '
              f'title="Download a CSV of every task in this plan. Import into ClickUp, Asana, Monday, or any PM tool — map columns during import.">'
                f'<span class="export-btn-icon">↓</span>'
                f'<span class="export-btn-label">Export Tasks</span>'
                f'<span class="export-btn-ext">.csv</span>'
              f'</a>'
              f'<span class="task-export-hint">Import to ClickUp · Asana · Monday · or any PM tool</span>'
            f'</div>'
        )
    else:
        export_strip = (
            '<div class="task-export-strip">'
              '<span class="export-btn export-btn-disabled" title="No project plan yet — run the WQA workflow first">'
                '<span class="export-btn-icon">↓</span>'
                '<span class="export-btn-label">Export Tasks</span>'
                '<span class="export-btn-ext">unavailable</span>'
              '</span>'
              '<span class="task-export-hint">No project plan yet — run the WQA workflow first</span>'
            '</div>'
        )

    # ----- TASKS VIEW (flat cascading list, sorted by due date) -----
    tasks_view = ['<div class="view active" data-view="tasks">', export_strip, '<div class="task-table">', table_header]
    tasks_view.append('<div class="flat-body">')
    for i, d in enumerate(sorted_deliverables):
        tasks_view.append(render_row(d, slug, i))
    tasks_view.append('</div></div></div>')

    # ----- TIMELINE VIEW (Gantt) -----
    project_start = project.get("start_date") or TODAY
    project_end   = project.get("target_end_date") or TODAY
    timeline_view = render_gantt_view(slug, sorted_deliverables, project_start, project_end)

    # ----- DELIVERABLES VIEW (things sent to client) -----
    deliverables_view = render_deliverables_view(slug, sorted_deliverables)

    # ----- PEOPLE VIEW (team cards w/ current work) -----
    people_view = render_people_view(slug, sorted_deliverables)

    # ----- CONTENT VIEW (reads from content workbook cache; sheet is SoT) -----
    content_view = render_content_view(slug, cd.get("content_cache"), client)

    # ----- LINKS VIEW (reads from central link DB cache; sheet is SoT) -----
    links_view = render_links_view(slug, cd.get("links_cache"), client)

    return (hero + kpi_strip + tabs_html + filters_html
            + "\n".join(tasks_view) + timeline_view + deliverables_view + people_view
            + content_view + links_view)


# ============ REPORTING VIEW ============

def mock_series(slug, n, base, key=""):
    """Deterministic growing time series with seasonal-ish noise."""
    import hashlib
    h = int(hashlib.md5((slug + key).encode()).hexdigest()[:16], 16)
    out = []
    for i in range(n):
        seed_noise = ((h >> (i * 3)) & 0xFFF) / 4095.0  # 0-1
        growth = 1 + 0.025 * i  # +2.5% per period
        out.append(int(max(10, base * growth * (0.75 + 0.55 * seed_noise))))
    return out


def load_series(slug, key, *_args, **_kw):
    """Load a real time series from clients/{slug}/analytics/{key}.json if present.

    Cache file format: {"labels": [...], "data": [...], "source": "...", "pulled_at": "..."}

    Returns (data, labels, source) — all None if cache file missing (no fallback).
    """
    cache = os.path.join(ROOT, "clients", slug, "analytics", f"{key}.json")
    if os.path.exists(cache):
        try:
            payload = json.load(open(cache))
            return (payload.get("data") or [],
                    payload.get("labels"),
                    payload.get("source") or "cached")
        except Exception:
            pass
    return None, None, None


def pct_change(cur, prev):
    if not prev: return 0.0
    return ((cur - prev) / prev) * 100


def render_kpi_card(label, value, delta_pct=None, delta_label="vs last period", suffix=""):
    delta_html = ""
    if delta_pct is not None:
        arrow = "▲" if delta_pct >= 0 else "▼"
        sign = "+" if delta_pct >= 0 else ""
        color = "#16a34a" if delta_pct >= 0 else "#dc2626"
        delta_html = (f'<div class="rep-kpi-delta" style="color:{color}">'
                      f'{arrow} {sign}{delta_pct:.1f}% '
                      f'<span class="rep-kpi-delta-label">{esc(delta_label)}</span></div>')
    return (f'<div class="rep-kpi">'
              f'<div class="rep-kpi-label">{esc(label)}</div>'
              f'<div class="rep-kpi-value">{value}{esc(suffix)}</div>'
              f'{delta_html}'
            f'</div>')


def render_reporting_view(cd, deliverables):
    """Full SEO report view for one client."""
    slug = cd["slug"]
    client = cd["client"]
    company = client.get("company_name", "")
    website = client.get("website", "—")

    # Account ID wiring (from data/clients.json)
    ga4_id = client.get("ga4_property_id") or "—"
    gsc_prop = client.get("gsc_property") or "—"
    cf = client.get("custom_fields") or {}
    gmb_id = cf.get("gmb_location_id") or "—"
    has_ga4 = ga4_id != "—"
    has_gsc = gsc_prop != "—"
    has_gmb = gmb_id != "—"

    # Load real data — when missing, the series is None and the section renders
    # as a "Not Connected" empty state (NO mock data).
    organic_24m, organic_labels, organic_src = load_series(slug, "ga4_organic_monthly_24m")
    gsc_clicks_12w, gsc_clicks_labels, gsc_clicks_src = load_series(slug, "gsc_clicks_weekly_12w")
    gsc_impr_12w, gsc_impr_labels, gsc_impr_src = load_series(slug, "gsc_impressions_weekly_12w")
    conv_12m, conv_labels, conv_src = load_series(slug, "ga4_conversions_monthly_12m")
    gbp_impr_12m, gbp_impr_labels, gbp_impr_src = load_series(slug, "gbp_impressions_monthly_12m")
    gbp_calls_12m, gbp_calls_labels, gbp_calls_src = load_series(slug, "gbp_calls_monthly_12m")
    gbp_clicks_12m, gbp_clicks_labels, gbp_clicks_src = load_series(slug, "gbp_clicks_monthly_12m")
    gbp_reviews_12m, gbp_reviews_labels, gbp_reviews_src = load_series(slug, "gbp_reviews_monthly_12m")

    # Call tracking (CallRail / WhatConverts). Two possible series:
    #   - total tracked calls per month
    #   - calls flagged as conversions / qualified
    # Source is determined per-client by which connector is configured in
    # the client's custom_fields (callrail_company_id or whatconverts_account_id).
    ct_calls_12m, ct_calls_labels, ct_calls_src = load_series(slug, "call_tracking_calls_monthly_12m")
    ct_conv_12m,  ct_conv_labels,  ct_conv_src  = load_series(slug, "call_tracking_conversions_monthly_12m")
    callrail_id     = cf.get("callrail_company_id")
    whatconverts_id = cf.get("whatconverts_account_id")
    has_call_tracking_config = bool(callrail_id or whatconverts_id)
    ct_provider = "CallRail" if callrail_id else ("WhatConverts" if whatconverts_id else None)

    live_sections = [s for s in [organic_src, gsc_clicks_src, gsc_impr_src, conv_src,
                                  gbp_impr_src, gbp_calls_src, gbp_clicks_src, gbp_reviews_src,
                                  ct_calls_src, ct_conv_src] if s]
    not_connected_count = 10 - len(live_sections)
    any_real = len(live_sections) > 0

    NC_ACTION = {
        "ga4": "Wire up Google Analytics 4 via Windsor.ai (account-filter fix needed)",
        "gsc": "Wire up Search Console via Ahrefs project or Windsor.ai",
        "gbp": "Wire up Google Business Profile via Windsor.ai or GBP API",
        "call_tracking_config":
            "No call-tracking connector configured. Add callrail_company_id "
            "(CallRail) or whatconverts_account_id (WhatConverts) to this "
            "client's custom_fields in data/clients.json, then re-run the "
            "analytics pull.",
        "call_tracking_data":
            "Call-tracking connector configured but no data cached yet. "
            "Run the analytics pull to fetch call-tracking history.",
        "content_perf": "Needs GSC per-URL impressions history (Ahrefs gsc-page-history or windsor_query gsc by page)",
        "link_perf":    "Needs GSC per-URL impressions history (same source as Content Performance)",
    }
    def not_connected_block(action):
        return (f'<div class="rep-not-connected">'
                f'<div class="rep-nc-badge">⊘ NOT CONNECTED</div>'
                f'<div class="rep-nc-action">Action: {esc(action)}</div>'
                f'</div>')

    # Section 1: Organic Traffic
    if organic_24m and len(organic_24m) >= 2:
        org_now = organic_24m[-1]
        org_mom_prev = organic_24m[-2]
        org_yoy_prev = organic_24m[-13] if len(organic_24m) >= 13 else None
        s1_kpis = "".join([
            render_kpi_card("Organic visits (last month)", f"{org_now:,}",
                             pct_change(org_now, org_mom_prev), "MoM"),
            render_kpi_card("Year-over-year", f"{org_now:,}",
                             pct_change(org_now, org_yoy_prev) if org_yoy_prev else None, "YoY"),
            render_kpi_card(f"{len(organic_24m)}-month total", f"{sum(organic_24m):,}", None, ""),
        ])
        s1_chart = f'<div class="rep-chart-card"><canvas class="rep-chart" data-chart-id="{esc(slug)}-organic" data-chart-key="organic_24m"></canvas></div>'
        s1_html = f'<div class="rep-kpi-row">{s1_kpis}</div>{s1_chart}'
    else:
        s1_html = not_connected_block(NC_ACTION["ga4"])

    # Section 2: GSC Performance (WoW)
    if gsc_clicks_12w and gsc_impr_12w and len(gsc_clicks_12w) >= 2:
        gsc_clicks_now = gsc_clicks_12w[-1]; gsc_clicks_prev = gsc_clicks_12w[-2]
        gsc_impr_now = gsc_impr_12w[-1]; gsc_impr_prev = gsc_impr_12w[-2]
        s2_kpis = "".join([
            render_kpi_card("Clicks (this week)", f"{gsc_clicks_now:,}",
                             pct_change(gsc_clicks_now, gsc_clicks_prev), "WoW"),
            render_kpi_card("Impressions (this week)", f"{gsc_impr_now:,}",
                             pct_change(gsc_impr_now, gsc_impr_prev), "WoW"),
            render_kpi_card("Avg CTR", f"{100*gsc_clicks_now/max(1,gsc_impr_now):.2f}",
                             None, "", suffix="%"),
        ])
        s2_charts = (f'<div class="rep-chart-grid">'
                     f'<div class="rep-chart-card"><div class="rep-chart-label">Clicks · 12-week trend</div><canvas class="rep-chart" data-chart-id="{esc(slug)}-gsc-clicks" data-chart-key="gsc_clicks_12w"></canvas></div>'
                     f'<div class="rep-chart-card"><div class="rep-chart-label">Impressions · 12-week trend</div><canvas class="rep-chart" data-chart-id="{esc(slug)}-gsc-impr" data-chart-key="gsc_impr_12w"></canvas></div>'
                     f'</div>')
        s2_html = f'<div class="rep-kpi-row">{s2_kpis}</div>{s2_charts}'
    else:
        s2_html = not_connected_block(NC_ACTION["gsc"])

    # Section 3: Conversions
    if conv_12m and len(conv_12m) >= 2:
        conv_now = conv_12m[-1]; conv_mom_prev = conv_12m[-2]
        conv_yoy_prev = conv_12m[0] if len(conv_12m) >= 12 else None
        s3_kpis = "".join([
            render_kpi_card("Conversions (last month)", f"{conv_now:,}",
                             pct_change(conv_now, conv_mom_prev), "MoM"),
            render_kpi_card("Year-over-year", f"{conv_now:,}",
                             pct_change(conv_now, conv_yoy_prev) if conv_yoy_prev else None, "YoY"),
            render_kpi_card("12-month total", f"{sum(conv_12m):,}", None, ""),
        ])
        s3_chart = f'<div class="rep-chart-card"><canvas class="rep-chart" data-chart-id="{esc(slug)}-conv" data-chart-key="conv_12m" data-chart-type="bar"></canvas></div>'
        s3_html = f'<div class="rep-kpi-row">{s3_kpis}</div>{s3_chart}'
    else:
        s3_html = not_connected_block(NC_ACTION["ga4"] + " (filter to medium=organic for conversions)")

    # Section 4: Google Business Profile — render what's available, mark missing as N/A
    gbp_has_any = any([gbp_impr_12m, gbp_calls_12m, gbp_clicks_12m, gbp_reviews_12m])
    if gbp_has_any:
        kpi_parts = []
        chart_parts = []
        # Profile impressions
        if gbp_impr_12m and len(gbp_impr_12m) >= 2:
            kpi_parts.append(render_kpi_card("Profile impressions", f"{gbp_impr_12m[-1]:,}",
                              pct_change(gbp_impr_12m[-1], gbp_impr_12m[-2]), "MoM"))
            chart_parts.append(f'<div class="rep-chart-card"><div class="rep-chart-label">Profile impressions · 12 months</div><canvas class="rep-chart" data-chart-id="{esc(slug)}-gbp-impr" data-chart-key="gbp_impr_12m"></canvas></div>')
        else:
            kpi_parts.append(render_kpi_card("Profile impressions", "—", None, "(not connected)"))
        # Phone calls — not currently exposed by windsor GBP connector
        if gbp_calls_12m and len(gbp_calls_12m) >= 2:
            kpi_parts.append(render_kpi_card("Phone calls", f"{gbp_calls_12m[-1]:,}",
                              pct_change(gbp_calls_12m[-1], gbp_calls_12m[-2]), "MoM"))
            chart_parts.append(f'<div class="rep-chart-card"><div class="rep-chart-label">Phone calls · 12 months</div><canvas class="rep-chart" data-chart-id="{esc(slug)}-gbp-calls" data-chart-key="gbp_calls_12m"></canvas></div>')
        else:
            kpi_parts.append(render_kpi_card("Phone calls", "—", None, "(not exposed by Windsor GBP)"))
        # Website clicks
        if gbp_clicks_12m and len(gbp_clicks_12m) >= 2:
            kpi_parts.append(render_kpi_card("Website clicks", f"{gbp_clicks_12m[-1]:,}",
                              pct_change(gbp_clicks_12m[-1], gbp_clicks_12m[-2]), "MoM"))
            chart_parts.append(f'<div class="rep-chart-card"><div class="rep-chart-label">Website clicks · 12 months</div><canvas class="rep-chart" data-chart-id="{esc(slug)}-gbp-clicks" data-chart-key="gbp_clicks_12m"></canvas></div>')
        else:
            kpi_parts.append(render_kpi_card("Website clicks", "—", None, "(not connected)"))
        # New reviews
        if gbp_reviews_12m and len(gbp_reviews_12m) >= 2:
            kpi_parts.append(render_kpi_card("New reviews", f"{gbp_reviews_12m[-1]:,}",
                              pct_change(gbp_reviews_12m[-1], max(1, gbp_reviews_12m[-2])), "MoM"))
        else:
            kpi_parts.append(render_kpi_card("New reviews", "—", None, "(not exposed by Windsor GBP)"))
        s4_html = f'<div class="rep-kpi-row rep-kpi-row-4">{"".join(kpi_parts)}</div>'
        if chart_parts:
            s4_html += f'<div class="rep-chart-grid">{"".join(chart_parts)}</div>'
    elif has_gmb:
        s4_html = not_connected_block(NC_ACTION["gbp"])
    else:
        s4_html = (f'<div class="rep-not-connected">'
                   f'<div class="rep-nc-badge" style="background:#94a3b8">N/A</div>'
                   f'<div class="rep-nc-action">No Google Business Profile linked to this client.</div>'
                   f'</div>')

    # Section 5: Call Tracking (CallRail or WhatConverts).
    # Three possible states:
    #   1. No connector configured → loud "Not Connected" alert with action
    #   2. Connector configured but no data cached → softer "Pending data" alert
    #   3. Data present → KPI row + 12-month trend chart
    if ct_calls_12m and len(ct_calls_12m) >= 2:
        ct_now = ct_calls_12m[-1]
        ct_prev = ct_calls_12m[-2]
        ct_yoy = ct_calls_12m[0] if len(ct_calls_12m) >= 12 else None
        ct_kpis = [
            render_kpi_card("Calls (last month)", f"{ct_now:,}", pct_change(ct_now, ct_prev), "MoM"),
            render_kpi_card("Year-over-year", f"{ct_now:,}",
                             pct_change(ct_now, ct_yoy) if ct_yoy else None, "YoY"),
            render_kpi_card("12-month total", f"{sum(ct_calls_12m):,}", None, ""),
        ]
        if ct_conv_12m and len(ct_conv_12m) >= 1:
            conv_now_ct = ct_conv_12m[-1]
            ct_kpis.append(render_kpi_card("Qualified calls", f"{conv_now_ct:,}", None,
                                             f"{100*conv_now_ct/max(1,ct_now):.0f}% qualify rate"))
        ct_chart_parts = [
            f'<div class="rep-chart-card"><div class="rep-chart-label">Calls · 12 months</div>'
            f'<canvas class="rep-chart" data-chart-id="{esc(slug)}-ct-calls" data-chart-key="call_tracking_12m"></canvas></div>'
        ]
        if ct_conv_12m:
            ct_chart_parts.append(
                f'<div class="rep-chart-card"><div class="rep-chart-label">Qualified calls · 12 months</div>'
                f'<canvas class="rep-chart" data-chart-id="{esc(slug)}-ct-conv" data-chart-key="call_tracking_conv_12m" data-chart-type="bar"></canvas></div>'
            )
        s_calltrack_html = (
            f'<div class="rep-kpi-row rep-kpi-row-4">{"".join(ct_kpis)}</div>'
            f'<div class="rep-chart-grid">{"".join(ct_chart_parts)}</div>'
        )
        ct_source_label = f'{ct_provider}' if ct_provider else 'Call tracking'
    elif has_call_tracking_config:
        # Configured but no data
        s_calltrack_html = (
            f'<div class="rep-not-connected" style="background:#fef3c7;border-color:#fcd34d;color:#92400e">'
              f'<div class="rep-nc-badge" style="background:#d97706">⚠ PENDING DATA</div>'
              f'<div class="rep-nc-action">{esc(ct_provider or "Call tracking")} '
              f'connector is configured but no call history is cached yet. '
              f'{esc(NC_ACTION["call_tracking_data"])}</div>'
            f'</div>'
        )
        ct_source_label = ct_provider or 'Call tracking'
    else:
        # No connector at all → loud not-connected alert
        s_calltrack_html = (
            f'<div class="rep-not-connected">'
              f'<div class="rep-nc-badge">⊘ NOT CONNECTED</div>'
              f'<div class="rep-nc-action">{esc(NC_ACTION["call_tracking_config"])}</div>'
            f'</div>'
        )
        ct_source_label = 'CallRail · WhatConverts'

    # Sections 6 + 7: Content + Link Performance — read per-URL comparison from cache
    page_perf_cache = os.path.join(ROOT, "clients", slug, "analytics", "page_performance_90d_vs_prior.json")
    page_perf = None
    if os.path.exists(page_perf_cache):
        try: page_perf = json.load(open(page_perf_cache))
        except Exception: page_perf = None

    def render_page_perf_table(filter_urls=None, max_rows=30):
        """Render per-URL impressions comparison table."""
        if not page_perf:
            return None
        pages = page_perf["pages"]
        if filter_urls:
            keep = set(filter_urls)
            pages = [p for p in pages if p["url"] in keep or any(p["url"].startswith(u) for u in keep)]
        pages = pages[:max_rows]
        if not pages:
            return None
        rows = []
        for p in pages:
            cur = p["current_impressions"]; pri = p["prior_impressions"]
            delta = pct_change(cur, pri) if pri else (100.0 if cur else 0.0)
            color = "#16a34a" if delta >= 0 else "#dc2626"
            sign = "+" if delta >= 0 else ""
            short = p["url"].replace("https://", "").replace("http://", "")
            rows.append(
                f'<tr><td><div class="rep-page"><a href="{esc(p["url"])}" target="_blank">{esc(short[:90])}</a></div></td>'
                f'<td class="num">{cur:,}</td><td class="num">{pri:,}</td>'
                f'<td class="num" style="color:{color};font-weight:700;">{sign}{delta:.1f}%</td></tr>'
            )
        return (
            '<table class="rep-perf-table"><thead><tr>'
              '<th>Page</th><th class="num">Impressions (last 90d)</th>'
              '<th class="num">Prior 90d</th><th class="num">Δ</th>'
            '</tr></thead><tbody>' + "".join(rows) + '</tbody></table>'
            + f'<div class="muted" style="font-size:11px;margin-top:6px;">'
              f'{esc(page_perf["current_period"])} vs {esc(page_perf["prior_period"])} · '
              f'Source: {esc(page_perf["source"])}</div>'
        )

    # Sections 5 + 6: Content Performance + Link Performance.
    #
    # Design (June 2026): these sections track LIVE artifacts only. Content
    # Performance is the GSC trend on pages that have shipped (Live status in
    # the content workbook). Link Performance is the GSC trend on target
    # pages that have an acquired link (8. Live in the central link DB).
    #
    # Pre-production state (no live content / no live links yet) shows a
    # clear "waiting on production" notice rather than misleading data
    # filtered by planned-but-not-shipped URLs.

    content_cache = cd.get("content_cache") or {}
    links_cache   = cd.get("links_cache") or {}

    live_content_urls = []
    for r in (content_cache.get("rows") or []):
        if sheets_sync.is_content_live(r):
            url = (r.get("published_url") or "").strip()
            if url:
                live_content_urls.append(url)

    live_link_target_urls = []
    for r in (links_cache.get("rows") or []):
        if sheets_sync.is_link_live(r):
            url = (r.get("target_page") or "").strip()
            if url:
                live_link_target_urls.append(url)

    def _waiting_notice(kind_label, what_unblocks):
        """Render a clear 'waiting on production' panel for Content / Link Performance."""
        return (
            f'<div class="rep-not-connected" style="background:#f0f9ff;border-color:#bae6fd;color:#075985">'
              f'<div class="rep-nc-badge" style="background:#0284c7">⏳ Waiting</div>'
              f'<div class="rep-nc-action"><strong>{esc(kind_label)} will populate as {esc(what_unblocks)}.</strong> '
              f'This section tracks GSC trends for the specific URLs that have shipped during the engagement — '
              f'so it stays empty until that work goes live, then fills in row by row.</div>'
            f'</div>'
        )

    # Section 5: Content Performance — only show data once content is live.
    if live_content_urls and page_perf:
        s5_table = render_page_perf_table(filter_urls=live_content_urls, max_rows=30)
        s5_html = s5_table or _waiting_notice("Content performance", "the team ships content")
    else:
        s5_html = _waiting_notice("Content performance", "the team ships content")

    # Section 6: Link Performance — only show data once links are built.
    if live_link_target_urls and page_perf:
        s6_table = render_page_perf_table(filter_urls=live_link_target_urls, max_rows=30)
        s6_html = s6_table or _waiting_notice("Link performance", "the team builds links")
    else:
        s6_html = _waiting_notice("Link performance", "the team builds links")

    # Account for sections 5 + 6 in the disclaimer — they're "waiting" (not
    # "not connected") so they shouldn't count as failures, but they're not
    # "live" either until the production work flows through.
    if page_perf and (live_content_urls or live_link_target_urls):
        live_sections.append(page_perf["source"])
        not_connected_count = max(0, not_connected_count - 2)
        any_real = True

    # Chart data — emit as JSON for the per-client init
    from datetime import date as date_cls, timedelta
    today = date_cls.today()
    def labels_months(n):
        out = []
        for i in range(n):
            d = today.replace(day=1)
            for _ in range(n - 1 - i):
                d = (d - timedelta(days=1)).replace(day=1)
            out.append(d.strftime("%b '%y"))
        return out
    def labels_weeks(n):
        return [f"W{n - i}" for i in range(n)][::-1]

    # Per-section color palette. Each chart series gets a color matching
    # its parent section so the Reporting tab reads as visually grouped:
    #   Section 1 Organic         → blue
    #   Section 2 Search Console  → orange
    #   Section 3 Conversions     → green
    #   Section 4 GBP             → purple
    #   Section 5 Call Tracking   → teal
    SECTION_COLOR = {
        "organic_24m":     "#F59E0B",  # orange — Section 1 (GA4 organic = SEO color)
        "gsc_clicks_12w":  "#2563EB",  # blue   — Section 2 (Search Console)
        "gsc_impr_12w":    "#2563EB",  # blue   — Section 2
        "conv_12m":        "#16A34A",  # green  — Section 3
        "gbp_impr_12m":    "#9333EA",  # purple — Section 4
        "gbp_calls_12m":   "#9333EA",  # purple — Section 4
        "gbp_clicks_12m":  "#9333EA",  # purple — Section 4
        "call_tracking_12m":   "#0D9488",  # teal — Section 5
        "call_tracking_conv_12m": "#0D9488",  # teal — Section 5
    }

    chart_payload = {}
    if organic_24m:
        chart_payload["organic_24m"] = {"labels": organic_labels or labels_months(len(organic_24m)), "data": organic_24m, "color": SECTION_COLOR["organic_24m"]}
    if gsc_clicks_12w:
        chart_payload["gsc_clicks_12w"] = {"labels": gsc_clicks_labels or labels_weeks(len(gsc_clicks_12w)), "data": gsc_clicks_12w, "color": SECTION_COLOR["gsc_clicks_12w"]}
    if gsc_impr_12w:
        chart_payload["gsc_impr_12w"] = {"labels": gsc_impr_labels or labels_weeks(len(gsc_impr_12w)), "data": gsc_impr_12w, "color": SECTION_COLOR["gsc_impr_12w"]}
    if conv_12m:
        chart_payload["conv_12m"] = {"labels": conv_labels or labels_months(len(conv_12m)), "data": conv_12m, "color": SECTION_COLOR["conv_12m"]}
    if gbp_impr_12m:
        chart_payload["gbp_impr_12m"] = {"labels": gbp_impr_labels or labels_months(len(gbp_impr_12m)), "data": gbp_impr_12m, "color": SECTION_COLOR["gbp_impr_12m"]}
    if gbp_calls_12m:
        chart_payload["gbp_calls_12m"] = {"labels": gbp_calls_labels or labels_months(len(gbp_calls_12m)), "data": gbp_calls_12m, "color": SECTION_COLOR["gbp_calls_12m"]}
    if gbp_clicks_12m:
        chart_payload["gbp_clicks_12m"] = {"labels": gbp_clicks_labels or labels_months(len(gbp_clicks_12m)), "data": gbp_clicks_12m, "color": SECTION_COLOR["gbp_clicks_12m"]}
    if ct_calls_12m:
        chart_payload["call_tracking_12m"] = {"labels": ct_calls_labels or labels_months(len(ct_calls_12m)), "data": ct_calls_12m, "color": SECTION_COLOR["call_tracking_12m"]}
    if ct_conv_12m:
        chart_payload["call_tracking_conv_12m"] = {"labels": ct_conv_labels or labels_months(len(ct_conv_12m)), "data": ct_conv_12m, "color": SECTION_COLOR["call_tracking_conv_12m"]}

    # Count actual section states (live / partial / not_connected)
    live_section_count = 0
    partial_section_count = 0
    notes = []
    if organic_24m: live_section_count += 1
    else: notes.append("Organic Traffic")
    if gsc_clicks_12w and gsc_impr_12w: live_section_count += 1
    else: notes.append("GSC Performance")
    if conv_12m: live_section_count += 1
    else: notes.append("Conversions")
    # GBP — partial if only impressions+clicks, full if all 4
    gbp_full = all([gbp_impr_12m, gbp_calls_12m, gbp_clicks_12m, gbp_reviews_12m])
    if gbp_full:
        live_section_count += 1
    elif gbp_has_any:
        partial_section_count += 1
    elif has_gmb:
        notes.append("Google Business Profile")
    # Call Tracking — counts as live when call data present, partial when
    # configured but no data yet, not-connected when no config at all.
    if ct_calls_12m:
        live_section_count += 1
    elif has_call_tracking_config:
        partial_section_count += 1
    else:
        notes.append("Call Tracking")
    if page_perf:
        live_section_count += 2  # content + link
    else:
        notes.append("Content Performance")
        notes.append("Link Performance")

    # Base 5 (Organic, GSC, Conversions, Content perf, Link perf) + optional
    # GBP (if has_gmb) + Call Tracking (always shown — either live or alerted).
    total_sections = 7 if has_gmb else 6
    # ============ Paid media sections (Social Ads / PPC / LSA) ============
    # Each service line generates its own tabbed sub-view. The Reporting page
    # has a tab strip at top so clicking "Facebook Ads report" from the FB
    # performance card jumps straight to that view, not the SEO one.
    paid_media_by_service = {}   # service_type → inner HTML chunk
    service_lines_meta = (cf.get("service_lines") or [])
    fb_chart_payload = {}

    for sline in service_lines_meta:
        sl_type = sline.get("type")
        if sl_type == "social_ads" and sline.get("platform") == "facebook":
            fb_path = os.path.join(ROOT, "clients", slug, "analytics", "social_ads_facebook_summary.json")
            fb = None
            if os.path.exists(fb_path):
                try: fb = json.load(open(fb_path))
                except Exception: fb = None

            section_title = ('<h2 class="rep-section-title" style="border-left:4px solid #2563EB;padding-left:10px">'
                             'Facebook Ads <span class="rep-source">Windsor.ai · Meta Ads</span></h2>')

            if fb:
                # KPI row — 4 cards: Spend, Conversions, CPL/ROAS, Click-through
                spend = fb.get("spend_last_30d") or 0
                spend_prior = fb.get("spend_prior_30d") or 0
                convs = fb.get("conversions_last_30d") or 0
                convs_prior = fb.get("conversions_prior_30d") or 0
                impr = fb.get("impressions_last_30d") or 0
                clicks = fb.get("clicks_last_30d") or 0
                ctr = (100 * clicks / impr) if impr else 0
                cpl = (spend / convs) if convs else None
                roas = fb.get("roas_last_30d")
                mom_spend = fb.get("spend_mom_pct")
                mom_convs = fb.get("conversions_mom_pct")

                third_card = (
                    render_kpi_card("ROAS (30d)", f"{roas:.2f}x", None, "Revenue / spend")
                    if roas is not None else
                    render_kpi_card("Cost per lead (30d)",
                                     f"${cpl:,.0f}" if cpl else "—",
                                     None, "Spend / conversions")
                )
                fb_kpis = "".join([
                    render_kpi_card("Spend (last 30d)", f"${spend:,.0f}", mom_spend, "MoM"),
                    render_kpi_card("Conversions (last 30d)", f"{convs:,}", mom_convs, "MoM"),
                    third_card,
                    render_kpi_card("CTR", f"{ctr:.2f}", None, "%", suffix="%"),
                ])

                # Spend daily chart
                daily = fb.get("spend_daily_30d") or []
                if daily:
                    fb_chart_payload["fb_spend_daily_30d"] = {
                        "labels": [d.get("date", "")[5:] for d in daily],  # MM-DD
                        "data":   [d.get("spend", 0) for d in daily],
                        "color":  "#2563EB",
                    }
                # Conversions daily chart
                convs_daily = fb.get("conversions_daily_30d") or []
                if convs_daily:
                    fb_chart_payload["fb_conversions_daily_30d"] = {
                        "labels": [d.get("date", "")[5:] for d in convs_daily],
                        "data":   [d.get("conversions", 0) for d in convs_daily],
                        "color":  "#2563EB",
                    }

                chart_parts = []
                if daily:
                    chart_parts.append(
                        f'<div class="rep-chart-card"><div class="rep-chart-label">Daily spend · last 30 days</div>'
                        f'<canvas class="rep-chart" data-chart-id="{esc(slug)}-fb-spend" data-chart-key="fb_spend_daily_30d"></canvas></div>'
                    )
                if convs_daily:
                    chart_parts.append(
                        f'<div class="rep-chart-card"><div class="rep-chart-label">Daily conversions · last 30 days</div>'
                        f'<canvas class="rep-chart" data-chart-id="{esc(slug)}-fb-conv" data-chart-key="fb_conversions_daily_30d" data-chart-type="bar"></canvas></div>'
                    )
                charts_html = f'<div class="rep-chart-grid">{"".join(chart_parts)}</div>' if chart_parts else ""

                # Account-context note — surface the campaign-pause caveat
                # whenever the spend swing is dramatic (>50% drop). The exact
                # cause (full pause / partial pause / budget cut) is for the
                # strategist to interpret; the banner just prevents the
                # leadership team from misreading the swing as a performance
                # collapse.
                caveat_html = ""
                if mom_spend is not None and mom_spend < -50 and spend_prior > 0:
                    caveat_html = (
                        f'<div class="rep-disclaimer" style="background:#fef3c7;border-color:#fde68a;color:#92400e;margin-bottom:14px;">'
                          f'<strong>⚠ Spend pattern change</strong> — spend dropped {abs(mom_spend):.0f}% MoM '
                          f'(${spend:,.0f} vs ${spend_prior:,.0f}). '
                          f'Likely a campaign pause or budget cut; check the daily chart below to confirm. '
                          f'Comparison reflects activity pattern, not necessarily a performance issue.'
                        f'</div>'
                    )

                period_note = (
                    f'<div class="muted" style="font-size:11px;margin-bottom:8px;">'
                    f'Period: {esc(fb.get("period_last_30d", {}).get("start", "?"))} → '
                    f'{esc(fb.get("period_last_30d", {}).get("end", "?"))} · '
                    f'Account: {esc(fb.get("account_id", "?"))} · '
                    f'Conversion event: {esc(fb.get("conversion_action_type", "—"))}'
                    f'</div>'
                )

                # --- Top Ads table (sortable: spend / conversions / CPL / CTR) ---
                top_ads_path = os.path.join(ROOT, "clients", slug, "analytics", "social_ads_facebook_top_ads.json")
                top_ads_html = ""
                if os.path.exists(top_ads_path):
                    try:
                        top_ads = json.load(open(top_ads_path))
                    except Exception:
                        top_ads = None
                    if top_ads:
                        fb_account = top_ads.get("account_id", "")

                        def _row(a, *, cpl_emphasis=False):
                            cpl = a.get("cpl")
                            cpl_str = f'${cpl:,.2f}' if cpl else '—'
                            ctr = a.get("ctr") or 0
                            convs = a.get("conversions") or 0
                            spend = a.get("spend") or 0
                            thumb = a.get("thumbnail_url") or ""
                            ad_id = a.get("ad_id") or ""

                            # Thumbnail cell — small image if we have one, else
                            # a placeholder square. Clicking the thumbnail opens
                            # the larger-preview modal (driven by data attrs).
                            if thumb:
                                thumb_cell = (
                                    f'<button class="ad-thumb-btn" '
                                    f'data-thumb-url="{esc(thumb)}" '
                                    f'data-ad-name="{esc(a.get("ad",""))}" '
                                    f'data-campaign="{esc(a.get("campaign",""))}" '
                                    f'data-ad-id="{esc(ad_id)}" '
                                    f'data-account-id="{esc(fb_account)}">'
                                      f'<img src="{esc(thumb)}" alt="ad preview" loading="lazy" />'
                                    f'</button>'
                                )
                            else:
                                thumb_cell = '<div class="ad-thumb-empty">—</div>'

                            # Ads Manager link — opens FB Ads Manager filtered
                            # to this ad ID. Requires the user to be logged
                            # into a Meta account with access to the ad account.
                            if ad_id and fb_account:
                                manage_url = (
                                    f'https://www.facebook.com/adsmanager/manage/ads'
                                    f'?act={fb_account}&selected_ad_ids={ad_id}'
                                )
                                manage_link = f' · <a href="{esc(manage_url)}" target="_blank" rel="noopener" class="ads-manager-link">Open in Ads Manager ↗</a>'
                            else:
                                manage_link = ''

                            return (
                                f'<tr>'
                                  f'<td class="ad-thumb-cell">{thumb_cell}</td>'
                                  f'<td class="ad-name">'
                                    f'<div class="ad-name-title">{esc(a.get("ad","")[:80])}</div>'
                                    f'<div class="ad-name-campaign">{esc(a.get("campaign","")[:70])}{manage_link}</div>'
                                  f'</td>'
                                  f'<td class="num">${spend:,.0f}</td>'
                                  f'<td class="num">{a.get("impressions",0):,}</td>'
                                  f'<td class="num">{a.get("clicks",0):,}</td>'
                                  f'<td class="num">{ctr:.2f}%</td>'
                                  f'<td class="num"><strong>{convs}</strong></td>'
                                  f'<td class="num" style="font-weight:{"700" if cpl_emphasis else "500"}">{cpl_str}</td>'
                                  f'<td class="num">{a.get("days_active",0)}</td>'
                                f'</tr>'
                            )
                        def _table(rows, *, cpl_emphasis=False):
                            if not rows:
                                return '<div class="muted" style="padding:18px;text-align:center">No ads cleared the threshold for this ranking.</div>'
                            return (
                                '<table class="rep-perf-table top-ads-table"><thead><tr>'
                                  '<th></th>'
                                  '<th>Ad / Campaign</th><th class="num">Spend</th><th class="num">Impr.</th>'
                                  '<th class="num">Clicks</th><th class="num">CTR</th>'
                                  '<th class="num">Conv.</th><th class="num">CPL</th><th class="num">Days</th>'
                                '</tr></thead><tbody>' +
                                "".join(_row(a, cpl_emphasis=cpl_emphasis) for a in rows) +
                                '</tbody></table>'
                            )

                        period_str = (
                            f'{esc(top_ads.get("period", {}).get("start", "?"))} → '
                            f'{esc(top_ads.get("period", {}).get("end", "?"))} '
                            f'({top_ads.get("period", {}).get("active_days", "?")} active days · '
                            f'{top_ads.get("total_ads_seen", "?")} unique ads)'
                        )
                        period_note_2 = (
                            f'<div class="muted" style="font-size:11px;margin:14px 0 6px">'
                              f'Aggregated over {period_str} — gaps within the period (e.g. campaign pauses) are excluded from the active-day count.'
                              f'<br><em>Note:</em> {esc(top_ads.get("period", {}).get("note", ""))}'
                            f'</div>'
                        )
                        top_ads_html = (
                            '<h2 class="rep-section-title" style="border-left:4px solid #2563EB;padding-left:10px;margin-top:32px;">'
                              'Top Ads <span class="rep-source">Ranked by spend / conversions / CPL / CTR</span>'
                            '</h2>'
                            + period_note_2 +
                            '<div class="top-ads-tabs">'
                              '<button class="top-ads-tab active" data-rank="by_spend">By Spend</button>'
                              '<button class="top-ads-tab" data-rank="by_conversions">By Conversions</button>'
                              '<button class="top-ads-tab" data-rank="by_cpl">By Cost / Lead (best)</button>'
                              '<button class="top-ads-tab" data-rank="by_ctr">By CTR</button>'
                            '</div>'
                            f'<div class="top-ads-view" data-rank="by_spend">{_table(top_ads.get("by_spend") or [])}</div>'
                            f'<div class="top-ads-view" data-rank="by_conversions" style="display:none">{_table(top_ads.get("by_conversions") or [])}</div>'
                            f'<div class="top-ads-view" data-rank="by_cpl" style="display:none">{_table(top_ads.get("by_cpl") or [], cpl_emphasis=True)}</div>'
                            f'<div class="top-ads-view" data-rank="by_ctr" style="display:none">{_table(top_ads.get("by_ctr") or [])}</div>'
                        )

                paid_media_by_service["social_ads"] = (
                    section_title
                    + caveat_html
                    + period_note
                    + f'<div class="rep-kpi-row rep-kpi-row-4">{fb_kpis}</div>'
                    + charts_html
                    + top_ads_html
                )
            else:
                paid_media_by_service["social_ads"] = (
                    section_title
                    + f'<div class="rep-not-connected">'
                      f'<div class="rep-nc-badge">⊘ NOT CONNECTED</div>'
                      f'<div class="rep-nc-action">Run build_facebook_ads_summary.py to populate '
                      f'clients/{esc(slug)}/analytics/social_ads_facebook_summary.json — the Windsor.ai '
                      f'Meta Ads connector is the data source.</div>'
                    f'</div>'
                )

        elif sl_type == "ppc":
            # PPC reporting (Google Ads) — load cached summary, render KPIs,
            # daily charts, top campaigns table. LSA gets a sub-section
            # inside this same tab since LSA data lives in Google Ads.
            ppc_path = os.path.join(ROOT, "clients", slug, "analytics", "ppc_google_ads_summary.json")
            ppc = None
            if os.path.exists(ppc_path):
                try: ppc = json.load(open(ppc_path))
                except Exception: ppc = None

            ppc_section_title = (
                '<h2 class="rep-section-title" style="border-left:4px solid #9333EA;padding-left:10px">'
                'PPC (Google Ads) <span class="rep-source">Windsor.ai · Google Ads</span></h2>'
            )

            if ppc:
                spend = ppc.get("spend_last_30d") or 0
                convs = ppc.get("conversions_last_30d") or 0
                clicks = ppc.get("clicks_last_30d") or 0
                impr = ppc.get("impressions_last_30d") or 0
                ctr = ppc.get("ctr") or 0
                cpc = ppc.get("cpc") or 0
                cpa = ppc.get("cpa")
                mom_spend = ppc.get("spend_mom_pct")
                mom_convs = ppc.get("conversions_mom_pct")

                ppc_kpis = "".join([
                    render_kpi_card("Spend (last 30d)", f"${spend:,.0f}", mom_spend, "MoM"),
                    render_kpi_card("Conversions", f"{convs:,.0f}", mom_convs, "MoM"),
                    render_kpi_card("Cost per acq. (CPA)",
                                     f"${cpa:,.0f}" if cpa else "—", None, "Spend / conv."),
                    render_kpi_card("CTR", f"{ctr:.2f}", None, "%", suffix="%"),
                ])

                # Daily charts
                daily_spend = ppc.get("spend_daily_30d") or []
                daily_convs = ppc.get("conversions_daily_30d") or []
                if daily_spend:
                    fb_chart_payload["ppc_spend_daily_30d"] = {
                        "labels": [d.get("date", "")[5:] for d in daily_spend],
                        "data":   [d.get("spend", 0) for d in daily_spend],
                        "color":  "#9333EA",
                    }
                if daily_convs:
                    fb_chart_payload["ppc_conversions_daily_30d"] = {
                        "labels": [d.get("date", "")[5:] for d in daily_convs],
                        "data":   [d.get("conversions", 0) for d in daily_convs],
                        "color":  "#9333EA",
                    }
                ppc_chart_parts = []
                if daily_spend:
                    ppc_chart_parts.append(
                        f'<div class="rep-chart-card"><div class="rep-chart-label">Daily spend · last 30 days</div>'
                        f'<canvas class="rep-chart" data-chart-id="{esc(slug)}-ppc-spend" data-chart-key="ppc_spend_daily_30d"></canvas></div>'
                    )
                if daily_convs:
                    ppc_chart_parts.append(
                        f'<div class="rep-chart-card"><div class="rep-chart-label">Daily conversions · last 30 days</div>'
                        f'<canvas class="rep-chart" data-chart-id="{esc(slug)}-ppc-conv" data-chart-key="ppc_conversions_daily_30d" data-chart-type="bar"></canvas></div>'
                    )
                ppc_charts_html = f'<div class="rep-chart-grid">{"".join(ppc_chart_parts)}</div>' if ppc_chart_parts else ""

                # Top search terms table — what users actually typed to
                # trigger our ads. Loaded from a separate cache file because
                # the search-term resource pulls more granular data than
                # campaign-level rollup. 4 ranking views.
                terms_cache = os.path.join(ROOT, "clients", slug, "analytics", "ppc_google_ads_search_terms.json")
                top_campaigns_html = ""
                if os.path.exists(terms_cache):
                    try:
                        terms = json.load(open(terms_cache))
                    except Exception:
                        terms = None
                    if terms:
                        def _term_row(t, *, cpa_emphasis=False):
                            cpa_v = t.get("cpa")
                            cpa_cell = (
                                f'<td class="num" style="font-weight:{"700" if cpa_emphasis else "500"}">${cpa_v:,.0f}</td>'
                                if cpa_v else '<td class="num">—</td>'
                            )
                            return (
                                f'<tr>'
                                  f'<td class="ad-name">'
                                    f'<div class="ad-name-title">{esc(t.get("search_term","")[:90])}</div>'
                                  f'</td>'
                                  f'<td class="num">{t.get("impressions",0):,}</td>'
                                  f'<td class="num">{t.get("clicks",0):,}</td>'
                                  f'<td class="num">{t.get("ctr",0):.2f}%</td>'
                                  f'<td class="num">${t.get("cost",0):,.0f}</td>'
                                  f'<td class="num"><strong>{t.get("conversions",0):,.0f}</strong></td>'
                                  f'{cpa_cell}'
                                f'</tr>'
                            )
                        def _terms_table(rows, *, cpa_emphasis=False):
                            if not rows:
                                return '<div class="muted" style="padding:18px;text-align:center">No search terms cleared the threshold for this ranking.</div>'
                            return (
                                '<table class="rep-perf-table top-ads-table"><thead><tr>'
                                  '<th>Search Term</th><th class="num">Impr.</th>'
                                  '<th class="num">Clicks</th><th class="num">CTR</th>'
                                  '<th class="num">Cost</th><th class="num">Conv.</th>'
                                  '<th class="num">CPA</th>'
                                '</tr></thead><tbody>' +
                                "".join(_term_row(t, cpa_emphasis=cpa_emphasis) for t in rows) +
                                '</tbody></table>'
                            )
                        period_note_terms = (
                            f'<div class="muted" style="font-size:11px;margin:14px 0 8px;">'
                              f'Aggregated over {esc(terms.get("period", {}).get("start", "?"))} → '
                              f'{esc(terms.get("period", {}).get("end", "?"))} · '
                              f'{terms.get("total_search_terms", 0):,} unique terms · '
                              f'Source: {esc(terms.get("source", "?"))}.<br>'
                              f'<em>Note:</em> Google\'s search-term report omits low-volume queries (privacy filter) — totals here are a subset of overall ad spend.'
                            f'</div>'
                        )
                        top_campaigns_html = (
                            '<h3 style="font-family:var(--display);font-size:18px;text-transform:uppercase;letter-spacing:0.02em;margin-top:24px;color:var(--ink);">'
                              'Top Search Terms'
                            '</h3>'
                            + period_note_terms +
                            '<div class="top-ads-tabs">'
                              '<button class="top-ads-tab active" data-rank="by_cost">By Cost</button>'
                              '<button class="top-ads-tab" data-rank="by_conversions">By Conversions</button>'
                              '<button class="top-ads-tab" data-rank="by_cpa">By Cost / Conv. (best)</button>'
                              '<button class="top-ads-tab" data-rank="by_impressions">By Impressions</button>'
                            '</div>'
                            f'<div class="top-ads-view" data-rank="by_cost">{_terms_table(terms.get("by_cost") or [])}</div>'
                            f'<div class="top-ads-view" data-rank="by_conversions" style="display:none">{_terms_table(terms.get("by_conversions") or [])}</div>'
                            f'<div class="top-ads-view" data-rank="by_cpa" style="display:none">{_terms_table(terms.get("by_cpa") or [], cpa_emphasis=True)}</div>'
                            f'<div class="top-ads-view" data-rank="by_impressions" style="display:none">{_terms_table(terms.get("by_impressions") or [])}</div>'
                        )

                ppc_period_note = (
                    f'<div class="muted" style="font-size:11px;margin-bottom:8px;">'
                    f'Period: {esc(ppc.get("period_last_30d", {}).get("start", "?"))} → '
                    f'{esc(ppc.get("period_last_30d", {}).get("end", "?"))} · '
                    f'Account: {esc(ppc.get("account_id", "?"))}'
                    f'</div>'
                )

                ppc_main_html = (
                    ppc_section_title
                    + ppc_period_note
                    + f'<div class="rep-kpi-row rep-kpi-row-4">{ppc_kpis}</div>'
                    + ppc_charts_html
                    + top_campaigns_html
                )
            else:
                ppc_main_html = (
                    ppc_section_title
                    + f'<div class="rep-not-connected">'
                      f'<div class="rep-nc-badge">⊘ NOT CONNECTED</div>'
                      f'<div class="rep-nc-action">Run the Google Ads pull to populate '
                      f'clients/{esc(slug)}/analytics/ppc_google_ads_summary.json — Windsor.ai '
                      f'Google Ads connector is the data source.</div>'
                    f'</div>'
                )

            # --- LSA sub-section (inside the PPC tab) ---
            # LSA campaigns live in Google Ads with the prefix
            # "LocalServicesCampaign:SystemGenerated:". If the cached summary
            # found any, we'd display them; otherwise show empty state with
            # a hint about how to wire up.
            lsa_subsection = (
                '<h2 class="rep-section-title" style="border-left:4px solid #0EA5E9;padding-left:10px;margin-top:32px;">'
                'Local Service Ads <span class="rep-source">Google LSA · same Google Ads account</span></h2>'
            )
            if ppc and ppc.get("lsa_note"):
                # The PPC pull didn't find LSA campaigns — surface that note + the path to fix
                lsa_subsection += (
                    f'<div class="rep-not-connected" style="border-left-color:#0EA5E9;">'
                      f'<div class="rep-nc-badge" style="background:#0EA5E9">○ NO LSA ACTIVE</div>'
                      f'<div class="rep-nc-action">'
                        f'{esc(ppc["lsa_note"])} '
                        f'If this client has a separate LSA-only Google Ads account, add it to the '
                        f'PPC service_line\'s custom_fields as <code>google_ads_lsa_account_id</code> '
                        f'and re-run the analytics pull.'
                      f'</div>'
                    f'</div>'
                )
            else:
                lsa_subsection += (
                    f'<div class="rep-not-connected" style="border-left-color:#0EA5E9;">'
                      f'<div class="rep-nc-badge" style="background:#0EA5E9">⊘ NOT CONNECTED</div>'
                      f'<div class="rep-nc-action">No LSA cache data found yet. LSA campaigns appear '
                      f'in Google Ads with the prefix <code>LocalServicesCampaign:SystemGenerated:</code> '
                      f'— the PPC pull will detect them automatically when next run.</div>'
                    f'</div>'
                )

            paid_media_by_service["ppc"] = ppc_main_html + lsa_subsection

        elif sl_type == "lsa":
            # LSA service line still exists in clients.json but doesn't get
            # its own tab — its data lives inside the PPC tab (since LSA
            # and PPC both come from Google Ads / Adwords). Skip rendering
            # a separate tab for it.
            pass

    # Merge FB chart data into the main report payload
    chart_payload_merged = dict(fb_chart_payload)  # populated above

    if live_section_count == total_sections and not notes:
        disclaimer_html = (f'<div class="rep-disclaimer rep-disclaimer-live" style="background:#dcfce7;border-color:#86efac;color:#14532d">'
                           f'<strong>{esc(company)}</strong> · {esc(website)} · '
                           f'<strong>All sections live.</strong></div>')
    elif live_section_count > 0 or partial_section_count > 0:
        partial_note = f" ({partial_section_count} partial)" if partial_section_count else ""
        notconn_note = f" Not connected: {', '.join(notes)}." if notes else ""
        disclaimer_html = (f'<div class="rep-disclaimer" style="background:#dcfce7;border-color:#86efac;color:#14532d">'
                           f'<strong>{esc(company)}</strong> · {esc(website)} · '
                           f'<strong>{live_section_count} sections live{partial_note}.</strong>'
                           f'{esc(notconn_note)}</div>')
    else:
        disclaimer_html = (f'<div class="rep-disclaimer" style="background:#fee2e2;border-color:#fca5a5;color:#991b1b">'
                           f'<strong>{esc(company)}</strong> · {esc(website)} · '
                           f'<strong>No connectors active.</strong> See action notes in each section.</div>')

    # Build the service tab strip. Always show SEO (default tab). Add a tab
    # for each paid-media service that has rendered HTML. The first tab
    # active by default; deep-linking via #reporting/{slug}/<service>
    # activates a different tab.
    SERVICE_TAB_META = {
        "seo":        ("SEO",          "#F59E0B"),
        "social_ads": ("Facebook Ads", "#2563EB"),
        "ppc":        ("PPC",          "#9333EA"),
        # LSA intentionally not in the tab strip — LSA reporting is rendered
        # as a sub-section *inside* the PPC tab because Google's LSA data
        # comes from the same Google Ads account as regular PPC data.
    }
    tabs_html_parts = [
        f'<button class="rep-tab active" data-rep-service="seo" style="border-color:#F59E0B">'
          f'<span class="rep-tab-dot" style="background:#F59E0B"></span>SEO'
        f'</button>'
    ]
    for st, html_chunk in paid_media_by_service.items():
        label, c = SERVICE_TAB_META.get(st, (st.title(), "#64748b"))
        tabs_html_parts.append(
            f'<button class="rep-tab" data-rep-service="{esc(st)}" style="border-color:{c}">'
              f'<span class="rep-tab-dot" style="background:{c}"></span>{esc(label)}'
            f'</button>'
        )
    tabs_html = '<div class="rep-service-tabs">' + "".join(tabs_html_parts) + '</div>'

    # SEO content goes into the SEO sub-view; paid-media chunks each in their own.
    seo_view = (
        f'<div class="rep-service-view" data-rep-service="seo">'
          f'{disclaimer_html}'
          f'<h2 class="rep-section-title" style="border-left:4px solid #F59E0B;padding-left:10px">Organic Traffic <span class="rep-source">Google Analytics 4 / Ahrefs</span></h2>'
          f'{s1_html}'
          f'<h2 class="rep-section-title" style="border-left:4px solid #2563EB;padding-left:10px">Search Console Performance <span class="rep-source">Google Search Console</span></h2>'
          f'{s2_html}'
          f'<h2 class="rep-section-title" style="border-left:4px solid #16A34A;padding-left:10px">Conversions <span class="rep-source">GA4 · Organic traffic only</span></h2>'
          f'{s3_html}'
          f'<h2 class="rep-section-title" style="border-left:4px solid #9333EA;padding-left:10px">Google Business Profile <span class="rep-source">GBP / Google Maps</span></h2>'
          f'{s4_html}'
          f'<h2 class="rep-section-title" style="border-left:4px solid #0D9488;padding-left:10px">Call Tracking <span class="rep-source">{esc(ct_source_label)}</span></h2>'
          f'{s_calltrack_html}'
          f'<h2 class="rep-section-title" style="border-left:4px solid #DB2777;padding-left:10px">Content Performance <span class="rep-source">Impressions since updated vs prior period</span></h2>'
          f'{s5_html}'
          f'<h2 class="rep-section-title" style="border-left:4px solid #DC2626;padding-left:10px">Link Performance <span class="rep-source">Impressions last 90d vs prior 90d</span></h2>'
          f'{s6_html}'
        f'</div>'
    )

    paid_views = "".join(
        f'<div class="rep-service-view" data-rep-service="{esc(st)}" style="display:none">{html_chunk}</div>'
        for st, html_chunk in paid_media_by_service.items()
    )

    return f"""
<div class="reporting-panel" data-reporting-client="{esc(slug)}" style="display:none">
  {tabs_html}
  {seo_view}
  {paid_views}
  <script>window.REPORT_DATA = window.REPORT_DATA || {{}}; window.REPORT_DATA["{esc(slug)}"] = {json.dumps({**chart_payload, **fb_chart_payload})};</script>
</div>
"""


# ============ TIMELINE / GANTT VIEW ============

def render_gantt_view(slug, deliverables, project_start, project_end):
    """Render a Gantt-style timeline of all deliverables.

    Each deliverable becomes a horizontal bar positioned by start_date /
    due_date. Rows are grouped by sprint. The timeline spans the full
    engagement (project_start → project_end) with month-column gridlines.

    Layout uses CSS percentages: each bar's left + width is computed
    against the engagement length.
    """
    from datetime import date as date_cls, timedelta

    try:
        ps = date_cls.fromisoformat(project_start)
        pe = date_cls.fromisoformat(project_end)
    except (TypeError, ValueError):
        return '<div class="view" data-view="timeline"><div class="empty-state">No project dates available.</div></div>'

    total_days = max(1, (pe - ps).days)

    # Build month-column labels spanning the engagement
    month_cols = []
    cursor = ps.replace(day=1)
    while cursor <= pe:
        # Find the last day of this month
        if cursor.month == 12:
            next_month_first = cursor.replace(year=cursor.year + 1, month=1)
        else:
            next_month_first = cursor.replace(month=cursor.month + 1)
        month_end_day = next_month_first - timedelta(days=1)
        # Clamp to engagement range for the bar grid
        col_start = max(cursor, ps)
        col_end   = min(month_end_day, pe)
        left_pct  = ((col_start - ps).days / total_days) * 100
        width_pct = ((col_end - col_start).days + 1) / total_days * 100
        month_cols.append({
            "label": cursor.strftime("%b '%y"),
            "left_pct": left_pct,
            "width_pct": width_pct,
        })
        cursor = next_month_first

    # Group deliverables by sprint
    by_sprint = defaultdict(list)
    for d in deliverables:
        by_sprint[d.get("sprint_number") or 0].append(d)

    # Sort within each sprint by start_date then name
    for s in by_sprint:
        by_sprint[s].sort(key=lambda d: (d.get("start_date") or "9999", d.get("name") or ""))

    today = date_cls.today()
    today_pct = ((today - ps).days / total_days) * 100 if ps <= today <= pe else None

    # Header: month columns
    header_cells = "".join(
        f'<div class="gt-mh" style="left:{c["left_pct"]:.2f}%;width:{c["width_pct"]:.2f}%">'
        f'<span>{esc(c["label"])}</span></div>'
        for c in month_cols
    )

    # Build rows, grouped by sprint
    body_html = []
    for sprint_n in sorted(by_sprint.keys()):
        items = by_sprint[sprint_n]
        if not items:
            continue
        label = SPRINT_LABEL.get(sprint_n, f"Sprint {sprint_n}")
        color = SPRINT_COLOR.get(sprint_n, "#64748b")
        body_html.append(
            f'<div class="gt-group-header" style="border-left-color:{color};">'
            f'<span class="gt-group-name">{esc(label)}</span>'
            f'<span class="gt-group-count">{len(items)} task{"" if len(items) == 1 else "s"}</span>'
            f'</div>'
        )
        for d in items:
            sd = d.get("start_date")
            due = d.get("due_date")
            try:
                ds = date_cls.fromisoformat(sd)
                de = date_cls.fromisoformat(due)
            except (TypeError, ValueError):
                continue
            left_pct  = max(0, ((ds - ps).days / total_days) * 100)
            # Bar width: include the due day itself so 1-day tasks are visible
            width_pct = max(1.2, ((de - ds).days + 1) / total_days * 100)
            owner = d.get("assigned_to_email") or "unassigned"
            owner_name = PERSON_DISPLAY.get(owner, owner)
            owner_initial = (owner_name or "?")[0].upper()
            kind_tag = ""
            if d.get("is_monthly_report"): kind_tag = "monthly-report"
            elif d.get("is_heavy_batch"): kind_tag = "heavy-batch"
            elif d.get("is_placeholder"): kind_tag = "placeholder"
            else: kind_tag = "quick"
            bar_label = d.get("name") or ""
            tooltip = f"{bar_label} · {sd} → {due} · {owner_name}"
            body_html.append(
                f'<div class="gt-row" data-sprint="{sprint_n}" data-kind="{kind_tag}">'
                  f'<div class="gt-row-label">'
                    f'<span class="gt-avatar" title="{esc(owner_name)}">{esc(owner_initial)}</span>'
                    f'<span class="gt-task-name" title="{esc(bar_label)}">{esc(bar_label)}</span>'
                  f'</div>'
                  f'<div class="gt-row-track">'
                    f'<div class="gt-bar" '
                    f'style="left:{left_pct:.2f}%;width:{width_pct:.2f}%;background:{color};" '
                    f'title="{esc(tooltip)}">'
                      f'<span class="gt-bar-text">{esc(bar_label[:60])}</span>'
                    f'</div>'
                  f'</div>'
                f'</div>'
            )

    today_marker = (
        f'<div class="gt-today" style="left:{today_pct:.2f}%;"><span class="gt-today-label">Today</span></div>'
        if today_pct is not None else ""
    )

    return f"""
<div class="view" data-view="timeline" data-slug="{esc(slug)}">
  <div class="muted" style="margin-bottom:8px;font-size:12px;">
    Timeline of all {sum(len(v) for v in by_sprint.values())} deliverables across the {len(month_cols)}-month engagement.
    Bars colored by sprint. Hover a bar for full name + dates + owner.
  </div>
  <div class="gantt">
    <div class="gt-header">
      <div class="gt-row-label gt-header-label">Task</div>
      <div class="gt-row-track gt-header-track">{header_cells}</div>
    </div>
    <div class="gt-body">
      {today_marker}
      {''.join(body_html)}
    </div>
  </div>
</div>
"""




# ============ DELIVERABLES VIEW ============

def render_deliverables_view(slug, deliverables):
    """Auto-populated list of deliverables that roll up from tasks, plus manual adds."""
    # Roll up tasks → deliverables
    rollups = defaultdict(list)
    for d in deliverables:
        rollups[deliverable_for(d)].append(d)

    auto_rows = []
    for deliv_name, tasks in rollups.items():
        if deliv_name == "—": continue
        d_bg, d_fg = DELIVERABLE_PILL.get(deliv_name, ("#f1f5f9", "#475569"))
        statuses = Counter(default_status(t) for t in tasks)
        done = statuses["completed"] + statuses["approved"]
        progress = round(100 * done / len(tasks)) if tasks else 0
        due_dates = [t.get("due_date") for t in tasks if t.get("due_date")]
        target_date = max(due_dates) if due_dates else ""

        # Compose a status summary
        status_pieces = []
        for k, label in [("scheduled","scheduled"), ("working","working"),
                          ("review_needed","review"), ("delayed","delayed"),
                          ("completed","done")]:
            if statuses[k]:
                status_pieces.append(f"{statuses[k]} {label}")
        if statuses["approved"]: status_pieces.append(f'{statuses["approved"]} approved')
        status_summary = " · ".join(status_pieces) or "—"

        # Send-state default = scheduled (user updates as they send)
        # Use a stable key based on slug + deliverable name
        did = f"auto::{slug}::{deliv_name.lower().replace(' ', '-')}"
        first_opt = DELIVERABLE_STATUS_OPTIONS[0]
        send_bg, send_fg = first_opt[2], first_opt[3]
        send_label = first_opt[1]

        auto_rows.append(
            f'<div class="row deliverable-row auto-row" data-auto-id="{esc(did)}">'
              f'<div class="cell cell-dv-name"><span class="deliverable-pill" style="background:{d_bg};color:{d_fg}">{esc(deliv_name)}</span></div>'
              f'<div class="cell cell-dv-progress">'
                f'<div class="progress-wrap"><div class="progress-track"><div class="progress-bar" style="width:{progress}%"></div></div><span class="progress-label">{progress}%</span></div>'
                f'<div class="muted" style="font-size:10px;margin-top:2px;">{done} of {len(tasks)} tasks · {esc(status_summary)}</div>'
              f'</div>'
              f'<div class="cell cell-dv-target">{esc(format_date_mmddyy(target_date))}</div>'
              f'<div class="cell cell-dv-status"><span class="status-pill auto-deliverable-status" data-auto-id="{esc(did)}" data-status="scheduled" style="background:{send_bg};color:{send_fg}"><span class="pill-label">{send_label}</span><span class="pill-caret">▾</span></span></div>'
              f'<div class="cell cell-dv-senddate editable-cell" data-field="send_date" data-id="{esc(did)}" contenteditable="true" data-placeholder="MM/DD/YY"></div>'
              f'<div class="cell cell-dv-sender editable-cell" data-field="sender" data-id="{esc(did)}" contenteditable="true" data-placeholder="—"></div>'
              f'<div class="cell cell-dv-link editable-cell" data-field="link" data-id="{esc(did)}" contenteditable="true" data-placeholder="paste link…"></div>'
              f'<div class="cell cell-dv-notes editable-cell" data-field="notes" data-id="{esc(did)}" contenteditable="true" data-placeholder="—"></div>'
            f'</div>'
        )

    status_options_json = json.dumps(DELIVERABLE_STATUS_OPTIONS)
    auto_rows_html = "".join(auto_rows) if auto_rows else '<div class="empty-row">No tasks to roll up yet.</div>'

    return f"""
<div class="view" data-view="deliverables">
  <div class="deliverables-toolbar">
    <button class="btn-primary" onclick="addDeliverable('{esc(slug)}')">+ Add Custom Deliverable</button>
    <span class="muted" style="margin-left:auto;font-size:12px;">Auto-rolled-up from tasks + any ad-hoc items sent (audits, reports, etc.)</span>
  </div>
  <h3 class="section-title" style="font-size:14px;margin:14px 0 6px;letter-spacing:0.05em;">Auto-rolled from tasks</h3>
  <div class="task-table deliverables-table" data-client="{esc(slug)}">
    <div class="table-header">
      <div class="cell cell-dv-name">Deliverable</div>
      <div class="cell cell-dv-progress">Progress</div>
      <div class="cell cell-dv-target">Target Send</div>
      <div class="cell cell-dv-status">Send Status</div>
      <div class="cell cell-dv-senddate">Sent Date</div>
      <div class="cell cell-dv-sender">Sender</div>
      <div class="cell cell-dv-link">Link</div>
      <div class="cell cell-dv-notes">Notes</div>
    </div>
    <div class="deliverables-body">{auto_rows_html}</div>
  </div>
  <h3 class="section-title" style="font-size:14px;margin:20px 0 6px;letter-spacing:0.05em;">Custom / ad-hoc deliverables</h3>
  <div class="task-table custom-deliverables-table" data-client="{esc(slug)}">
    <div class="table-header">
      <div class="cell cell-d-date">Send Date</div>
      <div class="cell cell-d-sender">Sender</div>
      <div class="cell cell-d-name">Deliverable</div>
      <div class="cell cell-d-status">Status</div>
      <div class="cell cell-d-link">Link</div>
      <div class="cell cell-d-notes">Notes</div>
      <div class="cell cell-d-actions"></div>
    </div>
    <div class="deliverables-body" id="deliverables-{esc(slug)}">
      <div class="empty-row">Add WQA spreadsheet, WQA report, briefs, etc. via the button above.</div>
    </div>
  </div>
  <script>window.DELIVERABLE_STATUS_OPTIONS = {status_options_json};</script>
</div>
"""


# ============ PEOPLE VIEW ============

def render_people_view(slug, deliverables):
    """Team roster cards — name, email, specialty, current work."""
    # Group deliverables by assignee
    by_person = defaultdict(list)
    for d in deliverables:
        by_person[d.get("assigned_to_email") or "unassigned"].append(d)

    cards = []
    for person in TEAM_ROSTER:
        email = person["email"]
        items = by_person.get(email, [])
        items.sort(key=lambda d: d.get("due_date") or "9999-99-99")
        upcoming = items[:6]

        initial = person["name"][0].upper()
        skills_str = " · ".join(person["skills"])

        work_rows = []
        for d in upcoming:
            sn = d.get("sprint_number")
            b_bg, b_fg = BUCKET_BG.get(sn, ("#f1f5f9", "#475569"))
            bucket_label = BUCKET_LABEL.get(sn, "—")
            work_rows.append(
                f'<div class="work-row">'
                  f'<span class="work-due">{esc(format_date_mmddyy(d.get("due_date")))}</span>'
                  f'<span class="bucket-pill" style="background:{b_bg};color:{b_fg};font-size:9px;padding:1px 6px;">{esc(bucket_label)}</span>'
                  f'<span class="work-name">{esc(d.get("name") or "")}</span>'
                f'</div>'
            )
        if not work_rows:
            work_rows.append('<div class="muted" style="font-size:12px;">No deliverables assigned.</div>')

        cards.append(
            f'<div class="person-card clickable" data-jump-client="{esc(slug)}" data-jump-email="{esc(email)}" title="Click to see {esc(person["name"])}\'s tasks">'
              f'<div class="person-card-head">'
                f'<div class="avatar xl">{esc(initial)}</div>'
                f'<div class="person-card-info">'
                  f'<h3 class="person-card-name">{esc(person["name"])}</h3>'
                  f'<div class="person-card-title">{esc(person["title"])}</div>'
                  f'<div class="person-card-email"><a href="mailto:{esc(email)}" onclick="event.stopPropagation()">{esc(email)}</a></div>'
                f'</div>'
              f'</div>'
              f'<div class="person-card-section">'
                f'<div class="person-card-label">Specialties</div>'
                f'<div class="person-card-skills">{esc(skills_str)}</div>'
              f'</div>'
              f'<div class="person-card-section">'
                f'<div class="person-card-label">Current work ({len(items)} total)</div>'
                f'<div class="person-card-work">' + "".join(work_rows) + f'</div>'
              f'</div>'
              f'<div class="person-card-cta">View their tasks →</div>'
            f'</div>'
        )

    return (
        '<div class="view" data-view="people">'
          '<div class="people-grid">' + "".join(cards) + '</div>'
        '</div>'
    )


# ============ PER-PERSON CROSS-CLIENT VIEW ============

def render_person_page(person, all_client_data):
    """Single page showing every task assigned to one person across every client.
    Used when individual contributors log in to see their daily plate."""
    email = person["email"]
    name = person["name"]
    initial = name[0].upper()
    skills_str = " · ".join(person["skills"])

    # Aggregate all assigned tasks across clients
    tasks = []  # (deliverable, client_company, client_slug, idx)
    for cd in all_client_data:
        plan = cd.get("plan_info")
        if not plan: continue
        slug = cd["slug"]
        company = cd["client"].get("company_name", "")
        for idx, d in enumerate(plan["plan"]["deliverables"]):
            if d.get("assigned_to_email") == email:
                tasks.append((d, company, slug, idx))
    # Sort by due date ascending
    tasks.sort(key=lambda x: x[0].get("due_date") or "9999-99-99")

    # Status counts
    status_counts = Counter(default_status(t[0]) for t in tasks)
    delayed_count = status_counts.get("delayed", 0)
    completed_count = status_counts.get("completed", 0) + status_counts.get("approved", 0)

    if not tasks:
        rows_html = '<div class="empty-row">No tasks assigned across any client.</div>'
    else:
        # Render rows with a Client column
        row_parts = []
        for d, company, slug, idx in tasks:
            sn = d.get("sprint_number")
            bucket_label = BUCKET_LABEL.get(sn, "—")
            b_bg, b_fg = BUCKET_BG.get(sn, ("#f1f5f9", "#475569"))
            status = default_status(d)
            is_auto = status == "delayed"
            due_date = d.get("due_date") or ""
            sort_due = due_date or "9999-99-99"
            start_date = compute_start_date(d) or ""
            did = deliverable_id(slug, d, idx)
            src = d.get("source") or {}
            desc = d.get("description") or ""
            ai_html = '<span class="ai-tag">✨</span>' if d.get("ai_assisted") else ''
            notes_inline = ""
            if src.get("url"):
                u = src["url"].replace("https://", "").replace("http://", "")
                notes_inline = f'<a href="{esc(src["url"])}" target="_blank" onclick="event.stopPropagation()">{esc(u[:60])}</a>'

            row_parts.append(
                f'<details class="row" data-status="{status}" data-sprint="{sn}" '
                f'data-client="{esc(slug)}" data-due="{sort_due}" '
                f'data-search="{esc((d.get("name") or "").lower() + " " + company.lower())}">'
                f'<summary>'
                  f'<div class="cell cell-pp-client"><a href="#client/{esc(slug)}" onclick="event.stopPropagation()"><strong>{esc(company)}</strong></a></div>'
                  f'<div class="cell cell-pp-start">{esc(format_date_mmddyy(start_date))}</div>'
                  f'<div class="cell cell-pp-due">{date_pill(due_date, status)}</div>'
                  f'<div class="cell cell-pp-status">{status_pill_editable(status, did, is_auto)}</div>'
                  f'<div class="cell cell-pp-bucket"><span class="bucket-pill" style="background:{b_bg};color:{b_fg}">{esc(bucket_label)}</span></div>'
                  f'<div class="cell cell-pp-task">{ai_html}<span class="row-name">{esc(d.get("name") or "")}</span></div>'
                  f'<div class="cell cell-pp-notes">{notes_inline}</div>'
                f'</summary>'
                f'<div class="row-body">'
                  f'<div class="row-detail"><div class="row-detail-label">Description</div><div>{esc(desc) or "—"}</div></div>'
                f'</div>'
                f'</details>'
            )
        rows_html = "".join(row_parts)

    # Filter dropdowns
    client_options = "".join(
        f'<option value="{esc(cd["slug"])}">{esc(cd["client"].get("company_name", ""))}</option>'
        for cd in all_client_data
    )
    status_options = "".join(
        f'<option value="{esc(k)}">{esc(label)}</option>'
        for k, label, _, _ in STATUS_OPTIONS
    )

    return f"""
<div class="page" data-page="person/{esc(email)}" style="display:none">
  <div class="breadcrumb"><a href="#admin">← All team</a></div>
  <header class="person-header">
    <div class="avatar xl">{esc(initial)}</div>
    <div>
      <h1 style="font-family:var(--display);font-size:36px;line-height:1.0;margin:0 0 4px;text-transform:uppercase;letter-spacing:0.01em;font-weight:400;">{esc(name)}</h1>
      <div style="font-size:13px;color:var(--muted);font-weight:600;text-transform:uppercase;letter-spacing:0.05em;">{esc(person["title"])}</div>
      <div style="font-size:13px;margin-top:4px;"><a href="mailto:{esc(email)}">{esc(email)}</a></div>
      <div style="font-size:12px;color:var(--muted);margin-top:4px;">{esc(skills_str)}</div>
    </div>
  </header>
  <div class="kpi-grid" style="margin-bottom:16px;">
    <div class="kpi"><div class="kpi-label">Total tasks</div><div class="kpi-value">{len(tasks)}</div></div>
    <div class="kpi"><div class="kpi-label">Delayed</div><div class="kpi-value" style="color:#dc2626">{delayed_count}</div></div>
    <div class="kpi"><div class="kpi-label">Completed</div><div class="kpi-value" style="color:#16a34a">{completed_count}</div></div>
    <div class="kpi"><div class="kpi-label">Across clients</div><div class="kpi-value">{len(set(t[2] for t in tasks))}</div></div>
  </div>
  <div class="filters person-filters">
    <label>Filter:</label>
    <select class="pf-client"><option value="">All clients</option>{client_options}</select>
    <select class="pf-status"><option value="">All statuses</option>{status_options}</select>
    <input type="text" class="pf-search" placeholder="Search task name…" style="margin-left:auto;width:240px;">
  </div>
  <div class="task-table">
    <div class="table-header">
      <div class="cell cell-pp-client">Client</div>
      <div class="cell cell-pp-start">Start</div>
      <div class="cell cell-pp-due">Due</div>
      <div class="cell cell-pp-status">Status</div>
      <div class="cell cell-pp-bucket">Bucket</div>
      <div class="cell cell-pp-task">Task</div>
      <div class="cell cell-pp-notes">Notes</div>
    </div>
    <div class="flat-body">{rows_html}</div>
  </div>
</div>
"""


# ============ CONTENT VIEW ============

def _sheet_live_count_html(cd, kind):
    """Render the Live Content / Live Links count for the clients overview.

    kind: "content" or "links"
    Returns 0+ when the cache exists, "—" when not connected yet.
    """
    if kind == "content":
        cache = cd.get("content_cache")
        if not cache:
            return '<span class="muted-link" title="Content workbook not connected">—</span>'
        n = sum(1 for r in cache.get("rows", []) if sheets_sync.is_content_live(r))
        return str(n)
    elif kind == "links":
        cache = cd.get("links_cache")
        if not cache:
            return '<span class="muted-link" title="Link DB not synced">—</span>'
        n = sum(1 for r in cache.get("rows", []) if sheets_sync.is_link_live(r))
        return str(n)
    return "—"


def _sheets_banner(cache, sheet_kind_label, fallback_sheet_id, fallback_help_text):
    """Render the 'Last synced / Open workbook' banner above sheet-backed tables.

    Args:
      cache: the loaded JSON cache (or None if missing)
      sheet_kind_label: human label e.g. "Content workbook"
      fallback_sheet_id: the sheet ID to link to when cache is missing
                        (per-client for content, agency-level for links)
      fallback_help_text: what message to show when sheet_id is empty
    """
    if cache:
        synced = sheets_sync.cache_freshness_label(cache)
        sheet_url = cache.get("sheet_url") or "#"
        return (
            f'<div class="sheets-banner">'
              f'<div class="sb-meta">'
                f'<span class="sb-dot" style="background:#16a34a"></span>'
                f'<span class="sb-label">{esc(sheet_kind_label)}</span>'
                f'<span class="sb-sync">{esc(synced)}</span>'
              f'</div>'
              f'<div class="sb-actions">'
                f'<a href="{esc(sheet_url)}" target="_blank" class="sb-cta">📋 Open workbook ↗</a>'
              f'</div>'
            f'</div>'
        )
    # No cache yet — show a not-connected state.
    if fallback_sheet_id:
        sheet_url = f"https://docs.google.com/spreadsheets/d/{fallback_sheet_id}/edit"
        msg = "Configured but never synced. Pull the workbook to populate this view."
        cta = f'<a href="{esc(sheet_url)}" target="_blank" class="sb-cta">📋 Open workbook ↗</a>'
    else:
        msg = fallback_help_text
        cta = ""
    return (
        f'<div class="sheets-banner sheets-banner-warn">'
          f'<div class="sb-meta">'
            f'<span class="sb-dot" style="background:#dc2626"></span>'
            f'<span class="sb-label">{esc(sheet_kind_label)}</span>'
            f'<span class="sb-sync">{esc(msg)}</span>'
          f'</div>'
          f'<div class="sb-actions">{cta}</div>'
        f'</div>'
    )


def render_content_view(slug, content_cache, client):
    """Content tracker — read-only mirror of the client's content workbook.

    The workbook is the source of truth. Writers edit rows in the sheet;
    the dashboard reflects them on the next build. No inline editing here.
    """
    rows_html = []
    cache_rows = (content_cache or {}).get("rows", [])

    for r in cache_rows:
        status = r.get("status") or ""
        status_class = sheets_sync.content_status_class(status)
        kw = r.get("main_kw") or ""
        published_url = r.get("published_url") or ""
        published_short = published_url.replace("https://", "").replace("http://", "")
        draft_url = r.get("draft_url") or ""
        # Topic cell: link to the live URL if the piece is live, else to the
        # draft doc if there is one; otherwise just show the KW
        if published_url and sheets_sync.is_content_live(r):
            topic_cell = f'<a href="{esc(published_url)}" target="_blank">{esc(kw)}</a> <span class="muted-link">· live</span>'
        elif draft_url:
            topic_cell = f'<a href="{esc(draft_url)}" target="_blank">{esc(kw)}</a> <span class="muted-link">· draft</span>'
        else:
            topic_cell = esc(kw)

        rows_html.append(
            f'<div class="row content-row sheet-row" data-search="{esc((kw + " " + status).lower())}">'
              f'<div class="cell cell-c-status"><span class="status-pill {status_class}">{esc(status or "—")}</span></div>'
              f'<div class="cell cell-c-feedback">{esc(r.get("client_feedback") or "")}</div>'
              f'<div class="cell cell-c-topic">{topic_cell}</div>'
              f'<div class="cell cell-c-pagetype">{esc(r.get("page_type") or "")}</div>'
              f'<div class="cell cell-c-newrewrite">{esc(r.get("new_or_rewrite") or "")}</div>'
              f'<div class="cell cell-c-vol">{esc(r.get("search_volume") or "")}</div>'
              f'<div class="cell cell-c-published">{esc(r.get("published_date") or "")}</div>'
              f'<div class="cell cell-c-url">{esc(published_short)}</div>'
            f'</div>'
        )

    if not rows_html:
        rows_html.append('<div class="empty-row">No content rows yet. Add rows in the workbook and rebuild.</div>')

    cf = (client or {}).get("custom_fields", {}) or {}
    banner = _sheets_banner(
        content_cache,
        "Content workbook",
        fallback_sheet_id=cf.get("content_workbook_id"),
        fallback_help_text=("No content workbook configured for this client yet. "
                            "It will be created during onboarding."),
    )
    live_count = sum(1 for r in cache_rows if sheets_sync.is_content_live(r))
    summary = (
        f'<div class="muted" style="margin-bottom:8px;font-size:12px;">'
          f'{len(cache_rows)} pieces tracked · {live_count} live. '
          f'All edits happen in the workbook.'
        f'</div>'
    )

    return f"""
<div class="view" data-view="content" data-slug="{esc(slug)}">
  {banner}
  {summary}
  <div class="task-table content-table">
    <div class="table-header">
      <div class="cell cell-c-status">Status</div>
      <div class="cell cell-c-feedback">Client Feedback</div>
      <div class="cell cell-c-topic">Topic / KW</div>
      <div class="cell cell-c-pagetype">Page Type</div>
      <div class="cell cell-c-newrewrite">New / Rewrite</div>
      <div class="cell cell-c-vol">Search Vol</div>
      <div class="cell cell-c-published">Published</div>
      <div class="cell cell-c-url">URL</div>
    </div>
    <div class="flat-body">{"".join(rows_html)}</div>
  </div>
</div>
"""


# ============ LINKS VIEW ============

LINK_STATUS_COLOR = {
    "live":     ("#22c55e", "#ffffff"),  # green
    "in_flight":("#fde68a", "#92400e"),  # gold
    "outreach": ("#bfdbfe", "#1e40af"),  # blue
    "dead":     ("#fecaca", "#991b1b"),  # red
    "other":    ("#e5e7eb", "#374151"),
    "unknown":  ("#f3f4f6", "#6b7280"),
}


def render_links_view(slug, links_cache, client):
    """Link tracker — read-only mirror of the central link DB filtered to this client.

    The link DB is the source of truth. Rinor + the link-building team
    edits rows in the central sheet; the dashboard reflects them on the
    next build.
    """
    rows_html = []
    cache_rows = (links_cache or {}).get("rows", [])

    # Group by status bucket, then show in pipeline order (live -> in-flight ->
    # outreach -> dead). Within each bucket, sort by date desc.
    bucket_order = ["live", "in_flight", "outreach", "other", "dead", "unknown"]
    bucketed = {b: [] for b in bucket_order}
    for r in cache_rows:
        bucketed[sheets_sync.link_status_bucket(r.get("status"))].append(r)

    def parse_date(s):
        # The DB uses M/D/YYYY. Fall back to a sentinel that sorts last.
        if not s:
            return (9999, 12, 31)
        parts = (s or "").strip().split("/")
        if len(parts) != 3:
            return (9999, 12, 31)
        try:
            m, d, y = int(parts[0]), int(parts[1]), int(parts[2])
            if y < 100:
                y += 2000
            return (y, m, d)
        except ValueError:
            return (9999, 12, 31)

    for b in bucket_order:
        bucketed[b].sort(key=lambda r: parse_date(r.get("date")), reverse=True)

    for b in bucket_order:
        for r in bucketed[b]:
            status = r.get("status") or ""
            bucket = sheets_sync.link_status_bucket(status)
            bg, fg = LINK_STATUS_COLOR.get(bucket, LINK_STATUS_COLOR["unknown"])
            target_page = r.get("target_page") or ""
            target_short = target_page.replace("https://", "").replace("http://", "")
            live_url = r.get("live_url") or ""
            live_short = live_url.replace("https://", "").replace("http://", "")
            domain = r.get("domain") or (live_short.split("/")[0] if live_short else "")
            url_cell = (
                f'<a href="{esc(live_url)}" target="_blank">{esc(domain or live_short)}</a>'
                if live_url else esc(domain or "—")
            )
            target_cell = (
                f'<a href="{esc(target_page)}" target="_blank">{esc(target_short)}</a>'
                if target_page else "—"
            )
            search_str = f"{domain} {target_short} {r.get('anchor', '')} {status}".lower()
            rows_html.append(
                f'<div class="row link-row sheet-row" data-search="{esc(search_str)}" data-bucket="{esc(bucket)}">'
                  f'<div class="cell cell-l-status"><span class="status-pill" style="background:{bg};color:{fg}">{esc(status or "—")}</span></div>'
                  f'<div class="cell cell-l-date">{esc(r.get("date") or "")}</div>'
                  f'<div class="cell cell-l-type">{esc(r.get("link_type") or "")}</div>'
                  f'<div class="cell cell-l-url">{url_cell}</div>'
                  f'<div class="cell cell-l-target">{target_cell}</div>'
                  f'<div class="cell cell-l-anchor">{esc(r.get("anchor") or "")}</div>'
                  f'<div class="cell cell-l-cost">{esc(r.get("cost") or "")}</div>'
                f'</div>'
            )

    if not rows_html:
        rows_html.append('<div class="empty-row">No link rows for this client in the central DB yet.</div>')

    # Link DB is agency-level: same sheet shared across all clients,
    # filtered by client_name. Sheet ID lives on data/agency.json.
    central_links_id = agency.get("google_config", {}).get("central_links_db_id")
    banner = _sheets_banner(
        links_cache,
        "Central link DB",
        fallback_sheet_id=central_links_id,
        fallback_help_text="Central link DB not configured. Set google_config.central_links_db_id in agency.json.",
    )
    live_count = sum(1 for r in cache_rows if sheets_sync.is_link_live(r))
    in_flight = sum(1 for r in cache_rows
                     if sheets_sync.link_status_bucket(r.get("status")) == "in_flight")
    outreach  = sum(1 for r in cache_rows
                     if sheets_sync.link_status_bucket(r.get("status")) == "outreach")
    summary = (
        f'<div class="muted" style="margin-bottom:8px;font-size:12px;">'
          f'{len(cache_rows)} links · {live_count} live · {in_flight} in-flight · {outreach} outreach. '
          f'All edits happen in the central DB.'
        f'</div>'
    )

    return f"""
<div class="view" data-view="links" data-slug="{esc(slug)}">
  {banner}
  {summary}
  <div class="task-table links-table">
    <div class="table-header">
      <div class="cell cell-l-status">Status</div>
      <div class="cell cell-l-date">Date</div>
      <div class="cell cell-l-type">Type</div>
      <div class="cell cell-l-url">Source</div>
      <div class="cell cell-l-target">Target Page</div>
      <div class="cell cell-l-anchor">Anchor</div>
      <div class="cell cell-l-cost">Cost</div>
    </div>
    <div class="flat-body">{"".join(rows_html)}</div>
  </div>
</div>
"""


# ============ Clients grid ============

def current_month_for(project_start, total_months=12):
    from datetime import date as date_cls
    try:
        start = date_cls.fromisoformat(project_start)
        today = date_cls.fromisoformat(TODAY)
        delta_days = (today - start).days
        return max(1, min(total_months, delta_days // 30 + 1))
    except Exception:
        return 1


def stage_for_month(m):
    if m == 1:
        return "Technical Foundations"
    if 2 <= m <= 5:
        return "Production Phase"
    if 6 <= m <= 12:
        return "Stabilize & Iterate"
    return "—"


def real_perf(slug):
    """Compute WoW (GSC clicks), MoM/YoY (Ahrefs organic) from cached data.

    Returns dict with wow/mom/yoy (or None if cache missing) AND is_real boolean.
    """
    def pct(cur, prev):
        if not prev: return 0.0
        return ((cur - prev) / prev) * 100

    org_cache = os.path.join(ROOT, "clients", slug, "analytics", "ga4_organic_monthly_24m.json")
    gsc_cache = os.path.join(ROOT, "clients", slug, "analytics", "gsc_clicks_weekly_12w.json")
    if os.path.exists(org_cache) and os.path.exists(gsc_cache):
        try:
            org = json.load(open(org_cache))["data"]
            gsc = json.load(open(gsc_cache))["data"]
            return {
                "wow": pct(gsc[-1], gsc[-2]) if len(gsc) >= 2 else None,
                "mom": pct(org[-1], org[-2]) if len(org) >= 2 else None,
                "yoy": pct(org[-1], org[-13]) if len(org) >= 13 else None,
                "is_real": True,
            }
        except Exception:
            pass
    return {"wow": None, "mom": None, "yoy": None, "is_real": False}


# Alias for any leftover callers
mock_perf = real_perf


STATUS_DISPLAY = {
    "active":          ("Active",           "#10b981"),
    "onboarding":      ("Onboarding",       "#f59e0b"),
    "needs_attention": ("Needs Attention",  "#ea580c"),
    "inactive":        ("Inactive",         "#ef4444"),
    "unknown":         ("Unknown",          "#94a3b8"),
}


def render_perf_delta(value):
    """Up/down arrow + percent. Renders '—' when value is None."""
    if value is None:
        return '<span style="color:#94a3b8;font-weight:600;">—</span>'
    sign = "+" if value >= 0 else ""
    arrow = "▲" if value >= 0 else "▼"
    color = "#16a34a" if value >= 0 else "#dc2626"
    return f'<span style="color:{color};font-weight:700;">{arrow} {sign}{value:.1f}%</span>'


SERVICE_COLORS = {
    "SEO":            ("#dbeafe", "#1e40af"),  # blue
    "Meta Ads":       ("#fce7f3", "#9f1239"),  # pink (FB)
    "Facebook Ads":   ("#fce7f3", "#9f1239"),
    "PPC":            ("#fef3c7", "#854d0e"),  # yellow
    "Google Ads":     ("#fef3c7", "#854d0e"),
    "Website Design": ("#dcfce7", "#15803d"),  # green
    "Consulting":     ("#ede9fe", "#5b21b6"),  # purple
    "Content":        ("#fed7aa", "#9a3412"),  # orange
    "Local SEO":      ("#bbf7d0", "#14532d"),
}


def render_service_chips(services):
    if not services:
        return '<span class="muted">—</span>'
    out = []
    for s in services:
        bg, fg = SERVICE_COLORS.get(s, ("#f1f5f9", "#475569"))
        out.append(f'<span class="svc-chip" style="background:{bg};color:{fg}">{esc(s)}</span>')
    return "".join(out)


def render_service_block(cd, service_line):
    """Render one service line as a labeled block with Campaign Stage +
    Performance cards. Each client can have many service blocks stacked
    inside its expanded row."""
    service_type = service_line.get("type", "seo")
    # seo (and the seo_sprint project alias) render from the WQA-driven project plan
    seo_like = service_type in ("seo", "seo_sprint")
    label = service_label(service_type)
    color = service_color(service_type)
    icon = service_icon(service_type)
    started = service_line.get("started_at") or ""
    sline_status = service_line.get("status", "active")
    engagement_months = service_line.get("engagement_months", 12)

    # --- Campaign Stage card per service ---
    if seo_like:
        # SEO uses the existing WQA project plan for stage + progress.
        plan = cd["plan_info"]["plan"] if cd["plan_info"] else None
        active_project = cd["active_project"]
        project_start = (active_project or {}).get("start_date", started)
        if plan and project_start:
            m = current_month_for(project_start)
            stage = stage_for_service("seo", m)
            statuses = Counter(default_status(d) for d in plan["deliverables"])
            done = statuses["completed"] + statuses["approved"]
            delayed = statuses["delayed"]
            progress_pct = round(100 * done / len(plan["deliverables"])) if plan["deliverables"] else 0
            cells = []
            for i in range(1, engagement_months + 1):
                if i < m: cells.append(f'<div class="d3-cell done">{i}</div>')
                elif i == m: cells.append(f'<div class="d3-cell current">{i}</div>')
                else: cells.append(f'<div class="d3-cell future">{i}</div>')
            timeline_html = '<div class="d3-strip">' + "".join(cells) + '</div>'
            card_stage = (
                f'<a class="client-card-3 card-stage" href="#client/{esc(cd["slug"])}">'
                  f'<div class="cc-label">Campaign Stage</div>'
                  f'{timeline_html}'
                  f'<div class="d3-stage-info">'
                    f'<div class="d3-stage-name">{esc(stage)}</div>'
                    f'<div class="d3-stage-stats">Month {m} of {engagement_months} · {progress_pct}% complete</div>'
                  f'</div>'
                  f'<div class="d3-stage-stats" style="margin-top:6px;">'
                    f'<span><strong>{statuses["scheduled"]}</strong> scheduled</span> · '
                    f'<span><strong>{statuses["working"]}</strong> working</span> · '
                    f'<span style="color:#dc2626;"><strong>{delayed}</strong> delayed</span> · '
                    f'<span style="color:#16a34a;"><strong>{done}</strong> done</span>'
                  f'</div>'
                f'</a>'
            )
        else:
            card_stage = (
                f'<div class="client-card-3 card-stage card-empty">'
                  f'<div class="cc-label">Campaign Stage</div>'
                  f'<div class="cc-empty-msg">No project plan yet</div>'
                  f'<div class="cc-empty-hint">Run the WQA + project plan workflow to populate</div>'
                f'</div>'
            )
    else:
        # PPC / LSA / Social: read the paid-media plan if one was generated
        # via build_paid_media_plan.py. Falls back to a generic stub if no
        # plan exists yet for this service.
        paid_plan_path = os.path.join(ROOT, "clients", cd["slug"], "paid-media",
                                       f"{service_type}-project-plan.json")
        paid_plan = None
        if os.path.exists(paid_plan_path):
            try: paid_plan = json.load(open(paid_plan_path))
            except Exception: paid_plan = None

        if started:
            try:
                m = current_month_for(started)
            except Exception:
                m = 1
            stage = stage_for_service(service_type, m)
            cells = []
            for i in range(1, engagement_months + 1):
                if i < m: cells.append(f'<div class="d3-cell done">{i}</div>')
                elif i == m: cells.append(f'<div class="d3-cell current">{i}</div>')
                else: cells.append(f'<div class="d3-cell future">{i}</div>')
            timeline_html = '<div class="d3-strip">' + "".join(cells) + '</div>'

            # If a real plan exists, render the same Stage card shape as SEO:
            # timeline + stage + progress + status counters.
            if paid_plan:
                delivs = paid_plan.get("deliverables") or []
                statuses = Counter(default_status(d) for d in delivs)
                done = statuses["completed"] + statuses["approved"]
                delayed = statuses["delayed"]
                progress_pct = round(100 * done / len(delivs)) if delivs else 0
                card_stage = (
                    f'<div class="client-card-3 card-stage">'
                      f'<div class="cc-label">Campaign Stage</div>'
                      f'{timeline_html}'
                      f'<div class="d3-stage-info">'
                        f'<div class="d3-stage-name">{esc(stage)}</div>'
                        f'<div class="d3-stage-stats">Month {m} of {engagement_months} · {progress_pct}% complete</div>'
                      f'</div>'
                      f'<div class="d3-stage-stats" style="margin-top:6px;">'
                        f'<span><strong>{statuses["scheduled"]}</strong> scheduled</span> · '
                        f'<span><strong>{statuses["working"]}</strong> working</span> · '
                        f'<span style="color:#dc2626;"><strong>{delayed}</strong> delayed</span> · '
                        f'<span style="color:#16a34a;"><strong>{done}</strong> done</span>'
                      f'</div>'
                    f'</div>'
                )
            else:
                card_stage = (
                    f'<div class="client-card-3 card-stage">'
                      f'<div class="cc-label">Campaign Stage</div>'
                      f'{timeline_html}'
                      f'<div class="d3-stage-info">'
                        f'<div class="d3-stage-name">{esc(stage)}</div>'
                        f'<div class="d3-stage-stats">Month {m} of {engagement_months}</div>'
                      f'</div>'
                      f'<div class="d3-stage-stats" style="margin-top:6px;color:#94a3b8;font-style:italic;">'
                        f'Run /paid-media-plan to generate the project plan'
                      f'</div>'
                    f'</div>'
                )
        else:
            card_stage = (
                f'<div class="client-card-3 card-stage card-empty">'
                  f'<div class="cc-label">Campaign Stage</div>'
                  f'<div class="cc-empty-msg">Service line configured</div>'
                  f'<div class="cc-empty-hint">Add started_at to begin tracking</div>'
                f'</div>'
            )

    # --- Performance card per service ---
    if seo_like:
        perf = real_perf(cd["slug"])
        def render_ring(value, label):
            if value is None:
                return (f'<div class="d2-perf-cell"><div class="ring">'
                        f'<svg width="80" height="80" viewBox="0 0 80 80">'
                        f'<circle cx="40" cy="40" r="33" fill="none" stroke="#e5e7eb" stroke-width="8"/></svg>'
                        f'<div class="ring-center"><div class="ring-num" style="font-size:14px;color:#94a3b8">—</div></div>'
                        f'</div><div class="ring-label">{esc(label)}</div></div>')
            magnitude = min(abs(value), 100) / 100.0
            circumference = 207
            offset = circumference * (1 - magnitude)
            track_color = "#dcfce7" if value >= 0 else "#fee2e2"
            stroke_color = "#16a34a" if value >= 0 else "#dc2626"
            num_color = "#16a34a" if value >= 0 else "#dc2626"
            arrow = "▲" if value >= 0 else "▼"
            sign = "+" if value >= 0 else ""
            return (f'<div class="d2-perf-cell"><div class="ring">'
                    f'<svg width="80" height="80" viewBox="0 0 80 80">'
                    f'<circle cx="40" cy="40" r="33" fill="none" stroke="{track_color}" stroke-width="8"/>'
                    f'<circle cx="40" cy="40" r="33" fill="none" stroke="{stroke_color}" stroke-width="8" '
                    f'stroke-dasharray="{circumference}" stroke-dashoffset="{offset:.1f}" stroke-linecap="round" '
                    f'transform="rotate(-90 40 40)"/></svg>'
                    f'<div class="ring-center"><div class="ring-num" style="color:{num_color}">{arrow} {sign}{abs(value):.0f}%</div></div>'
                    f'</div><div class="ring-label">{esc(label)}</div></div>')
        if perf.get("is_real"):
            card_perf = (
                f'<a class="client-card-3 card-perf" href="#reporting/{esc(cd["slug"])}/seo">'
                  f'<div class="cc-label">Performance · Organic Traffic</div>'
                  f'<div class="d2-perf-trio">'
                    f'{render_ring(perf.get("wow"), "WoW clicks")}'
                    f'{render_ring(perf.get("mom"), "MoM organic")}'
                    f'{render_ring(perf.get("yoy"), "YoY organic")}'
                  f'</div>'
                  f'<div class="cc-perf-cta">View full report →</div>'
                f'</a>'
            )
        else:
            card_perf = (
                f'<a class="client-card-3 card-perf card-not-connected" href="#reporting/{esc(cd["slug"])}/seo">'
                  f'<div class="cc-label">Performance · Organic Traffic</div>'
                  f'<div class="cc-not-connected">'
                    f'<div class="cc-not-connected-icon">⊘</div>'
                    f'<div class="cc-not-connected-title">Not Connected</div>'
                    f'<div class="cc-not-connected-msg">Wire up Ahrefs + GSC connectors to populate</div>'
                  f'</div>'
                f'</a>'
            )
    elif service_type == "social_ads":
        # Try to load cached Facebook ads metrics from
        # clients/{slug}/analytics/social_ads_facebook_summary.json
        # Falls back to "Not Connected" with action.
        fb_path = os.path.join(ROOT, "clients", cd["slug"], "analytics", "social_ads_facebook_summary.json")
        fb_data = None
        if os.path.exists(fb_path):
            try: fb_data = json.load(open(fb_path))
            except Exception: fb_data = None
        if fb_data:
            spend = fb_data.get("spend_last_30d") or 0
            convs = fb_data.get("conversions_last_30d") or 0
            roas  = fb_data.get("roas_last_30d")  # may be None for lead-gen accounts
            mom   = fb_data.get("spend_mom_pct")
            convs_mom = fb_data.get("conversions_mom_pct")
            # ROAS isn't meaningful for lead-gen accounts (no action_values).
            # Show CPL instead when revenue is null — cost per lead is the
            # canonical efficiency metric for lead-gen FB.
            if roas is not None:
                third_val = f'{roas:.2f}x'
                third_lbl = 'ROAS'
            else:
                cpl = (spend / convs) if convs else None
                third_val = f'${cpl:,.0f}' if cpl else '—'
                third_lbl = 'Cost per lead'
            spend_str = f'${spend:,.0f}'
            spend_sub = f'{mom:+.0f}% MoM' if mom is not None else ''
            convs_sub = f'{convs_mom:+.0f}% MoM' if convs_mom is not None else ''
            def _color(pct):
                if pct is None: return '#64748b'
                return '#16a34a' if pct >= 0 else '#dc2626'
            card_perf = (
                f'<a class="client-card-3 card-perf" href="#reporting/{esc(cd["slug"])}/social_ads">'
                  f'<div class="cc-label">Performance · Facebook Ads (last 30d)</div>'
                  f'<div class="d2-perf-trio">'
                    f'<div class="d2-perf-cell">'
                      f'<div style="font-size:20px;font-weight:700">{spend_str}</div>'
                      f'<div class="ring-label">Spend</div>'
                      f'<div style="font-size:10px;color:{_color(mom)};margin-top:2px">{spend_sub}</div>'
                    f'</div>'
                    f'<div class="d2-perf-cell">'
                      f'<div style="font-size:20px;font-weight:700">{convs:,}</div>'
                      f'<div class="ring-label">Conversions</div>'
                      f'<div style="font-size:10px;color:{_color(convs_mom)};margin-top:2px">{convs_sub}</div>'
                    f'</div>'
                    f'<div class="d2-perf-cell">'
                      f'<div style="font-size:20px;font-weight:700">{third_val}</div>'
                      f'<div class="ring-label">{third_lbl}</div>'
                    f'</div>'
                  f'</div>'
                  f'<div class="cc-perf-cta">View Facebook Ads report →</div>'
                f'</a>'
            )
        else:
            card_perf = (
                f'<a class="client-card-3 card-perf card-not-connected" href="#reporting/{esc(cd["slug"])}/social_ads">'
                  f'<div class="cc-label">Performance · Facebook Ads</div>'
                  f'<div class="cc-not-connected">'
                    f'<div class="cc-not-connected-icon">⊘</div>'
                    f'<div class="cc-not-connected-title">Not Connected</div>'
                    f'<div class="cc-not-connected-msg">Run /facebook-ads-report or wire Windsor.ai Facebook destination</div>'
                  f'</div>'
                f'</a>'
            )
    elif service_type == "ppc":
        # PPC service block — load cached Google Ads metrics. Mirrors the
        # social_ads card pattern. Falls back to "Not Connected" with an
        # action hint if no cache exists yet.
        ppc_path = os.path.join(ROOT, "clients", cd["slug"], "analytics", "ppc_google_ads_summary.json")
        ppc_data = None
        if os.path.exists(ppc_path):
            try: ppc_data = json.load(open(ppc_path))
            except Exception: ppc_data = None
        if ppc_data:
            spend = ppc_data.get("spend_last_30d") or 0
            convs = ppc_data.get("conversions_last_30d") or 0
            cpa   = ppc_data.get("cpa")
            mom_spend = ppc_data.get("spend_mom_pct")
            mom_convs = ppc_data.get("conversions_mom_pct")
            spend_str = f'${spend:,.0f}'
            spend_sub = f'{mom_spend:+.0f}% MoM' if mom_spend is not None else ''
            convs_sub = f'{mom_convs:+.0f}% MoM' if mom_convs is not None else ''
            cpa_str   = f'${cpa:,.0f}' if cpa else '—'
            def _color(pct):
                if pct is None: return '#64748b'
                return '#16a34a' if pct >= 0 else '#dc2626'
            card_perf = (
                f'<a class="client-card-3 card-perf" href="#reporting/{esc(cd["slug"])}/ppc">'
                  f'<div class="cc-label">Performance · Google Ads (last 30d)</div>'
                  f'<div class="d2-perf-trio">'
                    f'<div class="d2-perf-cell">'
                      f'<div style="font-size:20px;font-weight:700">{spend_str}</div>'
                      f'<div class="ring-label">Spend</div>'
                      f'<div style="font-size:10px;color:{_color(mom_spend)};margin-top:2px">{spend_sub}</div>'
                    f'</div>'
                    f'<div class="d2-perf-cell">'
                      f'<div style="font-size:20px;font-weight:700">{convs:,.0f}</div>'
                      f'<div class="ring-label">Conversions</div>'
                      f'<div style="font-size:10px;color:{_color(mom_convs)};margin-top:2px">{convs_sub}</div>'
                    f'</div>'
                    f'<div class="d2-perf-cell">'
                      f'<div style="font-size:20px;font-weight:700">{cpa_str}</div>'
                      f'<div class="ring-label">Cost per acq.</div>'
                    f'</div>'
                  f'</div>'
                  f'<div class="cc-perf-cta">View Google Ads report →</div>'
                f'</a>'
            )
        else:
            card_perf = (
                f'<a class="client-card-3 card-perf card-not-connected" href="#reporting/{esc(cd["slug"])}/ppc">'
                  f'<div class="cc-label">Performance · Google Ads</div>'
                  f'<div class="cc-not-connected">'
                    f'<div class="cc-not-connected-icon">⊘</div>'
                    f'<div class="cc-not-connected-title">Not Connected</div>'
                    f'<div class="cc-not-connected-msg">Run the Google Ads pull to populate this card</div>'
                  f'</div>'
                f'</a>'
            )
    else:
        # LSA + other services — placeholder (LSA folded into PPC tab in
        # Reporting view, so its block isn't normally rendered).
        card_perf = (
            f'<div class="client-card-3 card-perf card-not-connected">'
              f'<div class="cc-label">Performance · {esc(label)}</div>'
              f'<div class="cc-not-connected">'
                f'<div class="cc-not-connected-icon">⊘</div>'
                f'<div class="cc-not-connected-title">Reporting Coming Soon</div>'
                f'<div class="cc-not-connected-msg">{esc(label)} reporting template ships in Phase 2</div>'
              f'</div>'
            f'</div>'
        )

    # --- Per-service header strip (label, badge, dates) ---
    # NOTE: monthly_retainer intentionally NOT displayed here. We don't want
    # internal team members seeing what each client is being charged. The
    # retainer field is retained in clients.json for ownership/revenue
    # reporting elsewhere (separate access).
    started_chunk = ""
    if started:
        started_chunk = (
            '<span class="service-block-meta">Started '
            + esc(format_date_mmddyy(started))
            + '</span>'
        )
    header = (
        f'<div class="service-block-header" style="border-left:4px solid {color};">'
          f'<span class="service-block-icon">{icon}</span>'
          f'<span class="service-block-label" style="color:{color}">{esc(label)}</span>'
          f'<span class="service-block-status">{esc(sline_status)}</span>'
          f'{started_chunk}'
        f'</div>'
    )

    return (
        f'<div class="service-block">'
          f'{header}'
          f'<div class="service-block-cards">{card_stage}{card_perf}</div>'
        f'</div>'
    )


def render_client_row(cd):
    """One client = one collapsible table row. Summary shows columns;
    expanded shows one service block per service line."""
    client = cd["client"]
    plan = cd["plan_info"]["plan"] if cd["plan_info"] else None
    active_project = cd["active_project"]
    company = client.get("company_name", "")
    cf = client.get("custom_fields") or {}
    service_lines = cd.get("service_lines") or []
    services = [service_label(s.get("type", "seo")) for s in service_lines] or (cf.get("services") or [])
    project_start = (active_project or {}).get("start_date", "")
    status_label, _ = STATUS_DISPLAY.get(cd["status"], STATUS_DISPLAY["unknown"])

    # Trend in the summary row: SEO MoM for now (legacy column).
    perf = real_perf(cd["slug"])
    trend_html = render_perf_delta(perf.get("mom"))

    # Per-service conversions trends (PPC + FB Ads) — read from each
    # service's cached summary and render as compact "<count> · <±pct>%"
    # mini-pills. When no data exists, show "—".
    def _conv_pill(count, mom_pct):
        if count is None:
            return '<span class="muted">—</span>'
        if mom_pct is None:
            return f'<span class="conv-pill"><strong>{count:,.0f}</strong></span>'
        sign = "+" if mom_pct >= 0 else ""
        color = "#16a34a" if mom_pct >= 0 else "#dc2626"
        arrow = "▲" if mom_pct >= 0 else "▼"
        return (f'<span class="conv-pill">'
                f'<strong>{count:,.0f}</strong> '
                f'<span style="color:{color};font-size:11px;font-weight:700">{arrow} {sign}{mom_pct:.0f}%</span>'
                f'</span>')

    ppc_conv_count = None; ppc_conv_mom = None
    fb_conv_count  = None; fb_conv_mom  = None
    ppc_path = os.path.join(ROOT, "clients", cd["slug"], "analytics", "ppc_google_ads_summary.json")
    if os.path.exists(ppc_path):
        try:
            ppc_d = json.load(open(ppc_path))
            ppc_conv_count = ppc_d.get("conversions_last_30d")
            ppc_conv_mom   = ppc_d.get("conversions_mom_pct")
        except Exception:
            pass
    fb_path = os.path.join(ROOT, "clients", cd["slug"], "analytics", "social_ads_facebook_summary.json")
    if os.path.exists(fb_path):
        try:
            fb_d = json.load(open(fb_path))
            fb_conv_count = fb_d.get("conversions_last_30d")
            fb_conv_mom   = fb_d.get("conversions_mom_pct")
        except Exception:
            pass
    ppc_conv_html = _conv_pill(ppc_conv_count, ppc_conv_mom)
    fb_conv_html  = _conv_pill(fb_conv_count, fb_conv_mom)

    # ----- Card 2: Campaign Stage (Design 3 — Timeline strip) -----
    if plan and project_start:
        m = current_month_for(project_start)
        stage = stage_for_month(m)
        statuses = Counter(default_status(d) for d in plan["deliverables"])
        done = statuses["completed"] + statuses["approved"]
        delayed = statuses["delayed"]
        progress_pct = round(100 * done / len(plan["deliverables"])) if plan["deliverables"] else 0
        # Build 12-segment timeline
        cells = []
        for i in range(1, 13):
            if i < m: cells.append(f'<div class="d3-cell done">{i}</div>')
            elif i == m: cells.append(f'<div class="d3-cell current">{i}</div>')
            else: cells.append(f'<div class="d3-cell future">{i}</div>')
        timeline_html = '<div class="d3-strip">' + "".join(cells) + '</div>'
        card_stage = (
            f'<a class="client-card-3 card-stage" href="#client/{esc(cd["slug"])}">'
              f'<div class="cc-label">Campaign Stage</div>'
              f'{timeline_html}'
              f'<div class="d3-stage-info">'
                f'<div class="d3-stage-name">{esc(stage)}</div>'
                f'<div class="d3-stage-stats">Month {m} of 12 · {progress_pct}% complete</div>'
              f'</div>'
              f'<div class="d3-stage-stats" style="margin-top:6px;">'
                f'<span><strong>{statuses["scheduled"]}</strong> scheduled</span> · '
                f'<span><strong>{statuses["working"]}</strong> working</span> · '
                f'<span style="color:#dc2626;"><strong>{delayed}</strong> delayed</span> · '
                f'<span style="color:#16a34a;"><strong>{done}</strong> done</span>'
              f'</div>'
            f'</a>'
        )
    else:
        card_stage = (
            f'<a class="client-card-3 card-stage card-empty" href="#client/{esc(cd["slug"])}">'
              f'<div class="cc-label">Campaign Stage</div>'
              f'<div class="cc-empty-msg">No project plan yet</div>'
              f'<div class="cc-empty-hint">Run the WQA + project plan workflow to populate</div>'
            f'</a>'
        )

    # ----- Card 3: Performance Snapshot (Design 2 — 3 mini progress rings) -----
    perf = real_perf(cd["slug"])

    def render_ring(value, label):
        """Render a small SVG ring with the % value in the center."""
        if value is None:
            return (f'<div class="d2-perf-cell">'
                    f'<div class="ring">'
                      f'<svg width="80" height="80" viewBox="0 0 80 80">'
                        f'<circle cx="40" cy="40" r="33" fill="none" stroke="#e5e7eb" stroke-width="8"/>'
                      f'</svg>'
                      f'<div class="ring-center"><div class="ring-num" style="font-size:14px;color:#94a3b8">—</div></div>'
                    f'</div>'
                    f'<div class="ring-label">{esc(label)}</div></div>')
        # Clamp magnitude to 100 for ring fill; color by sign
        magnitude = min(abs(value), 100) / 100.0
        circumference = 207  # 2 * pi * 33
        offset = circumference * (1 - magnitude)
        track_color = "#dcfce7" if value >= 0 else "#fee2e2"
        stroke_color = "#16a34a" if value >= 0 else "#dc2626"
        num_color = "#16a34a" if value >= 0 else "#dc2626"
        arrow = "▲" if value >= 0 else "▼"
        sign = "+" if value >= 0 else ""
        return (f'<div class="d2-perf-cell">'
                f'<div class="ring">'
                  f'<svg width="80" height="80" viewBox="0 0 80 80">'
                    f'<circle cx="40" cy="40" r="33" fill="none" stroke="{track_color}" stroke-width="8"/>'
                    f'<circle cx="40" cy="40" r="33" fill="none" stroke="{stroke_color}" stroke-width="8" '
                    f'stroke-dasharray="{circumference}" stroke-dashoffset="{offset:.1f}" stroke-linecap="round" '
                    f'transform="rotate(-90 40 40)"/>'
                  f'</svg>'
                  f'<div class="ring-center">'
                    f'<div class="ring-num" style="color:{num_color}">{arrow} {sign}{abs(value):.0f}%</div>'
                  f'</div>'
                f'</div>'
                f'<div class="ring-label">{esc(label)}</div></div>')

    if perf.get("is_real"):
        card_perf = (
            f'<a class="client-card-3 card-perf" href="#reporting/{esc(cd["slug"])}">'
              f'<div class="cc-label">Performance · Organic Traffic</div>'
              f'<div class="d2-perf-trio">'
                f'{render_ring(perf.get("wow"), "WoW clicks")}'
                f'{render_ring(perf.get("mom"), "MoM organic")}'
                f'{render_ring(perf.get("yoy"), "YoY organic")}'
              f'</div>'
              f'<div class="cc-perf-cta">View full report →</div>'
            f'</a>'
        )
    else:
        card_perf = (
            f'<a class="client-card-3 card-perf card-not-connected" href="#reporting/{esc(cd["slug"])}">'
              f'<div class="cc-label">Performance · Organic Traffic</div>'
              f'<div class="cc-not-connected">'
                f'<div class="cc-not-connected-icon">⊘</div>'
                f'<div class="cc-not-connected-title">Not Connected</div>'
                f'<div class="cc-not-connected-msg">Wire up Ahrefs + GSC connectors to populate</div>'
              f'</div>'
              f'<div class="cc-perf-cta">Connect data →</div>'
            f'</a>'
        )

    # Build summary row (table columns) — clickable to expand
    # Client name is plain text; clicking the row toggles the accordion.
    # To open the full client dashboard, click the Campaign Stage card inside.
    summary_html = (
        f'<summary>'
          f'<span class="ct-cell ct-caret">▸</span>'
          f'<span class="ct-cell ct-name">{esc(company)} <span class="ct-expand-hint"></span></span>'
          f'<span class="ct-cell ct-start">{esc(format_date_mmddyy(project_start))}</span>'
          f'<span class="ct-cell ct-status">'
            f'<span class="status-pill" style="background:{cd["color"]}1A;color:{cd["color"]};border:1px solid {cd["color"]}40;">'
              f'<span class="status-dot" style="background:{cd["color"]}"></span>{esc(status_label)}'
            f'</span>'
          f'</span>'
          f'<span class="ct-cell ct-services">{render_service_chips(services)}</span>'
          f'<span class="ct-cell ct-trend" title="SEO organic traffic, MoM%">{trend_html}</span>'
          f'<span class="ct-cell ct-ppc-conv" title="Google Ads conversions, last 30d · MoM%">{ppc_conv_html}</span>'
          f'<span class="ct-cell ct-fb-conv" title="Facebook Ads conversions, last 30d · MoM%">{fb_conv_html}</span>'
          # Live Content / Live Links counts are computed from the sheet
          # caches at build time. Cached row counts feed straight in;
          # if the cache is missing we show "—" so it's visually distinct
          # from a real zero.
          f'<span class="ct-cell ct-content">{_sheet_live_count_html(cd, "content")}</span>'
          f'<span class="ct-cell ct-links">{_sheet_live_count_html(cd, "links")}</span>'
        f'</summary>'
    )

    # Multi-service: render one service-block per service line. The old
    # single-Stage + single-Perf cards (card_stage, card_perf, computed
    # above) are now superseded by render_service_block which handles
    # per-service rendering. They are kept for layout-state continuity
    # (e.g., empty-state messages) but no longer emitted directly.
    #
    # NOTE: LSA is intentionally NOT given its own service block here —
    # LSA reporting + tracking is folded into the PPC tab in the Reporting
    # view (since LSA data lives in Google Ads). The LSA service_line
    # still exists in clients.json for PM tracking, but the visible
    # client-overview surface treats LSA as part of PPC.
    visible_service_lines = [
        sl for sl in service_lines if sl.get("type") != "lsa"
    ]
    if visible_service_lines:
        blocks_html = "".join(render_service_block(cd, sl) for sl in visible_service_lines)
    else:
        # Empty service_lines (shouldn't happen with derive_service_lines
        # fallback, but defensive) — fall back to the legacy single-row
        # render to avoid blank space.
        blocks_html = f'<div class="client-row-cards">{card_stage}{card_perf}</div>'

    return (f'<details class="client-row" data-status="{cd["status"]}" data-name="{esc(company.lower())}">'
            f'{summary_html}'
            f'<div class="client-row-services">{blocks_html}</div>'
            f'</details>')

grid_active = [c for c in client_data if c["status"] == "active"]
grid_onboarding = [c for c in client_data if c["status"] == "onboarding"]
grid_needs_attn = [c for c in client_data if c["status"] == "needs_attention"]
grid_inactive = [c for c in client_data if c["status"] in ("inactive", "unknown")]

clients_grid_html = (
    '<header class="page-header"><h1>Clients</h1>'
    '<div class="sub">' + str(len(client_data)) + ' total · '
      + str(len(grid_active)) + ' active · ' + str(len(grid_onboarding)) + ' onboarding · '
      + str(len(grid_needs_attn)) + ' need attention · '
      + str(len(grid_inactive)) + ' inactive</div></header>'
    '<div class="clients-toolbar">'
      '<input type="text" id="client-search" placeholder="Search clients by name…" />'
      '<label class="toggle-switch" title="Show inactive clients">'
        '<input type="checkbox" id="show-inactive" />'
        '<span class="toggle-slider"></span>'
        '<span class="toggle-label">Show inactive clients</span>'
      '</label>'
    '</div>'
    '<div class="client-table" id="client-rows-container">'
      '<div class="ct-header">'
        '<span class="ct-cell ct-caret"></span>'
        '<span class="ct-cell ct-name">Client</span>'
        '<span class="ct-cell ct-start">Start Date</span>'
        '<span class="ct-cell ct-status">Status</span>'
        '<span class="ct-cell ct-services">Services</span>'
        '<span class="ct-cell ct-trend">SEO Trend</span>'
        '<span class="ct-cell ct-ppc-conv">PPC Conv (30d)</span>'
        '<span class="ct-cell ct-fb-conv">FB Conv (30d)</span>'
        '<span class="ct-cell ct-content">Live Content</span>'
        '<span class="ct-cell ct-links">Live Links</span>'
      '</div>'
      + ''.join(render_client_row(cd) for cd in client_data) +
    '</div>'
)

# Build per-client reporting panels for the top-level Reporting page.
# NOTE: We render a panel for EVERY client, even those without an SEO project
# plan. Reason: paid-media clients (Social Ads / PPC) may have full reporting
# data even without an SEO WQA plan generated yet. The reporting view itself
# handles the no-plan case by showing "Not Connected" empty states per
# service that has no data.
reporting_panels = []
reporting_client_options = []
for cd in client_data:
    plan_info = cd["plan_info"]
    if plan_info:
        plan = plan_info["plan"]
        sorted_dels = sorted(plan["deliverables"], key=lambda d: d.get("due_date") or "9999-99-99")
    else:
        sorted_dels = []  # no SEO plan yet; reporting view still renders for paid-media
    reporting_panels.append(render_reporting_view(cd, sorted_dels))
    reporting_client_options.append(
        f'<option value="{esc(cd["slug"])}">{esc(cd["client"].get("company_name", ""))}</option>'
    )

if reporting_panels:
    reporting_html = (
        '<header class="page-header"><h1>Reporting</h1>'
          '<div class="sub">Per-client SEO performance — GA4 · Search Console · Google Business Profile</div>'
        '</header>'
        '<div class="reporting-picker">'
          '<label>Client:</label>'
          '<select id="reporting-client-picker">'
            + "".join(reporting_client_options) +
          '</select>'
        '</div>'
        '<div class="reporting-panels" id="reporting-panels">'
          + "".join(reporting_panels) +
        '</div>'
    )
else:
    reporting_html = (
        '<header class="page-header"><h1>Reporting</h1>'
          '<div class="sub">Per-client SEO performance</div>'
        '</header>'
        '<div class="placeholder">'
          '<div class="placeholder-icon">📊</div><h3>No client reports yet</h3>'
          '<p>Once you have an active client with a project plan, their SEO report will appear here.</p>'
        '</div>'
    )

agency_name = esc(agency.get("name", "Agency"))
team_rows = ''.join(
    f'<tr><td><strong>{esc(t.get("name",""))}</strong></td><td>{esc(t.get("email",""))}</td>'
    f'<td>{esc(t.get("title") or t.get("role") or "")}</td>'
    f'<td>{esc(", ".join(t.get("skills") or []))}</td></tr>'
    for t in team
)
# Build Admin: two sub-tabs (Clients table + People table)
# CLIENTS sub-tab: spreadsheet-style table of all clients
admin_status_cell = {
    "active":     ('#dcfce7', '#15803d', 'Active'),
    "onboarding": ('#fef3c7', '#92400e', 'Onboarding'),
    "inactive":   ('#fee2e2', '#b91c1c', 'Inactive'),
    "unknown":    ('#f1f5f9', '#475569', 'Unknown'),
}

admin_client_rows = []
for cd in client_data:
    client = cd["client"]
    cf = client.get("custom_fields") or {}
    company = client.get("company_name", "")
    website = client.get("website", "")
    website_short = website.replace("https://", "").replace("http://", "")
    drive_folder = client.get("drive_folder") or cf.get("assets_folder") or ""
    workbook = cf.get("access_checklist_doc") or ""
    contract_start = cf.get("contract_start_date") or client.get("contract_start_date") or ""
    contract_start_disp = format_date_mmddyy(contract_start) if contract_start else "—"
    poc = client.get("contact_name") or ""
    contact = client.get("email") or ""
    service = client.get("service_type") or "—"
    description = cf.get("service_type_note") or ""
    s_bg, s_fg, s_label = admin_status_cell.get(cd["status"], admin_status_cell["unknown"])

    admin_client_rows.append(
        f'<div class="row admin-row">'
          f'<div class="cell cell-ac-status"><span class="status-pill" style="background:{s_bg};color:{s_fg};cursor:default;"><span class="pill-label">{s_label}</span></span></div>'
          f'<div class="cell cell-ac-name"><a href="#client/{esc(cd["slug"])}"><strong>{esc(company)}</strong></a></div>'
          f'<div class="cell cell-ac-home">' + (f'<a href="{esc(website)}" target="_blank">{esc(website_short)}</a>' if website else '—') + '</div>'
          f'<div class="cell cell-ac-workbook">' + (f'<a href="{esc(workbook)}" target="_blank">workbook</a>' if workbook else '<span class="muted">—</span>') + '</div>'
          f'<div class="cell cell-ac-folder">' + (f'<a href="{esc(drive_folder)}" target="_blank">folder</a>' if drive_folder else '<span class="muted">—</span>') + '</div>'
          f'<div class="cell cell-ac-start">{esc(contract_start_disp)}</div>'
          f'<div class="cell cell-ac-desc">{esc(description) or "—"}</div>'
          f'<div class="cell cell-ac-poc">{esc(poc)}</div>'
          f'<div class="cell cell-ac-contact">{esc(contact)}</div>'
          f'<div class="cell cell-ac-scope">{esc(service)}</div>'
        f'</div>'
    )

admin_clients_table = (
    '<div class="task-table admin-clients-table">'
      '<div class="table-header">'
        '<div class="cell cell-ac-status">Status</div>'
        '<div class="cell cell-ac-name">Client</div>'
        '<div class="cell cell-ac-home">Homepage</div>'
        '<div class="cell cell-ac-workbook">Workbook</div>'
        '<div class="cell cell-ac-folder">Folder</div>'
        '<div class="cell cell-ac-start">Start Date</div>'
        '<div class="cell cell-ac-desc">Description</div>'
        '<div class="cell cell-ac-poc">POC</div>'
        '<div class="cell cell-ac-contact">Contact</div>'
        '<div class="cell cell-ac-scope">Scope</div>'
      '</div>'
      '<div class="flat-body">' + "".join(admin_client_rows) + '</div>'
    '</div>'
)

# PEOPLE sub-tab: table of entire team roster (cross-client). Clicking a name → person page.
# Load = tasks scheduled for the current month of each client's engagement, owned by this person.
people_rows = []
for person in TEAM_ROSTER:
    initial = person["name"][0].upper()
    skills_str = " · ".join(person["skills"])
    capacity = person.get("monthly_capacity") or 50
    # Count this-month load + total
    this_month_load = 0
    all_assigned = 0
    for cd in client_data:
        plan = cd["plan_info"]
        if not plan: continue
        proj = cd.get("active_project") or {}
        client_current_month = current_month_for(proj.get("start_date", ""))
        for d in plan["plan"]["deliverables"]:
            if d.get("assigned_to_email") != person["email"]: continue
            all_assigned += 1
            if d.get("scheduled_month") == client_current_month:
                this_month_load += 1

    pct = round(100 * this_month_load / capacity) if capacity else 0
    pct_clamp = min(pct, 100)
    if pct >= 100: bar_color = "#dc2626"   # red — over capacity
    elif pct >= 70: bar_color = "#f59e0b"  # yellow — heavy
    else: bar_color = "#16a34a"            # green — sustainable
    load_html = (
        f'<div class="load-cell">'
          f'<div class="load-bar-track">'
            f'<div class="load-bar-fill" style="width:{pct_clamp}%;background:{bar_color}"></div>'
          f'</div>'
          f'<div class="load-meta"><strong style="color:{bar_color}">{pct}%</strong> · '
            f'{this_month_load} / {capacity} this month <span class="muted">({all_assigned} total)</span></div>'
        f'</div>'
    )

    people_rows.append(
        f'<tr>'
          f'<td><div style="display:flex;align-items:center;gap:10px;">'
            f'<span class="avatar">{esc(initial)}</span>'
            f'<a href="#person/{esc(person["email"])}"><strong>{esc(person["name"])}</strong></a>'
          f'</div></td>'
          f'<td><a href="mailto:{esc(person["email"])}">{esc(person["email"])}</a></td>'
          f'<td>{esc(person["title"])}</td>'
          f'<td style="font-size:12px;color:var(--muted);">{esc(skills_str)}</td>'
          f'<td class="load-cell-wrap" data-load-pct="{pct}">{load_html}</td>'
          f'<td><a class="btn-mini" href="#person/{esc(person["email"])}">View tasks →</a></td>'
        f'</tr>'
    )
# Sort by load descending so overloaded shows first
people_rows.sort(key=lambda r: -int(re.search(r'data-load-pct="(\d+)"', r).group(1)))

admin_html = (
    '<header class="page-header"><h1>Admin</h1><div class="sub">Manage clients and team</div></header>'
    '<div class="view-tabs" data-admin-tabs>'
      '<button class="view-tab active" data-admin-tab="clients">Clients</button>'
      '<button class="view-tab" data-admin-tab="people">People</button>'
    '</div>'
    '<div class="admin-panel active" data-admin-panel="clients">'
      f'<div class="muted" style="margin-bottom:8px;font-size:12px;">All clients · {len(client_data)} total</div>'
      f'{admin_clients_table}'
    '</div>'
    '<div class="admin-panel" data-admin-panel="people" style="display:none">'
      f'<div class="muted" style="margin-bottom:8px;font-size:12px;">All team members · {len(TEAM_ROSTER)} total — click a name to see all tasks assigned to them across every client.</div>'
      f'<table class="summary-table people-roster-table">'
        f'<thead><tr><th>Name</th><th>Email</th><th>Role</th><th>Specialties</th><th>Load (this month)</th><th></th></tr></thead>'
        f'<tbody>{"".join(people_rows)}</tbody>'
      f'</table>'
    '</div>'
)

client_pages = []
for cd in client_data:
    page_html = render_client_view(cd)
    client_pages.append(
        f'<div class="page" data-page="client/{esc(cd["slug"])}" data-client="{esc(cd["slug"])}" style="display:none">'
        f'<div class="breadcrumb"><a href="#clients">← All clients</a></div>'
        f'{page_html}</div>'
    )

# Per-person cross-client pages (one per team member)
person_pages = [render_person_page(p, client_data) for p in TEAM_ROSTER]

nav_items = [("clients", "Clients", "👥"), ("admin", "Admin", "⚙️")]
nav_html = "\n".join(
    f'<a class="nav-item" data-nav="{key}" href="#{key}"><span class="nav-icon">{icon}</span>{label}</a>'
    for key, label, icon in nav_items
)


# ============ Final HTML ============

html = f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>{esc(agency.get("name", "Agency"))} — Dashboard</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Bebas+Neue&family=Figtree:wght@300;400;500;600;700;800&display=swap" rel="stylesheet">
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js"></script>
<style>
  :root {{
    --primary: {PRIMARY};
    --primary-soft: {PRIMARY}1A;
    --ink: #0a0e1a;
    --text: #0a0e1a;
    --muted: #6b7280;
    --border: #e5e7eb;
    --bg: #ffffff;
    --soft: #f7f7f8;
    --sidebar-w: 240px;
    --display: 'Bebas Neue', 'Arial Narrow', sans-serif;
    --body: 'Figtree', -apple-system, BlinkMacSystemFont, system-ui, sans-serif;
  }}
  * {{ box-sizing: border-box; }}
  body {{ font-family: var(--body); margin: 0; color: var(--text); background: #ededee;
         line-height: 1.55; font-size: 13px; }}
  a {{ color: var(--primary); text-decoration: none; }}
  a:hover {{ text-decoration: underline; }}
  code {{ background: var(--soft); padding: 2px 6px; border-radius: 4px; font-size: 12px; }}

  /* Sidebar */
  .sidebar {{ position: fixed; left: 0; top: 0; bottom: 0; width: var(--sidebar-w);
              background: var(--ink); color: white; padding: 24px 0; z-index: 10; overflow-y: auto; }}
  .sidebar-brand {{ padding: 0 22px 24px; border-bottom: 1px solid rgba(255,255,255,0.08); }}
  .sidebar-brand-name {{ font-family: var(--display); font-size: 26px; text-transform: uppercase;
                          letter-spacing: 0.04em; line-height: 1.0; font-weight: 400; }}
  .sidebar-brand-tag {{ font-size: 10px; text-transform: uppercase; letter-spacing: 0.1em;
                         opacity: 0.55; margin-top: 4px; font-weight: 700; }}
  .sidebar-nav {{ padding: 16px 0; }}
  .nav-item {{ display: flex; align-items: center; gap: 12px; padding: 12px 22px;
                color: rgba(255,255,255,0.7); font-weight: 600; font-size: 14px;
                text-decoration: none; border-left: 3px solid transparent; }}
  .nav-item:hover {{ background: rgba(255,255,255,0.04); color: white; text-decoration: none; }}
  .nav-item.active {{ background: rgba(37,99,235,0.15); color: white; border-left-color: var(--primary); }}
  .nav-icon {{ font-size: 16px; }}

  /* Main */
  main {{ margin-left: var(--sidebar-w); padding: 24px 28px 80px; max-width: 1500px; }}
  .page-header {{ margin-bottom: 20px; }}
  .page-header h1 {{ font-family: var(--display); font-size: 44px; text-transform: uppercase;
                      letter-spacing: 0.01em; line-height: 1.0; font-weight: 400; margin: 0; }}
  .page-header .sub {{ font-size: 12px; text-transform: uppercase; letter-spacing: 0.08em;
                        color: var(--muted); font-weight: 700; margin-top: 6px; }}
  .breadcrumb {{ margin-bottom: 10px; font-size: 13px; }}

  /* Client rows (3 cards per client) */
  .status-legend {{ display: flex; gap: 18px; margin-bottom: 14px; font-size: 12px;
                     color: var(--muted); font-weight: 600; }}
  .status-legend .dot {{ display: inline-block; width: 10px; height: 10px; border-radius: 50%;
                          margin-right: 6px; vertical-align: middle; }}
  .status-circle {{ width: 12px; height: 12px; border-radius: 50%; flex-shrink: 0;
                     box-shadow: 0 0 0 3px rgba(0,0,0,0.04); }}

  /* Client table */
  .client-table {{ background: white; border: 1px solid var(--border); border-radius: 10px;
                    overflow: hidden; }}
  .ct-row, .ct-header, details.client-row > summary {{
                    display: grid;
                    grid-template-columns: 28px 1.5fr 90px 110px 1.3fr 90px 130px 130px 80px 80px;
                    align-items: center; gap: 10px;
                    padding: 10px 16px; }}
  .ct-header {{ background: var(--ink); color: white; font-size: 10px;
                 text-transform: uppercase; letter-spacing: 0.08em; font-weight: 700; }}
  .ct-header .ct-cell {{ color: rgba(255,255,255,0.85); font-family: var(--body) !important;
                          font-size: 10px !important; text-transform: uppercase !important;
                          letter-spacing: 0.08em !important; }}
  .ct-cell {{ min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }}
  .ct-caret {{ color: var(--primary); font-size: 16px; font-weight: 700;
                transition: transform 0.15s; display: inline-flex; align-items: center;
                justify-content: center; }}
  details.client-row[open] > summary .ct-caret {{ transform: rotate(90deg); }}
  .ct-name {{ font-family: var(--display); font-size: 20px; line-height: 1.0;
              text-transform: uppercase; letter-spacing: 0.01em; font-weight: 400;
              color: var(--ink); }}
  .ct-start {{ font-size: 12px; color: var(--muted); font-variant-numeric: tabular-nums; }}
  .ct-services {{ display: flex; gap: 4px; flex-wrap: wrap; overflow: visible; white-space: normal; }}
  .ct-trend {{ font-size: 13px; font-weight: 700; text-align: right;
               font-variant-numeric: tabular-nums; }}
  .ct-content, .ct-links {{ font-size: 14px; font-weight: 700; color: var(--ink);
               font-variant-numeric: tabular-nums; text-align: right; }}
  .ct-header .ct-trend, .ct-header .ct-content, .ct-header .ct-links {{
               text-align: right; color: rgba(255,255,255,0.85); }}

  .svc-chip {{ display: inline-block; padding: 2px 8px; border-radius: 4px;
                font-size: 10px; font-weight: 700; letter-spacing: 0.04em;
                text-transform: uppercase; }}

  details.client-row {{ border-top: 1px solid var(--border); position: relative; }}
  details.client-row:first-of-type {{ border-top: 0; }}
  details.client-row > summary {{ cursor: pointer; list-style: none;
        border-left: 3px solid transparent; transition: border-color 0.15s, background 0.15s; }}
  details.client-row > summary::-webkit-details-marker {{ display: none; }}
  details.client-row:hover > summary {{ background: #eff6ff;
        border-left-color: var(--primary); }}
  details.client-row:hover .ct-caret {{ transform: translateX(3px); }}
  details.client-row[open] > summary {{ background: #eff6ff;
        border-left-color: var(--primary);
        border-bottom: 1px solid var(--border); }}
  details.client-row.hidden {{ display: none; }}
  /* Hint badge on right side */
  .ct-expand-hint {{ font-size: 9px; text-transform: uppercase; letter-spacing: 0.08em;
                      color: var(--muted); font-weight: 700; opacity: 0; transition: opacity 0.15s;
                      white-space: nowrap; margin-left: 6px; }}
  details.client-row:hover .ct-expand-hint {{ opacity: 1; }}
  details.client-row[open] .ct-expand-hint::before {{ content: "Collapse"; }}
  details.client-row:not([open]) .ct-expand-hint::before {{ content: "Click to expand"; }}
  /* Conversions pill (PPC / FB Conv columns in client overview). Compact
     count + colored MoM% delta. */
  .conv-pill {{ display: inline-flex; align-items: baseline; gap: 4px;
                 font-size: 13px; font-variant-numeric: tabular-nums; }}
  .conv-pill strong {{ color: var(--ink); }}

  .client-row-cards {{ display: grid; grid-template-columns: 1fr 1fr; gap: 12px;
                        padding: 12px 16px 16px; background: #fafbfc; }}
  /* Multi-service container — one service block per row, stacked vertically. */
  .client-row-services {{ padding: 8px 16px 16px; background: #fafbfc; display: flex;
                           flex-direction: column; gap: 14px; }}
  .service-block {{ background: white; border: 1px solid var(--border); border-radius: 12px;
                     overflow: hidden; }}
  .service-block-header {{ display: flex; align-items: center; gap: 10px;
                            padding: 10px 16px; background: #f8fafc;
                            border-bottom: 1px solid var(--border);
                            font-size: 13px; }}
  .service-block-icon {{ font-size: 16px; }}
  .service-block-label {{ font-weight: 700; text-transform: uppercase; letter-spacing: 0.4px; font-size: 12px; }}
  .service-block-status {{ font-size: 11px; padding: 2px 8px; background: #ecfdf5; color: #047857;
                            border-radius: 999px; text-transform: capitalize; font-weight: 600; }}
  .service-block-meta {{ margin-left: auto; font-size: 11px; color: #64748b; }}
  .service-block-meta + .service-block-meta {{ margin-left: 12px; }}
  .service-block-cards {{ display: grid; grid-template-columns: 1fr 1fr; gap: 12px; padding: 12px; }}
  @media (max-width: 1100px) {{
    .service-block-cards {{ grid-template-columns: 1fr; }}
    .client-row-cards {{ grid-template-columns: 1fr; }}
    .ct-row, .ct-header, details.client-row > summary {{
      grid-template-columns: 28px 1.3fr 80px 100px 1.1fr 80px 110px 110px 70px 70px;
      gap: 6px;
    }}
  }}

  /* Clients toolbar */
  .clients-toolbar {{ display: flex; align-items: center; gap: 14px; margin-bottom: 16px;
                       background: white; border: 1px solid var(--border); border-radius: 10px;
                       padding: 8px 12px; }}
  #client-search {{ flex: 1; font-family: var(--body); font-size: 13px;
                     padding: 8px 12px; border: 1px solid var(--border); border-radius: 6px;
                     background: white; color: var(--text); max-width: 360px; }}
  #client-search:focus {{ outline: 2px solid var(--primary); border-color: var(--primary); }}

  /* Toggle switch */
  .toggle-switch {{ display: inline-flex; align-items: center; gap: 8px; cursor: pointer;
                     margin-left: auto; user-select: none; }}
  .toggle-switch input {{ display: none; }}
  .toggle-slider {{ position: relative; width: 36px; height: 20px; background: #cbd5e1;
                     border-radius: 999px; transition: background 0.15s; }}
  .toggle-slider::before {{ content: ""; position: absolute; top: 2px; left: 2px;
                             width: 16px; height: 16px; background: white;
                             border-radius: 50%; transition: transform 0.15s;
                             box-shadow: 0 1px 3px rgba(0,0,0,0.2); }}
  .toggle-switch input:checked + .toggle-slider {{ background: var(--primary); }}
  .toggle-switch input:checked + .toggle-slider::before {{ transform: translateX(16px); }}
  .toggle-label {{ font-size: 12px; font-weight: 600; color: var(--text); }}

  /* Compact Campaign Stage + Performance cards */
  .client-card-3 {{ padding: 14px 18px; min-height: 0; }}
  .cc-label {{ margin-bottom: 8px; }}

  /* Stage card — timeline strip (Design 3) */
  .d3-strip {{ display: flex; gap: 3px; margin-bottom: 10px; }}
  .d3-cell {{ flex: 1; height: 20px; border-radius: 3px;
              display: flex; align-items: center; justify-content: center;
              font-size: 9px; font-weight: 700; }}
  .d3-cell.done    {{ background: #16a34a; color: white; }}
  .d3-cell.current {{ background: var(--primary); color: white; }}
  .d3-cell.future  {{ background: var(--soft); color: var(--muted); }}
  .d3-stage-info {{ display: flex; justify-content: space-between; align-items: baseline;
                     margin-bottom: 4px; }}
  .d3-stage-name {{ font-family: var(--display); font-size: 18px; text-transform: uppercase;
                     letter-spacing: 0.02em; color: var(--ink); line-height: 1.0; }}
  .d3-stage-stats {{ font-size: 11px; color: var(--muted); }}
  .d3-stage-stats strong {{ color: var(--ink); }}

  /* Performance card — mini progress rings (Design 2) */
  .d2-perf-trio {{ display: flex; gap: 8px; width: 100%; justify-content: space-around;
                    margin-bottom: 8px; }}
  .d2-perf-cell {{ display: flex; flex-direction: column; align-items: center; }}
  .ring {{ position: relative; width: 80px; height: 80px; }}
  .ring-center {{ position: absolute; inset: 0; display: flex; align-items: center;
                   justify-content: center; flex-direction: column; }}
  .ring-num {{ font-family: var(--display); font-size: 15px; line-height: 1.0;
               letter-spacing: 0.01em; }}
  .ring-label {{ text-align: center; font-size: 10px; color: var(--muted);
                  margin-top: 4px; text-transform: uppercase; letter-spacing: 0.06em;
                  font-weight: 700; }}

  .cc-perf-cta {{ padding-top: 6px; }}
  .client-card-3 {{ background: white; border: 1px solid var(--border); border-radius: 12px;
                     padding: 20px; color: var(--text); display: flex; flex-direction: column;
                     transition: all 0.15s; min-height: 180px; }}
  .client-card-3:hover {{ text-decoration: none; transform: translateY(-2px);
                          box-shadow: 0 6px 20px rgba(0,0,0,0.08); border-color: var(--primary); }}
  .cc-label {{ font-size: 10px; text-transform: uppercase; letter-spacing: 0.08em;
                color: var(--muted); font-weight: 700; margin-bottom: 8px; }}

  /* Card 1: Client info */
  .cc-status-row {{ display: flex; align-items: center; gap: 8px; margin-bottom: 10px; }}
  .status-label-lg {{ font-size: 11px; text-transform: uppercase; letter-spacing: 0.08em;
                       font-weight: 700; }}
  .cc-client-name {{ font-family: var(--display); font-size: 30px; text-transform: uppercase;
                      letter-spacing: 0.02em; font-weight: 400; margin: 0 0 4px; color: var(--ink); }}
  .cc-contact {{ font-size: 13px; font-weight: 600; margin-bottom: 2px; }}
  .cc-website {{ font-size: 12px; margin-bottom: 14px; }}
  .cc-footer {{ font-size: 11px; color: var(--muted); margin-top: auto;
                 padding-top: 10px; border-top: 1px solid var(--border); }}

  /* Card 2: Stage */
  .cc-month-big {{ font-family: var(--display); font-size: 40px; line-height: 1.0;
                    color: var(--ink); margin-top: 2px; }}
  .cc-month-of {{ font-size: 18px; color: var(--muted); }}
  .cc-stage-label {{ font-size: 14px; font-weight: 700; color: var(--ink);
                      text-transform: uppercase; letter-spacing: 0.05em; margin-top: 4px;
                      margin-bottom: 14px; }}
  .cc-progress-bar {{ display: flex; align-items: center; gap: 10px; margin-bottom: 10px; }}
  .cc-progress-bar .progress-track {{ flex: 1; max-width: none; height: 8px; }}
  .cc-progress-pct {{ font-size: 13px; font-weight: 700; color: var(--ink);
                       font-variant-numeric: tabular-nums; }}
  .cc-stage-stats {{ display: grid; grid-template-columns: 1fr 1fr; gap: 6px 14px;
                      font-size: 12px; color: var(--muted); margin-top: auto; }}
  .cc-stage-stats strong {{ color: var(--ink); font-size: 13px; margin-right: 4px; }}
  .cc-stat-warn strong {{ color: #dc2626; }}
  .cc-empty-msg {{ font-family: var(--display); font-size: 26px; text-transform: uppercase;
                    color: var(--muted); letter-spacing: 0.02em; }}
  .cc-empty-hint {{ font-size: 12px; color: var(--muted); margin-top: 6px; }}

  /* Card 3: Performance */
  .cc-perf-grid {{ display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 12px;
                    margin-top: 4px; margin-bottom: 12px; }}
  .cc-perf-cell {{ text-align: center; padding: 8px 6px; background: var(--soft);
                    border-radius: 8px; }}
  .cc-perf-key {{ font-size: 10px; text-transform: uppercase; letter-spacing: 0.08em;
                   color: var(--muted); font-weight: 700; margin-bottom: 4px; }}
  .cc-perf-val {{ font-size: 16px; }}
  .cc-perf-source {{ font-size: 10px; color: var(--muted); margin-top: 4px;
                      text-align: center; font-style: italic; }}
  .cc-perf-cta {{ font-size: 12px; font-weight: 700; color: var(--primary);
                   margin-top: auto; padding-top: 10px;
                   border-top: 1px solid var(--border); text-align: right; }}

  /* Client detail */
  .client-hero {{ background: var(--ink); color: white; border-radius: 14px;
                   padding: 24px 28px; margin-bottom: 16px;
                   border-left: 8px solid var(--primary); }}
  .client-hero .sub {{ font-size: 11px; opacity: 0.7; text-transform: uppercase;
                        letter-spacing: 0.1em; font-weight: 700; }}
  .client-hero h2 {{ margin: 4px 0 6px; font-family: var(--display); text-transform: uppercase;
                      font-size: 36px; line-height: 1.0; letter-spacing: 0.01em; font-weight: 400; }}
  .client-hero .meta {{ font-size: 13px; opacity: 0.85; }}

  /* KPI grid */
  .kpi-grid {{ display: grid; grid-template-columns: repeat(4, 1fr); gap: 10px; margin-bottom: 16px; }}
  .kpi {{ background: white; border: 1px solid var(--border); border-radius: 10px; padding: 14px; }}
  .kpi-label {{ font-size: 10px; text-transform: uppercase; letter-spacing: 0.08em;
                color: var(--muted); font-weight: 700; }}
  .kpi-value {{ font-family: var(--display); font-size: 36px; line-height: 1.0;
                color: var(--ink); margin-top: 4px; text-transform: uppercase; }}
  .kpi-sub {{ font-size: 11px; color: var(--muted); margin-top: 4px; }}

  /* Export buttons strip — top of Tasks view. One button per supported
     PM tool format. Each is a real download link. */
  .task-export-strip {{ display: flex; align-items: center; gap: 8px;
                         margin-bottom: 10px; padding: 8px 12px;
                         background: white; border: 1px solid var(--border);
                         border-radius: 8px; }}
  .task-export-label {{ font-size: 10px; font-weight: 700; text-transform: uppercase;
                         letter-spacing: 0.08em; color: var(--muted);
                         margin-right: 4px; }}
  .task-export-hint {{ font-size: 11px; color: var(--muted); font-style: italic;
                        margin-left: 8px; }}
  .export-btn {{ display: inline-flex; align-items: center; gap: 6px;
                  padding: 8px 16px; border: 1.5px solid var(--primary); border-radius: 6px;
                  font-size: 12px; font-weight: 700; text-transform: uppercase;
                  letter-spacing: 0.04em; text-decoration: none;
                  background: white; color: var(--primary);
                  cursor: pointer; transition: all 0.15s; }}
  .export-btn:hover {{ background: var(--primary); color: white; }}
  .export-btn:hover .export-btn-label,
  .export-btn:hover .export-btn-ext,
  .export-btn:hover .export-btn-icon {{ color: white; }}
  .export-btn-icon {{ font-size: 13px; font-weight: 900; }}
  .export-btn-label {{ font-size: 12px; }}
  .export-btn-ext {{ font-size: 9px; opacity: 0.7; font-weight: 600;
                      letter-spacing: 0; text-transform: none; }}
  .export-btn-disabled {{ border-color: #e5e7eb !important; color: #cbd5e1 !important;
                           cursor: not-allowed; background: #f9fafb; }}
  .export-btn-disabled:hover {{ background: #f9fafb; }}
  .export-btn-disabled:hover .export-btn-label,
  .export-btn-disabled:hover .export-btn-ext,
  .export-btn-disabled:hover .export-btn-icon {{ color: #cbd5e1; }}

  /* View tabs + filters */
  .view-tabs {{ display: flex; gap: 4px; margin-bottom: 12px; background: white;
                border: 1px solid var(--border); border-radius: 10px; padding: 4px;
                width: fit-content; }}
  .view-tab {{ padding: 8px 18px; font-family: var(--body); font-weight: 700;
                font-size: 12px; text-transform: uppercase; letter-spacing: 0.06em;
                color: var(--muted); border: 0; background: transparent; cursor: pointer;
                border-radius: 6px; }}
  .view-tab.active {{ background: var(--ink); color: white; }}
  .filters {{ display: flex; gap: 8px; margin-bottom: 14px; flex-wrap: wrap;
              background: white; border: 1px solid var(--border); border-radius: 10px;
              padding: 10px 14px; align-items: center; }}
  .filters label {{ font-size: 11px; text-transform: uppercase; letter-spacing: 0.06em;
                     color: var(--muted); font-weight: 700; }}
  .filters select, .filters input[type=text] {{ font-family: var(--body); font-size: 13px;
        padding: 6px 10px; border: 1px solid var(--border); border-radius: 6px;
        background: white; color: var(--text); }}
  .filter-pill {{ padding: 4px 10px; background: var(--soft); border-radius: 999px;
                   font-size: 11px; font-weight: 600; color: var(--muted); cursor: pointer; }}
  .filter-pill.active {{ background: var(--ink); color: white; }}
  .view {{ display: none; }}
  .view.active {{ display: block; }}

  /* Gantt / Timeline view */
  .gantt {{ background: white; border: 1px solid var(--border); border-radius: 10px;
            overflow: hidden; --gt-sidebar: 280px; }}
  .gt-header {{ display: flex; background: var(--ink); color: white;
                font-size: 10px; text-transform: uppercase; letter-spacing: 0.08em;
                font-weight: 700; }}
  .gt-header-label {{ padding: 10px 14px; flex: 0 0 var(--gt-sidebar);
                       border-right: 1px solid rgba(255,255,255,0.15); }}
  .gt-row-track, .gt-header-track {{ position: relative; flex: 1; min-height: 32px; }}
  .gt-mh {{ position: absolute; top: 0; bottom: 0; padding: 10px 8px;
            border-right: 1px solid rgba(255,255,255,0.18);
            display: flex; align-items: center; overflow: hidden;
            color: rgba(255,255,255,0.85); }}
  .gt-mh:last-child {{ border-right: none; }}

  .gt-body {{ position: relative; background:
              repeating-linear-gradient(to right,
              transparent, transparent calc((100% / 12) - 1px),
              #f1f5f9 calc((100% / 12) - 1px), #f1f5f9 calc(100% / 12)); }}

  .gt-today {{ position: absolute; top: 0; bottom: 0; width: 2px;
               background: #dc2626; z-index: 5; pointer-events: none;
               left: 0; margin-left: var(--gt-sidebar); }}
  .gt-today-label {{ position: absolute; top: 4px; left: 4px; background: #dc2626;
                      color: white; padding: 2px 6px; border-radius: 4px;
                      font-size: 10px; font-weight: 700; }}

  .gt-group-header {{ padding: 10px 14px; background: #f8fafc;
                       border-top: 1px solid var(--border); border-left: 4px solid;
                       font-size: 11px; text-transform: uppercase; letter-spacing: 0.08em;
                       font-weight: 700; display: flex; align-items: center; gap: 12px; }}
  .gt-group-name {{ color: var(--ink); }}
  .gt-group-count {{ color: var(--muted); font-weight: 500; text-transform: none;
                      letter-spacing: 0; font-size: 11px; }}

  .gt-row {{ display: flex; align-items: center; min-height: 36px;
             border-top: 1px solid #f1f5f9; }}
  .gt-row:hover {{ background: #fafbfc; }}
  .gt-row-label {{ flex: 0 0 var(--gt-sidebar); padding: 4px 14px;
                    display: flex; align-items: center; gap: 8px;
                    border-right: 1px solid var(--border); min-height: 36px; }}
  .gt-avatar {{ display: inline-flex; width: 22px; height: 22px; border-radius: 50%;
                background: var(--soft); color: var(--ink); align-items: center;
                justify-content: center; font-size: 11px; font-weight: 700;
                flex-shrink: 0; }}
  .gt-task-name {{ font-size: 12px; color: var(--ink); overflow: hidden;
                    text-overflow: ellipsis; white-space: nowrap; }}

  .gt-bar {{ position: absolute; top: 6px; bottom: 6px; min-width: 6px;
             border-radius: 4px; padding: 0 8px; display: flex; align-items: center;
             color: white; font-size: 11px; font-weight: 600;
             overflow: hidden; white-space: nowrap;
             box-shadow: 0 1px 2px rgba(0,0,0,0.08); cursor: default; }}
  .gt-bar-text {{ overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }}
  .gt-bar:hover {{ filter: brightness(1.08); box-shadow: 0 2px 6px rgba(0,0,0,0.15); }}

  /* Special bar styles by kind */
  .gt-row[data-kind="monthly-report"] .gt-bar {{ background: #94a3b8 !important;
                                                  border: 1px dashed #475569 !important;
                                                  font-style: italic; }}
  .gt-row[data-kind="placeholder"] .gt-bar {{ opacity: 0.85;
                                               background-image: repeating-linear-gradient(
                                                 45deg, transparent, transparent 4px,
                                                 rgba(255,255,255,0.18) 4px, rgba(255,255,255,0.18) 8px); }}
  .gt-row[data-kind="quick"] .gt-bar {{ /* default */ }}
  .gt-row[data-kind="heavy-batch"] .gt-bar {{ /* default */ }}

  /* List / task table with resizable columns via CSS vars.
     Order: Start · Due · Status · Owner · Bucket · Task · Deliverable · Notes (flex) */
  .task-table {{ background: white; border: 1px solid var(--border); border-radius: 10px;
                  overflow: hidden;
                  --w-start:       90px;
                  --w-due:         90px;
                  --w-status:      150px;
                  --w-owner:       110px;
                  --w-bucket:      100px;
                  --w-task:        260px;
                  --w-deliverable: 170px; }}
  .table-header {{ display: flex; align-items: center; padding: 10px 14px; background: var(--ink);
                    color: white; font-size: 10px; text-transform: uppercase;
                    letter-spacing: 0.08em; font-weight: 700; }}
  .table-header .cell {{ color: rgba(255,255,255,0.85); position: relative; }}
  .cell {{ padding: 0 8px; min-width: 0; }}
  .cell-start  {{ width: var(--w-start);  flex: 0 0 var(--w-start); }}
  .cell-due    {{ width: var(--w-due);    flex: 0 0 var(--w-due); }}
  .cell-status {{ width: var(--w-status); flex: 0 0 var(--w-status); }}
  .cell-owner  {{ width: var(--w-owner);  flex: 0 0 var(--w-owner);
                  display: flex; align-items: center; gap: 6px; }}
  .cell-bucket {{ width: var(--w-bucket); flex: 0 0 var(--w-bucket); }}
  .cell-task   {{ width: var(--w-task);   flex: 0 0 var(--w-task);
                  display: flex; align-items: center; gap: 6px; }}
  .cell-deliverable {{ width: var(--w-deliverable); flex: 0 0 var(--w-deliverable); }}
  .deliverable-pill {{ display: inline-block; padding: 3px 10px; border-radius: 4px;
                        font-size: 10px; font-weight: 700; letter-spacing: 0.03em;
                        text-transform: uppercase;
                        max-width: 100%; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }}
  .cell-notes  {{ flex: 1 1 auto; min-width: 200px;
                  font-size: 12px; color: var(--muted);
                  overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }}

  /* Auto-deliverables (rolled up from tasks) */
  .cell-dv-name     {{ flex: 0 0 200px; }}
  .cell-dv-progress {{ flex: 0 0 200px; }}
  .cell-dv-target   {{ flex: 0 0 100px; font-size: 12px; font-variant-numeric: tabular-nums; }}
  .cell-dv-status   {{ flex: 0 0 150px; }}
  .cell-dv-senddate {{ flex: 0 0 100px; font-size: 12px; }}
  .cell-dv-sender   {{ flex: 0 0 110px; font-size: 12px; }}
  .cell-dv-link     {{ flex: 1; min-width: 150px; font-size: 12px;
                       overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }}
  .cell-dv-notes    {{ flex: 1; min-width: 150px; font-size: 12px; }}
  .auto-row {{ display: flex; align-items: center; padding: 10px 14px;
               border-top: 1px solid var(--border); min-height: 52px; }}
  .auto-row:hover {{ background: #f7f8fa; }}

  /* Deliverables table */
  .deliverables-toolbar {{ display: flex; align-items: center; margin-bottom: 8px; }}
  .btn-primary {{ background: var(--primary); color: white; border: 0; padding: 8px 16px;
                   border-radius: 6px; font-weight: 700; font-size: 12px; text-transform: uppercase;
                   letter-spacing: 0.05em; cursor: pointer; font-family: var(--body); }}
  .btn-primary:hover {{ filter: brightness(0.95); }}
  .cell-d-date    {{ flex: 0 0 100px; }}
  .cell-d-sender  {{ flex: 0 0 130px; }}
  .cell-d-name    {{ flex: 1.4; min-width: 180px; }}
  .cell-d-status  {{ flex: 0 0 150px; }}
  .cell-d-link    {{ flex: 1.2; min-width: 180px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }}
  .cell-d-notes   {{ flex: 1.5; min-width: 180px; }}
  .cell-d-actions {{ flex: 0 0 50px; text-align: right; }}
  .deliverables-body .empty-row {{ padding: 36px 24px; text-align: center;
                                    color: var(--muted); font-size: 13px; }}
  .deliverable-row {{ display: flex; align-items: center; padding: 8px 14px;
                       border-top: 1px solid var(--border); min-height: 40px; }}
  .deliverable-row:hover {{ background: #f7f8fa; }}
  .deliverable-row .editable {{ font-size: 12px; }}

  /* Sheets-backed banner (Content + Links tabs read-only mirrors) */
  .sheets-banner {{ display: flex; align-items: center; justify-content: space-between;
                     background: #f0fdf4; border: 1px solid #bbf7d0; border-radius: 8px;
                     padding: 8px 12px; margin-bottom: 10px; }}
  .sheets-banner-warn {{ background: #fef2f2; border-color: #fecaca; }}
  .sheets-banner .sb-meta {{ display: flex; align-items: center; gap: 10px; }}
  .sheets-banner .sb-dot {{ width: 8px; height: 8px; border-radius: 50%; display: inline-block; }}
  .sheets-banner .sb-label {{ font-size: 11px; font-weight: 700; text-transform: uppercase;
                               letter-spacing: 0.06em; color: var(--ink); }}
  .sheets-banner .sb-sync {{ font-size: 11px; color: var(--muted); }}
  .sheets-banner .sb-cta {{ font-size: 12px; font-weight: 700; color: var(--primary);
                             text-decoration: none; padding: 4px 10px; border-radius: 6px;
                             background: white; border: 1px solid var(--border); }}
  .sheets-banner .sb-cta:hover {{ background: var(--soft); }}

  /* Sheet-row: visually quieter than editable rows; signals read-only */
  .sheet-row {{ display: flex; align-items: center; padding: 8px 14px;
                border-top: 1px solid var(--border); background: white; }}
  .sheet-row:hover {{ background: #fafbfc; }}

  /* Status pill variants (content workbook) — workbook uses free-form labels,
     bucketed by sheets_sync.content_status_class() */
  .status-pill {{ display: inline-block; padding: 2px 10px; border-radius: 10px;
                   font-size: 11px; font-weight: 700; line-height: 1.4;
                   white-space: nowrap; }}
  .status-live    {{ background: #22c55e; color: white; }}
  .status-ready   {{ background: #bbf7d0; color: #14532d; }}
  .status-working {{ background: #fde68a; color: #92400e; }}
  .status-blocked {{ background: #fecaca; color: #991b1b; }}
  .status-empty   {{ background: #f3f4f6; color: #6b7280; }}
  .status-other   {{ background: #e5e7eb; color: #374151; }}

  .muted-link {{ font-size: 10px; color: var(--muted); }}

  /* Content table (sheet-backed) */
  .content-table .cell-c-status     {{ flex: 0 0 150px; }}
  .content-table .cell-c-feedback   {{ flex: 0 0 130px; font-size: 12px; color: var(--muted); }}
  .content-table .cell-c-topic      {{ flex: 1.4; min-width: 200px; font-size: 13px;
                                        overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }}
  .content-table .cell-c-pagetype   {{ flex: 0 0 110px; font-size: 12px; color: var(--muted); }}
  .content-table .cell-c-newrewrite {{ flex: 0 0 90px;  font-size: 12px; }}
  .content-table .cell-c-vol        {{ flex: 0 0 80px;  font-size: 12px; font-variant-numeric: tabular-nums; }}
  .content-table .cell-c-published  {{ flex: 0 0 100px; font-size: 12px;
                                        font-variant-numeric: tabular-nums; color: var(--muted); }}
  .content-table .cell-c-url        {{ flex: 1.2; min-width: 200px; font-size: 11px; color: var(--muted);
                                        overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }}

  /* Links table (sheet-backed) */
  .links-table .cell-l-status {{ flex: 0 0 150px; }}
  .links-table .cell-l-date   {{ flex: 0 0 90px;  font-size: 12px; font-variant-numeric: tabular-nums; }}
  .links-table .cell-l-type   {{ flex: 0 0 110px; font-size: 12px; color: var(--muted); }}
  .links-table .cell-l-url    {{ flex: 1.2; min-width: 200px; font-size: 12px;
                                  overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }}
  .links-table .cell-l-target {{ flex: 1.2; min-width: 200px; font-size: 12px;
                                  overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }}
  .links-table .cell-l-anchor {{ flex: 1; min-width: 140px; font-size: 12px; color: var(--muted);
                                  overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }}
  .links-table .cell-l-cost   {{ flex: 0 0 70px;  font-size: 12px;
                                  font-variant-numeric: tabular-nums; color: var(--muted); }}

  /* Editable cell (contenteditable) */
  .editable-cell {{ cursor: text; padding: 4px 6px; border-radius: 4px;
                     min-height: 22px; }}
  .editable-cell:focus {{ outline: 2px solid var(--primary); background: white; }}
  .editable-cell:empty::before {{ content: attr(data-placeholder); color: #cbd5e1; }}

  .empty-row {{ padding: 32px 24px; text-align: center; color: var(--muted); font-size: 13px; }}

  /* People grid */
  .people-grid {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(360px, 1fr)); gap: 14px; }}
  .person-card {{ background: white; border: 1px solid var(--border); border-radius: 12px;
                   padding: 18px; position: relative; }}
  .person-card.clickable {{ cursor: pointer; transition: all 0.15s; }}
  .person-card.clickable:hover {{ transform: translateY(-2px);
        box-shadow: 0 6px 18px rgba(0,0,0,0.08); border-color: var(--primary); }}
  .person-card-cta {{ margin-top: 12px; padding-top: 10px; border-top: 1px solid var(--border);
        text-align: right; font-size: 12px; font-weight: 700; color: var(--primary);
        text-transform: uppercase; letter-spacing: 0.04em; }}
  .person-card-head {{ display: flex; align-items: center; gap: 14px; margin-bottom: 14px; }}
  .avatar.xl {{ width: 52px; height: 52px; font-size: 20px; }}
  .person-card-info {{ flex: 1; min-width: 0; }}
  .person-card-name {{ font-family: var(--display); font-size: 22px; text-transform: uppercase;
                        letter-spacing: 0.02em; font-weight: 400; margin: 0; color: var(--ink); }}
  .person-card-title {{ font-size: 12px; font-weight: 600; color: var(--muted);
                         text-transform: uppercase; letter-spacing: 0.05em; }}
  .person-card-email {{ font-size: 12px; margin-top: 2px; }}
  .person-card-section {{ margin-top: 12px; }}
  .person-card-label {{ font-size: 10px; text-transform: uppercase; letter-spacing: 0.08em;
                         color: var(--muted); font-weight: 700; margin-bottom: 4px; }}
  .person-card-skills {{ font-size: 12px; color: var(--text); }}
  .person-card-work {{ background: var(--soft); border-radius: 6px; padding: 8px; }}
  .work-row {{ display: flex; align-items: center; gap: 8px; padding: 4px 0;
                font-size: 12px; }}
  .work-due {{ font-variant-numeric: tabular-nums; font-weight: 600; color: var(--muted);
                font-size: 11px; flex-shrink: 0; width: 60px; }}
  .work-name {{ overflow: hidden; text-overflow: ellipsis; white-space: nowrap; min-width: 0; flex: 1; }}

  .cell.sortable {{ cursor: pointer; user-select: none; }}
  .cell.sortable:hover {{ color: white; }}
  .sort-ind {{ display: inline-block; min-width: 10px; opacity: 0.5; }}
  .cell.sortable.sort-asc .sort-ind::after {{ content: "▲"; opacity: 1; }}
  .cell.sortable.sort-desc .sort-ind::after {{ content: "▼"; opacity: 1; }}

  /* Resize handles on header cells */
  .resize-handle {{ position: absolute; top: 0; right: -3px; width: 6px; height: 100%;
                     cursor: col-resize; z-index: 5; }}
  .resize-handle:hover {{ background: rgba(37,99,235,0.4); }}
  .resize-handle.dragging {{ background: rgba(37,99,235,0.7); }}

  /* Flat body (no bucket grouping) */
  .flat-body {{ background: white; }}

  /* Person group in By Person view */
  details.person-group {{ border-bottom: 1px solid var(--border); }}
  details.person-group:last-child {{ border-bottom: 0; }}
  details.person-group > summary {{ display: flex; align-items: center; gap: 10px;
        padding: 10px 14px; cursor: pointer; list-style: none; background: var(--soft); }}
  details.person-group > summary::-webkit-details-marker {{ display: none; }}
  details.person-group > summary::after {{ content: "▾"; color: var(--muted); margin-left: auto; }}
  details.person-group:not([open]) > summary::after {{ content: "▸"; }}
  .person-name-inline {{ font-family: var(--display); font-size: 20px; text-transform: uppercase;
                          letter-spacing: 0.02em; font-weight: 400; color: var(--ink); }}
  .bucket-count {{ font-size: 12px; color: var(--muted); font-weight: 600; }}

  /* Inline bucket pill (cell value) */
  .bucket-pill {{ display: inline-block; padding: 3px 10px; border-radius: 4px;
                   font-size: 11px; font-weight: 700; letter-spacing: 0.04em;
                   text-transform: uppercase; }}

  /* Row */
  details.row {{ border-top: 1px solid var(--border); }}
  details.row:first-child {{ border-top: 0; }}
  details.row > summary {{ display: flex; align-items: center; padding: 8px 14px;
        cursor: pointer; list-style: none; min-height: 40px; }}
  details.row > summary::-webkit-details-marker {{ display: none; }}
  details.row[open] {{ background: #fafbfc; }}
  details.row:hover > summary {{ background: #f7f8fa; }}

  /* Monthly report rows — gray styling, act as visual month-break in Tasks tab */
  details.row.row-monthly-report > summary {{
        background: #f1f5f9;
        color: #64748b;
        font-style: italic;
        border-top: 2px solid #cbd5e1;
        border-bottom: 1px solid #cbd5e1;
  }}
  details.row.row-monthly-report:hover > summary {{ background: #e2e8f0; }}
  details.row.row-monthly-report .cell {{ color: #64748b; }}
  details.row.row-monthly-report .cell-task {{ font-weight: 700; }}
  .row-name {{ font-weight: 500; font-size: 13px; overflow: hidden;
               text-overflow: ellipsis; white-space: nowrap; flex: 1; min-width: 0; }}
  .ai-tag {{ color: #7c3aed; font-size: 11px; flex-shrink: 0; }}
  .owner-name {{ font-size: 12px; font-weight: 600; }}

  /* Row body (expanded) */
  .row-body {{ padding: 14px 18px 18px 18px; background: #fafbfc;
                border-top: 1px solid var(--border); }}
  .row-detail {{ margin-bottom: 12px; }}
  .row-detail-label {{ font-size: 10px; text-transform: uppercase; letter-spacing: 0.08em;
                        color: var(--muted); font-weight: 700; margin-bottom: 4px; }}
  .sub-prompt {{ background: #ede9fe; color: #4c1d95; padding: 8px 12px; border-radius: 6px;
                  font-size: 13px; font-style: italic; }}

  /* Date pill */
  .date-pill {{ font-size: 12px; font-variant-numeric: tabular-nums; color: var(--text);
                 font-weight: 600; }}
  .date-pill.overdue {{ color: #dc2626; font-weight: 700; }}
  .date-empty {{ color: var(--muted); font-size: 12px; }}

  /* Status pill (editable) */
  .status-pill {{ display: inline-flex; align-items: center; gap: 4px; padding: 4px 10px;
                   border-radius: 4px; font-size: 11px; font-weight: 700; letter-spacing: 0.04em;
                   text-transform: uppercase; cursor: default; }}
  .status-pill.editable {{ cursor: pointer; }}
  .status-pill.editable:hover {{ filter: brightness(0.95); }}
  .date-edit {{ font: inherit; font-size: 12px; border: 1px solid transparent; background: #f1f5f9;
    border-radius: 6px; padding: 2px 6px; color: #0f172a; max-width: 122px; cursor: pointer; }}
  .date-edit:hover {{ border-color: #cbd5e1; background: #fff; }}
  .date-edit:focus {{ outline: none; border-color: #2563eb; background: #fff; }}
  .date-edit.overdue {{ color: #dc2626; background: #fef2f2; }}
  .pill-label {{ }}
  .pill-caret {{ font-size: 9px; opacity: 0.6; }}

  /* Status dropdown menu */
  .status-menu {{ position: absolute; z-index: 100; background: white;
                   border: 1px solid var(--border); border-radius: 8px;
                   box-shadow: 0 4px 16px rgba(0,0,0,0.12); padding: 4px;
                   min-width: 180px; }}
  .status-menu-item {{ display: flex; align-items: center; gap: 8px; padding: 8px 10px;
                        font-size: 12px; cursor: pointer; border-radius: 4px;
                        text-transform: uppercase; font-weight: 700; letter-spacing: 0.04em; }}
  .status-menu-item:hover {{ background: var(--soft); }}
  .status-menu-swatch {{ width: 12px; height: 12px; border-radius: 3px; flex-shrink: 0; }}

  /* Avatars */
  .avatar {{ display: inline-flex; align-items: center; justify-content: center;
             width: 22px; height: 22px; border-radius: 50%; background: var(--primary);
             color: white; font-weight: 700; font-size: 10px; flex-shrink: 0; }}
  .avatar.lg {{ width: 30px; height: 30px; font-size: 13px; }}

  /* Summary table */
  .summary-table {{ width: 100%; border-collapse: collapse; font-size: 13px;
                     background: white; border: 1px solid var(--border); border-radius: 10px;
                     overflow: hidden; margin-bottom: 16px; }}
  .summary-table th {{ background: var(--ink); color: white; padding: 10px 14px;
                        text-align: left; font-size: 11px; text-transform: uppercase;
                        letter-spacing: 0.08em; font-weight: 700; }}
  .summary-table td {{ padding: 12px 14px; border-bottom: 1px solid var(--border); }}
  .summary-table tr:last-child td {{ border-bottom: none; }}
  .muted {{ color: var(--muted); font-size: 11px; }}

  /* Empty / placeholder */
  .empty-state, .placeholder {{ background: white; border: 1px solid var(--border);
        border-radius: 12px; padding: 48px 32px; text-align: center; }}
  .empty-icon, .placeholder-icon {{ font-size: 48px; margin-bottom: 16px; opacity: 0.4; }}
  .empty-msg h3, .placeholder h3 {{ font-family: var(--display); font-size: 26px;
        text-transform: uppercase; letter-spacing: 0.02em; font-weight: 400; margin: 0 0 10px;
        color: var(--ink); }}
  .empty-msg p, .placeholder p {{ font-size: 14px; color: var(--muted); max-width: 540px;
        margin: 0 auto 8px; }}

  /* Admin */
  .section-title {{ font-family: var(--display); font-size: 22px; text-transform: uppercase;
        letter-spacing: 0.02em; font-weight: 400; margin: 24px 0 8px; color: var(--ink); }}
  .profile-card {{ background: white; border: 1px solid var(--border); border-radius: 12px;
        padding: 18px 22px; display: grid; grid-template-columns: repeat(2, 1fr);
        gap: 16px; margin-bottom: 12px; }}
  .profile-value {{ font-size: 14px; font-weight: 600; margin-top: 4px; color: var(--ink); }}

  .admin-panel {{ display: none; }}
  .admin-panel.active {{ display: block; }}

  /* Admin Clients table */
  .admin-clients-table .cell-ac-status   {{ flex: 0 0 110px; }}
  .admin-clients-table .cell-ac-name     {{ flex: 0 0 180px; font-size: 13px; }}
  .admin-clients-table .cell-ac-home     {{ flex: 0 0 160px; font-size: 12px;
                                             overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }}
  .admin-clients-table .cell-ac-workbook {{ flex: 0 0 90px; font-size: 12px; }}
  .admin-clients-table .cell-ac-folder   {{ flex: 0 0 80px; font-size: 12px; }}
  .admin-clients-table .cell-ac-start    {{ flex: 0 0 100px; font-size: 12px;
                                             font-variant-numeric: tabular-nums; }}
  .admin-clients-table .cell-ac-desc     {{ flex: 1.5; min-width: 200px; font-size: 12px;
                                             overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }}
  .admin-clients-table .cell-ac-poc      {{ flex: 0 0 140px; font-size: 12px; }}
  .admin-clients-table .cell-ac-contact  {{ flex: 0 0 200px; font-size: 12px;
                                             overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }}
  .admin-clients-table .cell-ac-scope    {{ flex: 0 0 140px; font-size: 12px; }}
  .admin-row {{ display: flex; align-items: center; padding: 10px 14px;
                 border-top: 1px solid var(--border); min-height: 42px; }}
  .admin-row:hover {{ background: #f7f8fa; }}

  /* Filtered */
  details.row.filtered-out {{ display: none; }}

  /* Person page (cross-client task view) */
  .person-header {{ display: flex; align-items: center; gap: 20px;
                     background: var(--ink); color: white; padding: 22px 26px;
                     border-radius: 12px; margin-bottom: 18px;
                     border-left: 8px solid var(--primary); }}
  .person-header h1 {{ color: white !important; }}
  .person-header .avatar.xl {{ width: 64px; height: 64px; font-size: 26px;
                                background: var(--primary); }}
  .person-header .muted, .person-header [style*="color:var(--muted)"] {{
                                color: rgba(255,255,255,0.7) !important; }}
  .person-header a {{ color: rgba(255,255,255,0.9); }}

  .cell-pp-client {{ flex: 0 0 180px; font-size: 13px; }}
  .cell-pp-client a {{ color: var(--ink); }}
  .cell-pp-start  {{ flex: 0 0 90px; font-size: 12px; color: var(--muted); }}
  .cell-pp-due    {{ flex: 0 0 90px; }}
  .cell-pp-status {{ flex: 0 0 150px; }}
  .cell-pp-bucket {{ flex: 0 0 110px; }}
  .cell-pp-task   {{ flex: 1.5; min-width: 180px; display: flex; align-items: center; gap: 6px; }}
  .cell-pp-notes  {{ flex: 1; min-width: 150px; font-size: 12px; color: var(--muted);
                      overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }}

  /* Workload bar in People table */
  .load-cell {{ display: flex; flex-direction: column; gap: 4px; min-width: 180px; }}
  .load-bar-track {{ height: 8px; background: #e5e7eb; border-radius: 4px; overflow: hidden;
                      width: 100%; max-width: 200px; }}
  .load-bar-fill {{ height: 100%; transition: width 0.3s; border-radius: 4px; }}
  .load-meta {{ font-size: 11px; color: var(--text); }}

  .btn-mini {{ display: inline-block; padding: 4px 10px; background: var(--soft);
                color: var(--primary); border-radius: 4px; font-size: 11px;
                font-weight: 700; text-transform: uppercase; letter-spacing: 0.04em;
                text-decoration: none; white-space: nowrap; }}
  .btn-mini:hover {{ background: var(--primary); color: white; text-decoration: none; }}

  /* "Not Connected" empty states */
  .rep-not-connected {{ background: white; border: 1px solid var(--border);
                         border-left: 4px solid #f59e0b; border-radius: 10px;
                         padding: 18px 22px; margin-bottom: 14px; }}
  .rep-nc-badge {{ display: inline-block; background: #f59e0b; color: white;
                    padding: 4px 12px; border-radius: 4px; font-size: 11px;
                    font-weight: 700; letter-spacing: 0.08em; text-transform: uppercase;
                    margin-bottom: 8px; }}
  .rep-nc-action {{ font-size: 13px; color: var(--text); font-weight: 500; }}

  /* Performance card "Not Connected" variant */
  .card-not-connected {{ opacity: 0.85; }}
  .cc-not-connected {{ display: flex; flex-direction: column; align-items: center;
                        justify-content: center; padding: 8px 0; gap: 2px; }}
  .cc-not-connected-icon {{ font-size: 24px; color: #f59e0b; line-height: 1; }}
  .cc-not-connected-title {{ font-family: var(--display); font-size: 18px;
                              text-transform: uppercase; letter-spacing: 0.04em;
                              color: #92400e; }}
  .cc-not-connected-msg {{ font-size: 11px; color: var(--muted); text-align: center; }}

  /* Reporting page picker */
  .reporting-picker {{ display: flex; align-items: center; gap: 12px;
                        background: white; border: 1px solid var(--border);
                        border-radius: 10px; padding: 10px 14px; margin-bottom: 16px; }}
  .reporting-picker label {{ font-size: 11px; text-transform: uppercase;
                              letter-spacing: 0.08em; color: var(--muted);
                              font-weight: 700; }}
  #reporting-client-picker {{ font-family: var(--body); font-size: 14px;
                                padding: 8px 12px; border: 1px solid var(--border);
                                border-radius: 6px; background: white;
                                color: var(--text); font-weight: 600; min-width: 280px; }}

  /* Top Ads table — sortable views (Spend / Conversions / CPL / CTR) */
  .top-ads-tabs {{ display: flex; gap: 4px; margin: 8px 0 10px; flex-wrap: wrap; }}
  .top-ads-tab {{ padding: 6px 12px; font-size: 11px; font-weight: 700;
                   text-transform: uppercase; letter-spacing: 0.05em;
                   color: var(--muted); background: var(--soft); border: 1px solid var(--border);
                   border-radius: 6px; cursor: pointer; font-family: var(--body); }}
  .top-ads-tab:hover {{ color: var(--ink); }}
  .top-ads-tab.active {{ background: #2563EB; border-color: #2563EB; color: white; }}
  .top-ads-table {{ font-size: 12px; }}
  .top-ads-table .ad-name {{ max-width: 360px; }}
  .top-ads-table .ad-name-title {{ font-weight: 600; color: var(--ink);
                                    overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
                                    font-size: 12px; }}
  .top-ads-table .ad-name-campaign {{ font-size: 10px; color: var(--muted);
                                       overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
                                       margin-top: 2px; }}
  .top-ads-table .ad-thumb-cell {{ width: 56px; padding: 4px 8px; }}
  .ad-thumb-btn {{ display: block; padding: 0; border: 1px solid var(--border);
                    border-radius: 6px; background: white; cursor: pointer;
                    overflow: hidden; transition: border-color 0.15s, transform 0.15s;
                    width: 48px; height: 48px; }}
  .ad-thumb-btn:hover {{ border-color: #2563EB; transform: scale(1.06); }}
  .ad-thumb-btn img {{ width: 100%; height: 100%; object-fit: cover; display: block; }}
  .ad-thumb-empty {{ width: 48px; height: 48px; border: 1px dashed var(--border);
                      border-radius: 6px; display: flex; align-items: center;
                      justify-content: center; color: #cbd5e1; font-size: 18px; }}
  .ads-manager-link {{ color: #2563EB; font-weight: 600; text-decoration: none;
                        font-size: 10px; }}
  .ads-manager-link:hover {{ text-decoration: underline; }}

  /* Ad preview modal — opens when a thumbnail is clicked */
  .ad-preview-modal {{ display: none; position: fixed; inset: 0; z-index: 9999;
                        background: rgba(15, 23, 42, 0.78); align-items: center;
                        justify-content: center; padding: 24px; }}
  .ad-preview-modal.open {{ display: flex; }}
  .ad-preview-card {{ background: white; border-radius: 14px; max-width: 520px;
                       width: 100%; overflow: hidden; box-shadow: 0 20px 60px rgba(0,0,0,0.35); }}
  .ad-preview-header {{ display: flex; align-items: center; justify-content: space-between;
                          padding: 14px 18px; background: #f8fafc; border-bottom: 1px solid var(--border); }}
  .ad-preview-title {{ font-size: 11px; font-weight: 700; text-transform: uppercase;
                        letter-spacing: 0.06em; color: var(--muted); }}
  .ad-preview-close {{ background: transparent; border: 0; font-size: 22px; cursor: pointer;
                        color: var(--muted); line-height: 1; padding: 4px 8px; border-radius: 4px; }}
  .ad-preview-close:hover {{ background: var(--soft); color: var(--ink); }}
  .ad-preview-body {{ padding: 18px; }}
  .ad-preview-img {{ width: 100%; max-height: 420px; object-fit: contain;
                      background: #f1f5f9; border-radius: 8px; display: block; }}
  .ad-preview-meta {{ margin-top: 14px; }}
  .ad-preview-meta .ad-meta-name {{ font-size: 16px; font-weight: 700; color: var(--ink);
                                     line-height: 1.3; }}
  .ad-preview-meta .ad-meta-campaign {{ font-size: 12px; color: var(--muted); margin-top: 4px; }}
  .ad-preview-actions {{ display: flex; gap: 8px; padding: 0 18px 18px; }}
  .ad-preview-btn {{ flex: 1; padding: 10px 14px; background: #2563EB; color: white;
                      border: 0; border-radius: 8px; font-weight: 700; font-size: 12px;
                      text-transform: uppercase; letter-spacing: 0.05em; text-align: center;
                      text-decoration: none; cursor: pointer; }}
  .ad-preview-btn.secondary {{ background: var(--soft); color: var(--ink); }}
  .ad-preview-btn:hover {{ filter: brightness(0.95); text-decoration: none; }}

  /* Reporting service tabs — at top of each client's reporting panel.
     One tab per service (SEO + N paid-media). Active tab gets a colored
     bottom border + filled dot. */
  .rep-service-tabs {{ display: flex; gap: 4px; margin-bottom: 16px;
                        border-bottom: 1px solid var(--border); }}
  .rep-tab {{ display: inline-flex; align-items: center; gap: 8px;
              padding: 10px 16px; font-family: var(--body); font-weight: 700;
              font-size: 12px; text-transform: uppercase; letter-spacing: 0.06em;
              color: var(--muted); border: 0; background: transparent;
              cursor: pointer; border-bottom: 3px solid transparent;
              margin-bottom: -1px; transition: color 0.15s, border-color 0.15s; }}
  .rep-tab:hover {{ color: var(--ink); }}
  .rep-tab.active {{ color: var(--ink); border-bottom-width: 3px;
                     border-bottom-style: solid;
                     /* color comes from inline border-color set per-tab */ }}
  .rep-tab-dot {{ width: 8px; height: 8px; border-radius: 50%; display: inline-block;
                   opacity: 0.5; }}
  .rep-tab.active .rep-tab-dot {{ opacity: 1; }}
  .rep-service-view {{ }}

  /* Reporting view */
  .rep-disclaimer {{ background: #fef3c7; border: 1px solid #fde68a; color: #854d0e;
                      padding: 10px 14px; border-radius: 8px; margin-bottom: 16px;
                      font-size: 12px; }}
  .rep-section-title {{ font-family: var(--display); font-size: 24px; text-transform: uppercase;
                         letter-spacing: 0.02em; font-weight: 400; margin: 26px 0 8px 0;
                         color: var(--ink); border-bottom: 1px solid var(--border);
                         padding-bottom: 8px; }}
  .rep-source {{ font-family: var(--body); font-size: 11px; font-weight: 700;
                  color: var(--muted); letter-spacing: 0.08em; text-transform: uppercase;
                  margin-left: 8px; }}
  .rep-kpi-row {{ display: grid; grid-template-columns: repeat(3, 1fr); gap: 10px;
                   margin-bottom: 14px; }}
  .rep-kpi-row-4 {{ grid-template-columns: repeat(4, 1fr); }}
  .rep-kpi {{ background: white; border: 1px solid var(--border); border-radius: 10px;
              padding: 14px 16px; }}
  .rep-kpi-label {{ font-size: 10px; text-transform: uppercase; letter-spacing: 0.08em;
                     color: var(--muted); font-weight: 700; }}
  .rep-kpi-value {{ font-family: var(--display); font-size: 32px; line-height: 1.0;
                     color: var(--ink); margin-top: 4px; }}
  .rep-kpi-delta {{ font-size: 12px; font-weight: 700; margin-top: 4px; }}
  .rep-kpi-delta-label {{ color: var(--muted); font-weight: 500; }}
  .rep-chart-card {{ background: white; border: 1px solid var(--border); border-radius: 10px;
                      padding: 14px; margin-bottom: 14px; position: relative;
                      height: 320px; display: flex; flex-direction: column; }}
  .rep-chart-card .rep-chart-label {{ flex-shrink: 0; }}
  .rep-chart-card canvas.rep-chart {{ flex: 1 1 auto; min-height: 0 !important;
                                       width: 100% !important; max-height: 100% !important; }}
  .rep-chart-label {{ font-size: 11px; text-transform: uppercase; letter-spacing: 0.08em;
                       color: var(--muted); font-weight: 700; margin-bottom: 8px; }}
  .rep-chart-grid {{ display: grid; grid-template-columns: 1fr 1fr; gap: 10px;
                      margin-bottom: 14px; }}
  .rep-chart-grid .rep-chart-card {{ height: 260px; }}
  .rep-perf-table {{ width: 100%; border-collapse: collapse; font-size: 12px;
                      background: white; border: 1px solid var(--border); border-radius: 10px;
                      overflow: hidden; margin-bottom: 14px; }}
  .rep-perf-table th {{ background: var(--ink); color: white; padding: 8px 12px;
                         text-align: left; font-size: 10px; text-transform: uppercase;
                         letter-spacing: 0.08em; font-weight: 700; }}
  .rep-perf-table th.num, .rep-perf-table td.num {{ text-align: right;
                         font-variant-numeric: tabular-nums; }}
  .rep-perf-table td {{ padding: 8px 12px; border-bottom: 1px solid var(--border); }}
  .rep-perf-table tr:last-child td {{ border-bottom: none; }}
  .rep-page {{ font-weight: 600; max-width: 420px; overflow: hidden; text-overflow: ellipsis;
                white-space: nowrap; }}
</style>
</head>
<body>

<aside class="sidebar">
  <div class="sidebar-brand">
    <div class="sidebar-brand-name">{esc(agency.get("name", "Agency"))}</div>
    <div class="sidebar-brand-tag">{esc(agency.get("tagline", "Agency OS"))}</div>
  </div>
  <nav class="sidebar-nav">
    {nav_html}
  </nav>
</aside>

<main>
  <div class="page" data-page="clients">{clients_grid_html}</div>
  <div class="page" data-page="reporting" style="display:none">{reporting_html}</div>
  <div class="page" data-page="admin" style="display:none">{admin_html}</div>
  {''.join(client_pages)}
  {''.join(person_pages)}
</main>

<script>
// Hash routing
function route() {{
  const hash = window.location.hash.replace(/^#/, '') || 'clients';
  const parts = hash.split('/');
  document.querySelectorAll('.page').forEach(p => p.style.display = 'none');
  let pageKey = hash;
  let subView = null;
  let reportingClient = null;
  let reportingService = null;   // 'seo' | 'social_ads' | 'ppc' | 'lsa' | null
  if (parts[0] === 'client' && parts.length >= 2) {{
    pageKey = 'client/' + parts[1];
    subView = parts[2] || null;
  }} else if (parts[0] === 'reporting' && parts.length >= 2) {{
    pageKey = 'reporting';
    reportingClient = parts[1];
    reportingService = parts[2] || null;
  }} else if (parts[0] === 'person' && parts.length >= 2) {{
    // #person/email — emails can contain '@' which is fine in hash
    pageKey = 'person/' + parts.slice(1).join('/');
  }}
  let target = document.querySelector(`.page[data-page="${{pageKey}}"]`);
  let navKey = parts[0];
  if (!target) {{
    target = document.querySelector('.page[data-page="clients"]');
    navKey = 'clients';
  }}
  target.style.display = '';
  if (subView) {{
    const btn = target.querySelector(`.view-tabs .view-tab[data-view="${{subView}}"]`);
    if (btn) btn.click();
  }}
  if (navKey === 'reporting') {{
    showReportingClient(reportingClient, reportingService);
  }}
  // Nav active state: person pages map to admin
  const activeNav = (navKey === 'client') ? 'clients'
                  : (navKey === 'person') ? 'admin'
                  : navKey;
  document.querySelectorAll('.nav-item').forEach(n => {{
    n.classList.toggle('active', n.dataset.nav === activeNav);
  }});
  window.scrollTo(0, 0);
}}

// Reporting page: pick a client to view their reports.
// Optional 'service' arg selects a service tab (seo / social_ads / ppc / lsa).
function showReportingClient(slug, service) {{
  const panels = document.querySelectorAll('.reporting-panel');
  if (!panels.length) return;
  if (!slug) slug = panels[0].dataset.reportingClient;
  panels.forEach(p => {{
    const match = p.dataset.reportingClient === slug;
    p.style.display = match ? '' : 'none';
    if (match) {{
      // Activate the requested service tab (default to seo).
      const tab = service || 'seo';
      switchReportingService(p, tab);
      initChartsForPanel(p);
    }}
  }});
  const picker = document.getElementById('reporting-client-picker');
  if (picker && picker.value !== slug) picker.value = slug;
}}

// Toggle which service-view is visible within a reporting panel.
function switchReportingService(panel, service) {{
  panel.querySelectorAll('.rep-service-view').forEach(v => {{
    v.style.display = (v.dataset.repService === service) ? '' : 'none';
  }});
  panel.querySelectorAll('.rep-tab').forEach(t => {{
    t.classList.toggle('active', t.dataset.repService === service);
  }});
}}

// Wire tab clicks → update hash so it's deep-linkable
document.addEventListener('click', e => {{
  const btn = e.target.closest('.rep-tab');
  if (!btn) return;
  const panel = btn.closest('.reporting-panel');
  if (!panel) return;
  const slug = panel.dataset.reportingClient;
  const svc  = btn.dataset.repService;
  window.location.hash = '#reporting/' + slug + '/' + svc;
}});

// Top Ads sub-tabs (By Spend / Conversions / CPL / CTR) — local to the Social Ads view.
document.addEventListener('click', e => {{
  const btn = e.target.closest('.top-ads-tab');
  if (!btn) return;
  const rank = btn.dataset.rank;
  const container = btn.parentElement.parentElement;
  container.querySelectorAll('.top-ads-tab').forEach(t => {{
    t.classList.toggle('active', t.dataset.rank === rank);
  }});
  container.querySelectorAll('.top-ads-view').forEach(v => {{
    v.style.display = (v.dataset.rank === rank) ? '' : 'none';
  }});
}});

document.getElementById('reporting-client-picker')?.addEventListener('change', e => {{
  const slug = e.target.value;
  window.location.hash = '#reporting/' + slug;
}});

// Chart.js — lazy init for the visible reporting panel
const _initedCharts = new Set();
function initChartsForPanel(panel) {{
  if (typeof Chart === 'undefined' || !window.REPORT_DATA) return;
  const slug = panel.dataset.reportingClient;
  if (!slug || !window.REPORT_DATA[slug]) return;
  const data = window.REPORT_DATA[slug];
  panel.querySelectorAll('canvas.rep-chart').forEach(canvas => {{
    const id = canvas.dataset.chartId;
    if (_initedCharts.has(id)) return;
    const key = canvas.dataset.chartKey;
    const series = data[key];
    if (!series) return;
    const type = canvas.dataset.chartType || 'line';
    // Per-section color comes from the chart payload (set in render_reporting_view).
    // Falls back to the agency primary color if a series doesn't specify one.
    const color = series.color || '{PRIMARY}';
    new Chart(canvas, {{
      type,
      data: {{
        labels: series.labels,
        datasets: [{{
          label: key, data: series.data,
          borderColor: color,
          backgroundColor: type === 'bar' ? color + '99' : color + '22',
          borderWidth: 2, fill: type !== 'bar',
          tension: 0.3, pointRadius: 2,
        }}],
      }},
      options: {{
        responsive: true, maintainAspectRatio: false,
        plugins: {{ legend: {{ display: false }} }},
        scales: {{
          x: {{ ticks: {{ font: {{ size: 10 }} }}, grid: {{ display: false }} }},
          y: {{ ticks: {{ font: {{ size: 10 }} }}, beginAtZero: false }},
        }},
      }},
    }});
    _initedCharts.add(id);
  }});
}}
window.addEventListener('hashchange', route);
window.addEventListener('DOMContentLoaded', route);

// Person page filters (client / status / search)
document.querySelectorAll('.person-filters').forEach(bar => {{
  const page = bar.closest('.page');
  if (!page) return;
  const clientSel = bar.querySelector('.pf-client');
  const statusSel = bar.querySelector('.pf-status');
  const searchInp = bar.querySelector('.pf-search');
  function apply() {{
    const c = clientSel.value;
    const s = statusSel.value;
    const q = (searchInp.value || '').toLowerCase().trim();
    page.querySelectorAll('details.row').forEach(r => {{
      let show = true;
      if (c && r.dataset.client !== c) show = false;
      if (s && r.dataset.status !== s) show = false;
      if (q && !(r.dataset.search || '').includes(q)) show = false;
      r.classList.toggle('filtered-out', !show);
    }});
  }}
  clientSel.addEventListener('change', apply);
  statusSel.addEventListener('change', apply);
  searchInp.addEventListener('input', apply);
}});

// Person card click → switch to Tasks tab and filter to that assignee
document.querySelectorAll('.person-card.clickable').forEach(card => {{
  card.addEventListener('click', () => {{
    const slug = card.dataset.jumpClient;
    const email = card.dataset.jumpEmail;
    const page = document.querySelector(`.page[data-client="${{slug}}"]`);
    if (!page) return;
    // Switch to Tasks tab
    const tasksBtn = page.querySelector('.view-tabs .view-tab[data-view="tasks"]');
    if (tasksBtn) tasksBtn.click();
    // Set assignee filter to this person, trigger filter
    const assigneeSel = page.querySelector('.filters .f-assignee');
    if (assigneeSel) {{
      assigneeSel.value = email;
      assigneeSel.dispatchEvent(new Event('change'));
    }}
    // Scroll to the table top
    const table = page.querySelector('.task-table');
    if (table) table.scrollIntoView({{ behavior: 'smooth', block: 'start' }});
  }});
}});

// Live Content + Live Links counts are now rendered server-side from the
// sheet caches (content_workbook.json + link_db.json). The build script
// computes them via sheets_sync.is_content_live() and is_link_live().
// No client-side localStorage logic is needed.

// Clients page filter + search + inactive toggle
(function() {{
  const search = document.getElementById('client-search');
  const showInactive = document.getElementById('show-inactive');
  const container = document.getElementById('client-rows-container');
  if (!container) return;
  function apply() {{
    const q = (search?.value || '').toLowerCase().trim();
    const includeInactive = showInactive?.checked;
    container.querySelectorAll('.client-row').forEach(row => {{
      const status = row.dataset.status;
      const name = row.dataset.name || '';
      let show = true;
      if (!includeInactive && status === 'inactive') show = false;
      if (q && !name.includes(q)) show = false;
      row.classList.toggle('hidden', !show);
    }});
  }}
  // Default: hide inactive
  apply();
  search?.addEventListener('input', apply);
  showInactive?.addEventListener('change', apply);
}})();

// Admin sub-tab switching
document.querySelectorAll('[data-admin-tabs] .view-tab').forEach(tab => {{
  tab.addEventListener('click', () => {{
    document.querySelectorAll('[data-admin-tabs] .view-tab').forEach(t => t.classList.remove('active'));
    tab.classList.add('active');
    document.querySelectorAll('.admin-panel').forEach(p => {{
      const match = p.dataset.adminPanel === tab.dataset.adminTab;
      p.classList.toggle('active', match);
      // Override inline style too so CSS .active rule applies
      p.style.display = match ? 'block' : 'none';
    }});
  }});
}});

// View tab switching (per-client)
document.querySelectorAll('.view-tabs').forEach(tabs => {{
  const clientSlug = tabs.dataset.client;
  if (!clientSlug) return;
  tabs.querySelectorAll('.view-tab').forEach(t => {{
    t.addEventListener('click', () => {{
      tabs.querySelectorAll('.view-tab').forEach(x => x.classList.remove('active'));
      t.classList.add('active');
      const page = document.querySelector(`.page[data-client="${{clientSlug}}"]`);
      page.querySelectorAll('.view').forEach(v => v.classList.remove('active'));
      page.querySelector(`.view[data-view="${{t.dataset.view}}"]`).classList.add('active');
    }});
  }});
}});

// Prevent link clicks from toggling row expansion
document.querySelectorAll('details.row a').forEach(a => {{
  a.addEventListener('click', e => e.stopPropagation());
}});

// ============ Status options + colors (from Python STATUS_OPTIONS) ============
const STATUS_OPTIONS = {json.dumps([(k, label, bg, fg) for k, label, bg, fg in STATUS_OPTIONS])};
const STATUS_LOOKUP = {{}};
STATUS_OPTIONS.forEach(([k, label, bg, fg]) => {{ STATUS_LOOKUP[k] = {{label, bg, fg}}; }});

// ============ localStorage hydration ============
function loadStoredStatus(id) {{
  try {{ return localStorage.getItem('task-status::' + id); }} catch (e) {{ return null; }}
}}
function saveStoredStatus(id, status) {{
  try {{ localStorage.setItem('task-status::' + id, status); }} catch (e) {{}}
}}

function setPillStatus(pill, status) {{
  const opt = STATUS_LOOKUP[status];
  if (!opt) return;
  pill.dataset.status = status;
  pill.style.background = opt.bg;
  pill.style.color = opt.fg;
  pill.querySelector('.pill-label').textContent = opt.label;
  // Also update parent row dataset so filters work
  const row = pill.closest('details.row');
  if (row) row.dataset.status = status;
}}

// Hydrate stored statuses on load
document.querySelectorAll('.status-pill.editable[data-id]').forEach(pill => {{
  const id = pill.dataset.id;
  const stored = loadStoredStatus(id);
  if (stored && STATUS_LOOKUP[stored]) {{
    setPillStatus(pill, stored);
  }}
}});

// ============ Editable dates (localStorage; browser-only, not synced to system data) ============
function dateKey(id, field) {{ return 'task-date::' + id + '::' + field; }}
document.querySelectorAll('input.date-edit[data-id]').forEach(inp => {{
  const id = inp.dataset.id, field = inp.dataset.field;
  try {{ const s = localStorage.getItem(dateKey(id, field)); if (s !== null) inp.value = s; }} catch (e) {{}}
  const row = inp.closest('details.row');
  if (row) row.dataset[field] = inp.value || '9999-99-99';
  inp.addEventListener('click', e => e.stopPropagation());
  inp.addEventListener('change', e => {{
    e.stopPropagation();
    try {{ localStorage.setItem(dateKey(id, field), inp.value); }} catch (e2) {{}}
    if (row) row.dataset[field] = inp.value || '9999-99-99';
    if (field === 'due') {{
      const today = new Date().toISOString().slice(0, 10);
      const st = row ? row.dataset.status : '';
      inp.classList.toggle('overdue', !!inp.value && inp.value < today && st !== 'completed' && st !== 'approved');
    }}
  }});
}});

// ============ Status dropdown menu ============
let openMenu = null;
function closeStatusMenu() {{
  if (openMenu) {{ openMenu.remove(); openMenu = null; }}
}}
document.addEventListener('click', e => {{
  if (openMenu && !openMenu.contains(e.target)) closeStatusMenu();
}});

document.querySelectorAll('.status-pill.editable').forEach(pill => {{
  pill.addEventListener('click', e => {{
    e.stopPropagation();
    e.preventDefault();
    closeStatusMenu();
    const menu = document.createElement('div');
    menu.className = 'status-menu';
    STATUS_OPTIONS.forEach(([k, label, bg, fg]) => {{
      const item = document.createElement('div');
      item.className = 'status-menu-item';
      item.innerHTML = `<span class="status-menu-swatch" style="background:${{bg}}"></span><span>${{label}}</span>`;
      item.addEventListener('click', ev => {{
        ev.stopPropagation();
        setPillStatus(pill, k);
        saveStoredStatus(pill.dataset.id, k);
        closeStatusMenu();
      }});
      menu.appendChild(item);
    }});
    document.body.appendChild(menu);
    const r = pill.getBoundingClientRect();
    menu.style.top = (window.scrollY + r.bottom + 4) + 'px';
    menu.style.left = (window.scrollX + r.left) + 'px';
    openMenu = menu;
  }});
}});

// ============ Sortable column headers ============
function sortBody(body, sortKey, direction) {{
  const rows = Array.from(body.querySelectorAll(':scope > details.row'));
  rows.sort((a, b) => {{
    let av, bv;
    if (sortKey === 'due') {{ av = a.dataset.due || ''; bv = b.dataset.due || ''; }}
    else if (sortKey === 'owner') {{ av = a.dataset.assignee || ''; bv = b.dataset.assignee || ''; }}
    else if (sortKey === 'bucket') {{ av = a.dataset.sprint || ''; bv = b.dataset.sprint || ''; }}
    else if (sortKey === 'task') {{ av = a.dataset.name || ''; bv = b.dataset.name || ''; }}
    else {{ av = ''; bv = ''; }}
    const cmp = av < bv ? -1 : av > bv ? 1 : 0;
    return direction === 'desc' ? -cmp : cmp;
  }});
  rows.forEach(r => body.appendChild(r));
}}

document.querySelectorAll('.task-table').forEach(table => {{
  table.querySelectorAll('.table-header .sortable').forEach(header => {{
    header.addEventListener('click', e => {{
      if (e.target.classList.contains('resize-handle')) return;
      const key = header.dataset.sort;
      const cur = header.classList.contains('sort-asc') ? 'asc' :
                  header.classList.contains('sort-desc') ? 'desc' : null;
      const next = cur === 'asc' ? 'desc' : 'asc';
      table.querySelectorAll('.sortable').forEach(h => h.classList.remove('sort-asc', 'sort-desc'));
      header.classList.add(next === 'asc' ? 'sort-asc' : 'sort-desc');
      table.querySelectorAll('.flat-body').forEach(b => sortBody(b, key, next));
    }});
  }});
}});

// Mark default sort indicator (due ASC)
document.querySelectorAll('.task-table .table-header .sortable[data-sort="due"]').forEach(h => {{
  h.classList.add('sort-asc');
}});

// ============ Column resize ============
document.querySelectorAll('.resize-handle').forEach(handle => {{
  handle.addEventListener('mousedown', e => {{
    e.preventDefault();
    e.stopPropagation();
    const col = handle.dataset.col;
    const table = handle.closest('.task-table');
    const startX = e.clientX;
    const cur = getComputedStyle(table).getPropertyValue('--w-' + col).trim();
    const startW = parseFloat(cur) || 100;
    handle.classList.add('dragging');
    document.body.style.cursor = 'col-resize';
    function onMove(ev) {{
      const newW = Math.max(60, Math.min(800, startW + (ev.clientX - startX)));
      table.style.setProperty('--w-' + col, newW + 'px');
    }}
    function onUp() {{
      document.removeEventListener('mousemove', onMove);
      document.removeEventListener('mouseup', onUp);
      handle.classList.remove('dragging');
      document.body.style.cursor = '';
      // Persist widths per table
      try {{
        const widths = {{}};
        ['start','due','status','owner','bucket','task','deliverable'].forEach(c => {{
          widths[c] = getComputedStyle(table).getPropertyValue('--w-' + c).trim();
        }});
        localStorage.setItem('col-widths::' + table.dataset.tableId, JSON.stringify(widths));
      }} catch (e) {{}}
    }}
    document.addEventListener('mousemove', onMove);
    document.addEventListener('mouseup', onUp);
  }});
}});

// Restore saved column widths
document.querySelectorAll('.task-table').forEach((table, i) => {{
  if (!table.dataset.tableId) table.dataset.tableId = (table.closest('.page')?.dataset.client || 'p') + '::' + i;
  try {{
    const stored = localStorage.getItem('col-widths::' + table.dataset.tableId);
    if (stored) {{
      const widths = JSON.parse(stored);
      Object.entries(widths).forEach(([col, w]) => table.style.setProperty('--w-' + col, w));
    }}
  }} catch (e) {{}}
}});

// ============ Editable cells (contenteditable) — persist to localStorage ============
document.querySelectorAll('.editable-cell').forEach(cell => {{
  const id = cell.dataset.id;
  const field = cell.dataset.field;
  if (!id || !field) return;
  const key = 'cell::' + id + '::' + field;
  try {{
    const stored = localStorage.getItem(key);
    if (stored !== null) cell.textContent = stored;
  }} catch (e) {{}}
  cell.addEventListener('blur', () => {{
    try {{ localStorage.setItem(key, cell.textContent.trim()); }} catch (e) {{}}
  }});
  cell.addEventListener('keydown', e => {{
    if (e.key === 'Enter') {{ e.preventDefault(); cell.blur(); }}
  }});
}});

// ============ Content status dropdown (different option set) ============
document.querySelectorAll('.status-pill.content-status').forEach(pill => {{
  const id = pill.dataset.contentId;
  const key = 'content-status::' + id;
  try {{
    const stored = localStorage.getItem(key);
    if (stored && window.CONTENT_STATUS_OPTIONS) {{
      const opt = window.CONTENT_STATUS_OPTIONS.find(o => o[0] === stored);
      if (opt) {{
        pill.dataset.status = opt[0];
        pill.style.background = opt[2];
        pill.style.color = opt[3];
        pill.querySelector('.pill-label').textContent = opt[1];
        const row = pill.closest('.row'); if (row) row.dataset.status = opt[0];
      }}
    }}
  }} catch (e) {{}}
  pill.addEventListener('click', e => {{
    e.stopPropagation();
    e.preventDefault();
    closeStatusMenu();
    if (!window.CONTENT_STATUS_OPTIONS) return;
    const menu = document.createElement('div');
    menu.className = 'status-menu';
    window.CONTENT_STATUS_OPTIONS.forEach(([k, label, bg, fg]) => {{
      const item = document.createElement('div');
      item.className = 'status-menu-item';
      item.innerHTML = `<span class="status-menu-swatch" style="background:${{bg}}"></span><span>${{label}}</span>`;
      item.addEventListener('click', ev => {{
        ev.stopPropagation();
        pill.dataset.status = k;
        pill.style.background = bg;
        pill.style.color = fg;
        pill.querySelector('.pill-label').textContent = label;
        const row = pill.closest('.row'); if (row) row.dataset.status = k;
        try {{ localStorage.setItem(key, k); }} catch (e) {{}}
        closeStatusMenu();
      }});
      menu.appendChild(item);
    }});
    document.body.appendChild(menu);
    const r = pill.getBoundingClientRect();
    menu.style.top = (window.scrollY + r.bottom + 4) + 'px';
    menu.style.left = (window.scrollX + r.left) + 'px';
    openMenu = menu;
  }});
}});

// ============ Deliverables tab — add/edit/delete ============
function loadDeliverables(slug) {{
  try {{ return JSON.parse(localStorage.getItem('deliverables::' + slug) || '[]'); }}
  catch (e) {{ return []; }}
}}
function saveDeliverables(slug, list) {{
  try {{ localStorage.setItem('deliverables::' + slug, JSON.stringify(list)); }} catch (e) {{}}
}}
function renderDeliverables(slug) {{
  const body = document.getElementById('deliverables-' + slug);
  if (!body) return;
  const list = loadDeliverables(slug);
  if (!list.length) {{
    body.innerHTML = '<div class="empty-row">No deliverables logged yet. Click "+ Add Deliverable" to record the first one.</div>';
    return;
  }}
  const opts = window.DELIVERABLE_STATUS_OPTIONS || [];
  const optLookup = {{}}; opts.forEach(o => optLookup[o[0]] = o);
  body.innerHTML = list.map((d, i) => {{
    const opt = optLookup[d.status] || opts[0] || ['scheduled','Scheduled','#cffafe','#155e75'];
    return `
      <div class="deliverable-row" data-idx="${{i}}">
        <div class="cell cell-d-date editable" contenteditable="true" data-d-field="send_date">${{d.send_date || ''}}</div>
        <div class="cell cell-d-sender editable" contenteditable="true" data-d-field="sender">${{d.sender || ''}}</div>
        <div class="cell cell-d-name editable" contenteditable="true" data-d-field="name">${{d.name || ''}}</div>
        <div class="cell cell-d-status"><span class="status-pill deliverable-status" data-d-idx="${{i}}" style="background:${{opt[2]}};color:${{opt[3]}}"><span class="pill-label">${{opt[1]}}</span><span class="pill-caret">▾</span></span></div>
        <div class="cell cell-d-link"><a href="${{d.link || '#'}}" target="_blank">${{d.link || ''}}</a> <span class="editable" contenteditable="true" data-d-field="link" style="font-size:11px;color:#94a3b8">[edit]</span></div>
        <div class="cell cell-d-notes editable" contenteditable="true" data-d-field="notes">${{d.notes || ''}}</div>
        <div class="cell cell-d-actions"><a href="#" onclick="removeDeliverable('${{slug}}',${{i}});return false;" style="color:#dc2626;font-size:11px;">Delete</a></div>
      </div>`;
  }}).join('');
  // Wire up editable fields
  body.querySelectorAll('[data-d-field]').forEach(el => {{
    el.addEventListener('blur', () => {{
      const row = el.closest('.deliverable-row');
      const i = parseInt(row.dataset.idx);
      const list = loadDeliverables(slug);
      list[i][el.dataset.dField] = el.textContent.trim();
      saveDeliverables(slug, list);
    }});
    el.addEventListener('keydown', e => {{ if (e.key === 'Enter') {{ e.preventDefault(); el.blur(); }} }});
  }});
  // Wire up status pills
  body.querySelectorAll('.deliverable-status').forEach(pill => {{
    pill.addEventListener('click', e => {{
      e.stopPropagation(); e.preventDefault(); closeStatusMenu();
      const menu = document.createElement('div');
      menu.className = 'status-menu';
      opts.forEach(([k, label, bg, fg]) => {{
        const item = document.createElement('div');
        item.className = 'status-menu-item';
        item.innerHTML = `<span class="status-menu-swatch" style="background:${{bg}}"></span><span>${{label}}</span>`;
        item.addEventListener('click', ev => {{
          ev.stopPropagation();
          const idx = parseInt(pill.dataset.dIdx);
          const list = loadDeliverables(slug);
          list[idx].status = k;
          saveDeliverables(slug, list);
          pill.style.background = bg;
          pill.style.color = fg;
          pill.querySelector('.pill-label').textContent = label;
          closeStatusMenu();
        }});
        menu.appendChild(item);
      }});
      document.body.appendChild(menu);
      const r = pill.getBoundingClientRect();
      menu.style.top = (window.scrollY + r.bottom + 4) + 'px';
      menu.style.left = (window.scrollX + r.left) + 'px';
      openMenu = menu;
    }});
  }});
}}
window.addDeliverable = function(slug) {{
  const list = loadDeliverables(slug);
  const today = new Date();
  const mmddyy = String(today.getMonth()+1).padStart(2,'0') + '/' + String(today.getDate()).padStart(2,'0') + '/' + String(today.getFullYear()).slice(2);
  list.push({{ send_date: mmddyy, sender: 'Ryan', name: 'New deliverable', status: 'scheduled', link: '', notes: '' }});
  saveDeliverables(slug, list);
  renderDeliverables(slug);
}};
window.removeDeliverable = function(slug, idx) {{
  const list = loadDeliverables(slug);
  list.splice(idx, 1);
  saveDeliverables(slug, list);
  renderDeliverables(slug);
}};
// Initial render of custom deliverables for each client
document.querySelectorAll('.custom-deliverables-table').forEach(t => {{
  const slug = t.dataset.client;
  if (slug) renderDeliverables(slug);
}});

// Auto-deliverable status pills (rolled up from tasks)
document.querySelectorAll('.status-pill.auto-deliverable-status').forEach(pill => {{
  const id = pill.dataset.autoId;
  const key = 'auto-deliverable-status::' + id;
  try {{
    const stored = localStorage.getItem(key);
    if (stored && window.DELIVERABLE_STATUS_OPTIONS) {{
      const opt = window.DELIVERABLE_STATUS_OPTIONS.find(o => o[0] === stored);
      if (opt) {{
        pill.dataset.status = opt[0];
        pill.style.background = opt[2];
        pill.style.color = opt[3];
        pill.querySelector('.pill-label').textContent = opt[1];
      }}
    }}
  }} catch (e) {{}}
  pill.addEventListener('click', e => {{
    e.stopPropagation(); e.preventDefault(); closeStatusMenu();
    const opts = window.DELIVERABLE_STATUS_OPTIONS || [];
    const menu = document.createElement('div');
    menu.className = 'status-menu';
    opts.forEach(([k, label, bg, fg]) => {{
      const item = document.createElement('div');
      item.className = 'status-menu-item';
      item.innerHTML = `<span class="status-menu-swatch" style="background:${{bg}}"></span><span>${{label}}</span>`;
      item.addEventListener('click', ev => {{
        ev.stopPropagation();
        pill.dataset.status = k;
        pill.style.background = bg;
        pill.style.color = fg;
        pill.querySelector('.pill-label').textContent = label;
        try {{ localStorage.setItem(key, k); }} catch (e) {{}}
        closeStatusMenu();
      }});
      menu.appendChild(item);
    }});
    document.body.appendChild(menu);
    const r = pill.getBoundingClientRect();
    menu.style.top = (window.scrollY + r.bottom + 4) + 'px';
    menu.style.left = (window.scrollX + r.left) + 'px';
    openMenu = menu;
  }});
}});

// ============ Filters ============
document.querySelectorAll('.filters').forEach(bar => {{
  const clientSlug = bar.dataset.client;
  const page = document.querySelector(`.page[data-client="${{clientSlug}}"]`);
  const sprintSel = bar.querySelector('.f-sprint');
  const assigneeSel = bar.querySelector('.f-assignee');
  const statusSel = bar.querySelector('.f-status');
  const aiPill = bar.querySelector('.f-ai');
  const searchInp = bar.querySelector('.f-search');
  function apply() {{
    const sprint = sprintSel.value;
    const assignee = assigneeSel.value;
    const status = statusSel.value;
    const aiOnly = aiPill.dataset.active === '1';
    const search = searchInp.value.toLowerCase().trim();
    page.querySelectorAll('details.row').forEach(r => {{
      let show = true;
      if (sprint && r.dataset.sprint !== sprint) show = false;
      if (assignee && r.dataset.assignee !== assignee) show = false;
      if (status && r.dataset.status !== status) show = false;
      if (aiOnly && r.dataset.ai !== '1') show = false;
      if (search && !(r.dataset.search || '').includes(search)) show = false;
      r.classList.toggle('filtered-out', !show);
    }});
  }}
  sprintSel.addEventListener('change', apply);
  assigneeSel.addEventListener('change', apply);
  statusSel.addEventListener('change', apply);
  searchInp.addEventListener('input', apply);
  aiPill.addEventListener('click', () => {{
    const cur = aiPill.dataset.active === '1';
    aiPill.dataset.active = cur ? '0' : '1';
    aiPill.classList.toggle('active', !cur);
    apply();
  }});
}});

// Ad preview modal — wire thumbnail clicks to a single shared modal.
// Each thumbnail button carries the data needed to populate the modal
// via data-* attributes (set in render_reporting_view's _row function).
document.addEventListener('click', e => {{
  const btn = e.target.closest('.ad-thumb-btn');
  if (btn) {{
    const modal = document.getElementById('ad-preview-modal');
    if (!modal) return;
    const thumb    = btn.dataset.thumbUrl;
    const adName   = btn.dataset.adName || '';
    const campaign = btn.dataset.campaign || '';
    const adId     = btn.dataset.adId || '';
    const accountId = btn.dataset.accountId || '';
    modal.querySelector('.ad-preview-img').src = thumb;
    modal.querySelector('.ad-preview-img').alt = adName;
    modal.querySelector('.ad-meta-name').textContent = adName;
    modal.querySelector('.ad-meta-campaign').textContent = campaign;
    const adsManagerBtn = modal.querySelector('.ad-preview-btn.primary');
    const openImgBtn    = modal.querySelector('.ad-preview-btn.secondary');
    if (adId && accountId) {{
      adsManagerBtn.href = `https://www.facebook.com/adsmanager/manage/ads?act=${{accountId}}&selected_ad_ids=${{adId}}`;
      adsManagerBtn.style.display = '';
    }} else {{
      adsManagerBtn.style.display = 'none';
    }}
    openImgBtn.href = thumb;
    modal.classList.add('open');
    return;
  }}
  // Click outside the card → close
  if (e.target.classList?.contains('ad-preview-modal')) {{
    e.target.classList.remove('open');
    return;
  }}
  // Close button
  if (e.target.closest('.ad-preview-close')) {{
    document.getElementById('ad-preview-modal')?.classList.remove('open');
  }}
}});
// Escape to close
document.addEventListener('keydown', e => {{
  if (e.key === 'Escape') {{
    document.getElementById('ad-preview-modal')?.classList.remove('open');
  }}
}});
</script>

<!-- Shared ad preview modal — single instance reused for any thumbnail click. -->
<div class="ad-preview-modal" id="ad-preview-modal">
  <div class="ad-preview-card" onclick="event.stopPropagation()">
    <div class="ad-preview-header">
      <span class="ad-preview-title">Ad Preview</span>
      <button class="ad-preview-close" aria-label="Close">×</button>
    </div>
    <div class="ad-preview-body">
      <img class="ad-preview-img" src="" alt="" />
      <div class="ad-preview-meta">
        <div class="ad-meta-name"></div>
        <div class="ad-meta-campaign"></div>
      </div>
    </div>
    <div class="ad-preview-actions">
      <a class="ad-preview-btn primary" href="#" target="_blank" rel="noopener">Open in Ads Manager ↗</a>
      <a class="ad-preview-btn secondary" href="#" target="_blank" rel="noopener">View Full Image ↗</a>
    </div>
  </div>
</div>
</body>
</html>
"""

with open(args.output, "w") as f:
    f.write(html)
print(f"Saved: {args.output} ({len(html):,} bytes)")
print(f"  Today: {TODAY}")
print(f"  Clients: {len(client_data)} ({len(grid_active)} active, {len(grid_onboarding)} onboarding, {len(grid_inactive)} inactive)")
for cd in client_data:
    plan = cd["plan_info"]
    if plan:
        ds = plan["plan"]["deliverables"]
        by_st = Counter(default_status(d) for d in ds)
        print(f"    · {cd['client'].get('company_name')} [{cd['status']}] — {len(ds)} deliverables")
        for k, label, _, _ in STATUS_OPTIONS:
            if by_st[k]:
                print(f"        {label}: {by_st[k]}")
    else:
        print(f"    · {cd['client'].get('company_name')} [{cd['status']}] — no plan")
