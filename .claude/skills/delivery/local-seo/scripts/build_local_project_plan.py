#!/usr/bin/env python3
"""build_local_project_plan.py — turn Local SEO audit approvals into a Sprint 3
deliverables patch that `project_plan_import` can apply.

The /bpt-project-plan skill emits Sprint 3 (Local SEO) with placeholder deliverables
when the client's vertical == "local_service". This script reads
{slug}-local-approvals.json and emits a structured payload that the agent then
hands to `project_plan_import` with replace_existing=true. The MCP tool overwrites
the existing Sprint 3 placeholders with these tailored deliverables.

Sprint 3 deliverables map to the standard step numbers in the productization
playbook (the Local SEO chapter):
  Step 4  GBP Optimization        ← category == "GBP"
  Step 5  Reviews                  ← category == "Reviews"
  Step 6  Citation Management      ← category == "Citations"
  Step 7  Local Links              ← category == "Local Links"
  Step 8  Website Architecture     ← category == "Local Content" (architecture subset)
  Step 9  Service Area Content     ← category == "Local Content" (content subset)

Each approved/edited row becomes one deliverable carrying:
  - name              From `action` (truncated)
  - description       From `specific_next_step` (strategist's edit) or `action`
  - sprint_step       Mapped step number above
  - priority          P1/P2/P3
  - source            audit row + category + finding for traceability
  - assigned_to_email Optional, defaults to team-member matched on assigned_skill

Usage:
  python3 build_local_project_plan.py \\
    --client-slug batch-williams \\
    --audit-id <audit-uuid> \\
    --workspace-root /path/to/agency \\
    --client-id <client-uuid> \\
    --project-id <project-uuid> \\
    --output /path/to/local-sprint3-patch.json
"""

import argparse
import json
import os
import sys
from pathlib import Path

parser = argparse.ArgumentParser()
parser.add_argument("--client-slug", required=True)
parser.add_argument("--audit-id", required=True)
parser.add_argument("--workspace-root", default=os.environ.get("AGENCY_OS_ROOT", "."))
parser.add_argument("--client-id", required=True, help="Client UUID (for project_plan_import)")
parser.add_argument("--project-id", help="Existing project UUID to patch into. Required for replace_existing.")
parser.add_argument("--output", help="Where to write the Sprint 3 patch JSON (defaults to audit dir)")
args = parser.parse_args()

SLUG = args.client_slug
AUDIT_DIR = Path(args.workspace_root) / "clients" / SLUG / "local-audit" / args.audit_id
APPROVALS = AUDIT_DIR / f"{SLUG}-local-approvals.json"

if not APPROVALS.exists():
    sys.exit(f"approvals not found: {APPROVALS}. Run parse_local_approvals.py first.")

approvals = json.loads(APPROVALS.read_text())
active = (approvals.get("buckets", {}).get("Approved") or []) + \
         (approvals.get("buckets", {}).get("Edited") or [])

if not active:
    sys.exit("No Approved or Edited rows in approvals — nothing to push.")

# Category → Sprint 3 step number + step name
STEP_MAP = {
    "gbp":              (4, "GBP Optimization"),
    "google business":  (4, "GBP Optimization"),
    "reviews":          (5, "Review Generation"),
    "citations":        (6, "Citation Management"),
    "citation":         (6, "Citation Management"),
    "local links":      (7, "Local Link Building"),
    "links":            (7, "Local Link Building"),
    "local content":    (9, "Service Area Content"),
    "service area":     (9, "Service Area Content"),
    "architecture":     (8, "Website Architecture"),
    "schema":           (8, "Website Architecture"),
}

def map_step(category: str) -> tuple[int, str]:
    c = (category or "").strip().lower()
    for needle, step in STEP_MAP.items():
        if needle in c:
            return step
    return (10, "Other Local SEO")  # catch-all

# Skill → email lookup (optional; falls back to project_plan_import's default routing)
skill_to_email: dict[str, str] = {}
team_path = Path(args.workspace_root) / "data" / "team.json"
if team_path.exists():
    try:
        team = json.loads(team_path.read_text())
        for member in team:
            if not member.get("active", True):
                continue
            for s in (member.get("skills") or []):
                skill_to_email.setdefault(s.lower(), member["email"])
    except Exception:
        pass

def email_for_skill(skill: str) -> str | None:
    return skill_to_email.get((skill or "").lower())

deliverables: list[dict] = []
for row in active:
    step_num, step_name = map_step(row.get("category", ""))
    description = row.get("specific_next_step") or row.get("action") or ""
    name = (row.get("action") or description or "Local SEO action").strip()
    if len(name) > 120:
        name = name[:117] + "..."

    deliverables.append({
        "name": name,
        "description": description,
        "deliverable_type": "local_seo",
        # Coerce non-enum priorities (e.g. "—", "", informational sub-rows)
        # to P3 so project_plan_import accepts them.
        "priority": (lambda p: p if p in ("P1", "P2", "P3") else "P3")(
            (row.get("priority") or "P2").upper()
        ),
        "sprint_step": step_num,
        "step_name": step_name,
        "category": row.get("category", ""),
        "assigned_to_email": email_for_skill(row.get("assigned_skill") or ""),
        "is_placeholder": False,
        "source": {
            "audit_id": args.audit_id,
            "audit_row": row.get("row"),
            "audit_category": row.get("category"),
            "audit_finding": row.get("source_finding"),
            "approval_state": row.get("approval"),
        },
    })

# Group by step for the per-step rollup the wrapper also writes.
by_step: dict[int, list[dict]] = {}
for d in deliverables:
    by_step.setdefault(d["sprint_step"], []).append(d)

# Look up the client's project. The importer keys off project.id, so populate it
# whenever we can — first from --project-id (explicit), then by discovering the
# client's most-recently-updated active/planning project. Falls back to a generic
# name when no project exists yet (importer will create one).
project_name = "Local SEO Sprint 3"
resolved_project_id = args.project_id
try:
    projects_path = Path(args.workspace_root) / "data" / "projects.json"
    if projects_path.exists():
        projects = json.loads(projects_path.read_text())
        match = None
        if args.project_id:
            match = next((p for p in projects if p.get("id") == args.project_id), None)
        if not match:
            # Pick the client's most-recently-updated active or planning project.
            candidates = [
                p for p in projects
                if p.get("client_id") == args.client_id
                and p.get("status") in ("active", "planning", None)
            ]
            candidates.sort(key=lambda p: p.get("updated_at") or "", reverse=True)
            match = candidates[0] if candidates else None
        if match:
            project_name = match.get("name") or project_name
            resolved_project_id = match.get("id") or resolved_project_id
except (json.JSONDecodeError, OSError):
    pass

# Tag every deliverable with sprint_number so project_plan_import can route them.
import_deliverables = [
    {**d, "sprint_number": 3}
    for d in deliverables
]

# `plan` is the canonical project_plan_import input shape:
#   { project, sprints[], deliverables[] }
# Wrap it in the audit-context envelope so callers can also see scope/totals.
plan = {
    "project": {
        "id": resolved_project_id,
        "client_id": args.client_id,
        "name": project_name,
    },
    "sprints": [
        {
            "sprint_number": 3,
            "name": "Sprint 3 — Local SEO",
            "sprint_type": "foundational",
        }
    ],
    "deliverables": import_deliverables,
}

patch = {
    "client_id": args.client_id,
    "project_id": args.project_id,
    "audit_id": args.audit_id,
    "scope": "sprint_3_local_seo",
    "replace_existing": True,
    "sprint_number": 3,
    "sprint_type": "foundational",
    "name": "Sprint 3 — Local SEO",
    # Drop this `plan` straight into project_plan_import as the `plan` arg.
    "plan": plan,
    "deliverables": deliverables,
    "deliverables_by_step": {
        str(step): rows for step, rows in sorted(by_step.items())
    },
    "totals": {
        "deliverables": len(deliverables),
        "by_priority": {
            p: sum(1 for d in deliverables if d["priority"] == p)
            for p in ("P1", "P2", "P3")
        },
    },
}

out_path = Path(args.output) if args.output else (AUDIT_DIR / f"{SLUG}-local-sprint3-patch.json")
out_path.write_text(json.dumps(patch, indent=2))
print(f"Wrote {out_path}")
print(f"  {len(deliverables)} deliverables across {len(by_step)} Sprint 3 steps")
print(f"  Import: project_plan_import with `plan` = patch['plan'], replace_existing=true")
