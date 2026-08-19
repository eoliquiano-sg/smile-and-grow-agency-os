#!/usr/bin/env python3
"""build_paid_media_plan — generate a project-plan.json for a paid-media service.

Supports three service types:
  - ppc        Google Ads (search + shopping)
  - lsa        Google Local Service Ads
  - social_ads Meta / Facebook / Instagram

Output mirrors the SEO project-plan.json shape so the dashboard can render
either flavor side-by-side. Each plan has 6 sprints (Kickoff, Build, Launch,
Optimize, Scale, Reporting) and per-month monthly reports.

Plan files land in:
  clients/{slug}/paid-media/{service_type}-project-plan.json

Usage:
  python3 build_paid_media_plan.py \\
    --client-slug webris-client \\
    --service-type social_ads \\
    --start-date 2026-06-07 \\
    --engagement-months 12 \\
    --workspace-root .
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import uuid
import datetime as _dt
from collections import defaultdict
from datetime import date, timedelta
from calendar import monthrange


# ---------------------------------------------------------------------------
# Service-type plan templates
# ---------------------------------------------------------------------------
#
# Each template is a dict:
#   {
#     "service_label": "...",          # human-readable
#     "sprints": [{number, label, sprint_type, lead_skill, notes}, ...],
#     "kickoff_deliverables": [        # Sprint 1 — onboarding tasks
#       {name, description, days, skill, priority, auto_tracked?, artifact?}
#     ],
#     "monthly_deliverables": [        # Sprint 2-5 — recurring per month
#       {name, description, sprint, kind: "quick|heavy|monthly", days_or_full_month, skill, priority,
#        starts_month, ends_month, frequency: "once|monthly|per_quarter"}
#     ],
#     "monthly_report_template": {     # Sprint 6 — monthly client report
#       name, description, skill
#     }
#   }

PPC_TEMPLATE = {
    "service_label": "PPC (Google Ads)",
    "sprints": [
        {"n": 1, "label": "Kickoff", "type": "onboarding", "lead_skill": "ppc",      "notes": "Account access, audit, campaign strategy, tracking validation."},
        {"n": 2, "label": "Build",   "type": "foundational", "lead_skill": "ppc",   "notes": "Campaign structure, keyword research, ad copy v1, landing page review."},
        {"n": 3, "label": "Launch",  "type": "foundational", "lead_skill": "ppc",   "notes": "Launch campaigns, initial bidding, verify conversion tracking is firing."},
        {"n": 4, "label": "Optimize","type": "ongoing",      "lead_skill": "ppc",   "notes": "Weekly bid adjustments, search term reviews, negative keyword additions."},
        {"n": 5, "label": "Scale",   "type": "ongoing",      "lead_skill": "ppc",   "notes": "Scale winners, test new campaigns, expand audience targeting."},
        {"n": 6, "label": "Reporting","type": "reporting",   "lead_skill": "ppc",   "notes": "Monthly client report — spend, leads, CPA, ROAS, top campaigns."},
    ],
    "kickoff_deliverables": [
        {"name": "Account access + permissions",
         "description": "Get MCC access to client's Google Ads account. Confirm billing setup. Document access scope + roles. Set up conversion API or import GA4 conversions if needed.",
         "days": 5, "skill": "ppc", "priority": "P1"},
        {"name": "PPC Account Audit",
         "description": "Audit the current account state:\n  · Existing campaigns + structure\n  · Historical performance (spend, CPC, conversion rate, CPA)\n  · Quality scores\n  · Negative keyword lists\n  · Conversion tracking — what's tracked, is it firing, attribution model\n  · Account budget pacing\nOutput: audit deck + recommendations doc.",
         "days": 7, "skill": "ppc", "priority": "P1",
         "auto_tracked": True, "artifact": "ppc-audit.html"},
        {"name": "Campaign Strategy + Plan",
         "description": "Lock in the campaign strategy:\n  · Target keywords + match types\n  · Campaign structure (by service / location / intent)\n  · Bidding strategy (manual / tCPA / tROAS / max conversions)\n  · Budget allocation across campaigns\n  · Audience strategy (in-market, custom intent, remarketing)\n  · KPIs + targets (CPA, ROAS, CPC ceiling)\nOutput: PPC strategy doc.",
         "days": 7, "skill": "strategy", "priority": "P1",
         "auto_tracked": True, "artifact": "ppc-strategy.html"},
        {"name": "Conversion Tracking Validation",
         "description": "Confirm conversion tracking is bulletproof before any spend:\n  · GA4 conversion events firing correctly\n  · Imported as conversions in Google Ads\n  · Server-side / CAPI if needed for resilience\n  · Phone calls tracked via Google forwarding numbers or call-tracking integration\n  · Form submissions tracked\n  · Cross-domain tracking if applicable",
         "days": 5, "skill": "analytics", "priority": "P1"},
    ],
    "monthly_deliverables": [
        # Build sprint — Month 1
        {"name": "Keyword research + structure",
         "description": "Build the full keyword list:\n  · Seed keywords from client brief\n  · Expand via Keyword Planner + competitor analysis\n  · Cluster by intent + match type\n  · Build negative keyword baseline\n  · Map to ad groups / campaigns",
         "sprint": 2, "kind": "quick", "skill": "ppc", "priority": "P1",
         "starts_month": 1, "frequency": "once"},
        {"name": "Ad copy v1 + assets",
         "description": "Write initial ad copy + RSAs:\n  · 3-5 headlines per ad group\n  · 4 descriptions\n  · Sitelink extensions + callouts\n  · Image assets / promotion extensions\n  · Coordinate with client for brand-approved copy",
         "sprint": 2, "kind": "quick", "skill": "copywriting", "priority": "P1",
         "starts_month": 1, "frequency": "once"},
        {"name": "Landing page review + optimization brief",
         "description": "Review target landing pages for conversion potential:\n  · Page speed\n  · Above-the-fold offer clarity\n  · Form length / friction\n  · Trust signals\n  · Mobile UX\n  · Recommend changes or new LPs.",
         "sprint": 2, "kind": "quick", "skill": "strategy", "priority": "P2",
         "starts_month": 1, "frequency": "once"},
        # Launch sprint — Month 2
        {"name": "Campaign launch + initial bid tuning",
         "description": "Launch campaigns, monitor closely:\n  · Verify ads serve correctly\n  · Adjust bids based on first-week impression share + CPC\n  · Watch for unexpectedly high spend / low quality scores\n  · Daily check-ins first week",
         "sprint": 3, "kind": "heavy", "skill": "ppc", "priority": "P1",
         "starts_month": 2, "frequency": "once"},
        # Optimize sprint — recurring monthly
        {"name": "Search term review + negative keywords",
         "description": "Weekly: pull search terms report, identify waste, add negatives. Monthly: roll-up review of what's converting vs what's bleeding.",
         "sprint": 4, "kind": "heavy", "skill": "ppc", "priority": "P2",
         "starts_month": 3, "ends_month": None, "frequency": "monthly"},
        {"name": "Bid + budget adjustments",
         "description": "Adjust bids by campaign / ad group / keyword. Reallocate budget toward winners. Manage daily caps.",
         "sprint": 4, "kind": "heavy", "skill": "ppc", "priority": "P2",
         "starts_month": 3, "ends_month": None, "frequency": "monthly"},
        # Scale sprint — quarterly tests
        {"name": "Test new ad creative / campaigns",
         "description": "Each quarter: test new ad creative variations. Add new campaigns (e.g., display, performance max, branded). Refresh declining creative.",
         "sprint": 5, "kind": "heavy", "skill": "ppc", "priority": "P3",
         "starts_month": 4, "ends_month": None, "frequency": "per_quarter"},
    ],
    "monthly_report_template": {
        "name": "Monthly PPC Report — Month {m}",
        "description": "Send the client a Month {m} PPC report:\n  · Spend + budget pacing\n  · Conversions + cost per conversion (CPA)\n  · ROAS / revenue (if available)\n  · Top campaigns + biggest movers\n  · Search term + negative-keyword additions\n  · Bid/budget changes this month\n  · Next-month focus areas\nTemplate: standard WEBRIS PPC report layout.",
        "skill": "ppc",
    },
}

LSA_TEMPLATE = {
    "service_label": "LSA (Local Service Ads)",
    "sprints": [
        {"n": 1, "label": "Kickoff",   "type": "onboarding",   "lead_skill": "lsa", "notes": "Profile setup, verification (background checks, license), Google Guarantee badge."},
        {"n": 2, "label": "Bidding",   "type": "foundational", "lead_skill": "lsa", "notes": "Initial bidding strategy + budget setup."},
        {"n": 3, "label": "Disputes",  "type": "ongoing",      "lead_skill": "lsa", "notes": "Establish lead dispute cadence — review every lead, dispute the bad ones."},
        {"n": 4, "label": "Optimize",  "type": "ongoing",      "lead_skill": "lsa", "notes": "Refine bids, services, hours, geographic targeting."},
        {"n": 5, "label": "Expand",    "type": "ongoing",      "lead_skill": "lsa", "notes": "Add services, expand geo, increase budget for high-ROI areas."},
        {"n": 6, "label": "Reporting", "type": "reporting",    "lead_skill": "lsa", "notes": "Monthly client report — leads, cost-per-lead, qualified rate."},
    ],
    "kickoff_deliverables": [
        {"name": "LSA Profile Setup",
         "description": "Set up the Google Local Service Ads profile:\n  · Business info (NAP, services, service area)\n  · Hours of operation\n  · Photos + bio\n  · Insurance + license docs uploaded\n  · Connect to client's payments / billing",
         "days": 5, "skill": "lsa", "priority": "P1"},
        {"name": "Verification + Background Checks",
         "description": "Complete the LSA verification process:\n  · Business verification (registration docs)\n  · Owner background checks (in-person or eligible third-party)\n  · License verification per state requirements\n  · Insurance verification — minimum required coverage levels\n  · Google Guarantee badge approval\nTypically takes 2-4 weeks end-to-end — start ASAP.",
         "days": 14, "skill": "lsa", "priority": "P1",
         "auto_tracked": True, "artifact": "lsa-verification-complete.txt"},
        {"name": "LSA Strategy + Budget Plan",
         "description": "Lock in the LSA strategy:\n  · Service categories to advertise\n  · Service area boundaries\n  · Monthly budget + daily caps\n  · Bidding strategy (max per lead or max budget mode)\n  · Lead qualification criteria — what counts as a 'good' lead for dispute purposes\nOutput: LSA strategy doc.",
         "days": 5, "skill": "strategy", "priority": "P1",
         "auto_tracked": True, "artifact": "lsa-strategy.html"},
    ],
    "monthly_deliverables": [
        {"name": "Initial bidding + budget setup",
         "description": "Configure initial bids:\n  · Cost-per-lead bid by service\n  · Daily budget caps\n  · Schedule (which hours bids are higher)\n  · Auto-bid vs manual decision",
         "sprint": 2, "kind": "quick", "skill": "lsa", "priority": "P1",
         "starts_month": 2, "frequency": "once"},
        {"name": "Lead dispute review (weekly)",
         "description": "Every week: review all incoming LSA leads, identify the bad ones (spam, wrong service, out of area, no answer to phone). Submit disputes within Google's window. Track approval rate.\nMonthly roll-up tracks dispute approval %.",
         "sprint": 3, "kind": "heavy", "skill": "lsa", "priority": "P1",
         "starts_month": 2, "ends_month": None, "frequency": "monthly"},
        {"name": "Profile optimization (hours, services, photos)",
         "description": "Monthly: review LSA profile health. Update hours seasonally. Add new services as offered. Refresh photos. Respond to reviews.",
         "sprint": 4, "kind": "quick", "skill": "lsa", "priority": "P2",
         "starts_month": 3, "ends_month": None, "frequency": "monthly"},
        {"name": "Bid + service area adjustments",
         "description": "Monthly: adjust per-service bids based on lead quality + cost-per-lead. Refine service area boundaries — pull back from low-ROI zips, push into high-ROI ones.",
         "sprint": 4, "kind": "quick", "skill": "lsa", "priority": "P2",
         "starts_month": 3, "ends_month": None, "frequency": "monthly"},
        {"name": "Service / geo expansion review",
         "description": "Quarterly: evaluate adding new services or expanding to adjacent service areas. Coordinate with client capacity to handle additional lead flow.",
         "sprint": 5, "kind": "quick", "skill": "strategy", "priority": "P3",
         "starts_month": 5, "ends_month": None, "frequency": "per_quarter"},
    ],
    "monthly_report_template": {
        "name": "Monthly LSA Report — Month {m}",
        "description": "Send the client a Month {m} LSA report:\n  · Leads received + cost-per-lead\n  · Lead quality breakdown (qualified vs bad)\n  · Disputes submitted + approved\n  · Top services by lead volume\n  · Budget pacing\n  · Profile health metrics\n  · Next-month focus.",
        "skill": "lsa",
    },
}

SOCIAL_ADS_TEMPLATE = {
    "service_label": "Social Ads (Meta)",
    "sprints": [
        {"n": 1, "label": "Kickoff",    "type": "onboarding",   "lead_skill": "social_ads", "notes": "Account audit, creative strategy, pixel + CAPI setup, audience research."},
        {"n": 2, "label": "Build",      "type": "foundational", "lead_skill": "social_ads", "notes": "Audience strategy, creative production (5-10 variants), landing page review."},
        {"n": 3, "label": "Launch",     "type": "foundational", "lead_skill": "social_ads", "notes": "Campaign launch, initial bidding, conversion tracking validation."},
        {"n": 4, "label": "Test",       "type": "ongoing",      "lead_skill": "social_ads", "notes": "A/B test creative, audiences, placements. Find winners."},
        {"n": 5, "label": "Scale",      "type": "ongoing",      "lead_skill": "social_ads", "notes": "Scale winning ad sets, expand to lookalikes, refresh creative monthly."},
        {"n": 6, "label": "Reporting",  "type": "reporting",    "lead_skill": "social_ads", "notes": "Monthly client report — spend, conversions, ROAS, top creative."},
    ],
    "kickoff_deliverables": [
        {"name": "Meta Account Access + Audit",
         "description": "Get Business Manager access to the client's ad account. Audit:\n  · Historical campaign performance\n  · Pixel + Conversions API health\n  · Existing audiences\n  · Creative library\n  · Ad account restrictions / policy issues\n  · Billing setup",
         "days": 5, "skill": "social_ads", "priority": "P1",
         "auto_tracked": True, "artifact": "social-ads-audit.html"},
        {"name": "Creative Strategy",
         "description": "Lock in the creative strategy:\n  · Brand visual guidelines / asset library\n  · Hook / value-prop angles to test\n  · Format mix (video / static / carousel / Reels)\n  · Voiceover / talent / UGC requirements\n  · Production cadence (5-10 new creatives per month default)\nOutput: creative strategy doc.",
         "days": 7, "skill": "strategy", "priority": "P1",
         "auto_tracked": True, "artifact": "social-ads-strategy.html"},
        {"name": "Pixel + CAPI Setup",
         "description": "Verify Meta pixel + Conversions API are firing reliably:\n  · Pixel events match GA4 events\n  · CAPI server-side events for iOS resilience\n  · Custom conversions defined for primary KPIs\n  · Match quality score above 7.0\n  · Domain verified",
         "days": 5, "skill": "analytics", "priority": "P1"},
        {"name": "Audience Strategy",
         "description": "Lock in audiences to launch:\n  · Custom audiences (website visitors, email list, video viewers)\n  · Lookalikes (1%, 3%, 5%)\n  · Interest + behavioral targeting\n  · Geographic + demographic targeting\n  · Exclusions to apply",
         "days": 5, "skill": "social_ads", "priority": "P1"},
    ],
    "monthly_deliverables": [
        {"name": "Creative production batch (5-10 ads)",
         "description": "Produce a fresh batch of ad creative each month:\n  · Mix of video, static, carousel\n  · Test new hooks + angles\n  · Update offers + promos\n  · Refresh declining creative\nDefault batch size: 5-10 ads/month.",
         "sprint": 2, "kind": "heavy", "skill": "creative", "priority": "P1",
         "starts_month": 1, "ends_month": None, "frequency": "monthly"},
        {"name": "Landing page review",
         "description": "Review landing pages each campaign points at:\n  · Page speed\n  · Mobile UX\n  · Above-the-fold offer clarity\n  · Form friction\n  · Trust signals\nRecommend changes; coordinate with client / web team.",
         "sprint": 2, "kind": "quick", "skill": "strategy", "priority": "P2",
         "starts_month": 1, "frequency": "once"},
        {"name": "Campaign launch + initial optimization",
         "description": "Launch campaigns, watch closely:\n  · Verify ads serve correctly\n  · Adjust budgets based on first-week CPM / CPA\n  · Daily check-ins first week\n  · Pause obvious losers, scale obvious winners",
         "sprint": 3, "kind": "heavy", "skill": "social_ads", "priority": "P1",
         "starts_month": 2, "frequency": "once"},
        {"name": "A/B testing cycle",
         "description": "Monthly: run structured A/B tests on:\n  · Creative variants (every ad set rotates through test variants)\n  · Audience segments\n  · Placements (auto vs manual)\n  · Bid strategies\nLog all test results in the experiment tracker.",
         "sprint": 4, "kind": "heavy", "skill": "social_ads", "priority": "P2",
         "starts_month": 3, "ends_month": None, "frequency": "monthly"},
        {"name": "Scale winning ad sets + audience expansion",
         "description": "Monthly: increase budget on winners, expand to lookalikes (1% → 3% → 5%), add new placements. Maintain frequency below 2.0 to avoid creative fatigue.",
         "sprint": 5, "kind": "heavy", "skill": "social_ads", "priority": "P2",
         "starts_month": 3, "ends_month": None, "frequency": "monthly"},
        {"name": "Creative refresh — Quarterly",
         "description": "Every quarter: full creative refresh. Retire fatigued creative (frequency > 2.0 or CTR dropped 30%+). Launch fresh batch tied to seasonal / promo calendar.",
         "sprint": 5, "kind": "heavy", "skill": "creative", "priority": "P2",
         "starts_month": 4, "ends_month": None, "frequency": "per_quarter"},
    ],
    "monthly_report_template": {
        "name": "Monthly Social Ads Report — Month {m}",
        "description": "Send the client a Month {m} Social Ads report:\n  · Spend + budget pacing\n  · Conversions + cost per conversion (CPA)\n  · ROAS / revenue (if e-commerce)\n  · Top ad sets + biggest movers\n  · Creative performance — winners + losers\n  · Audience insights\n  · Next-month creative + scaling plan.\nTemplate: standard WEBRIS Social Ads report layout.",
        "skill": "social_ads",
    },
}

SERVICE_TEMPLATES = {
    "ppc":        PPC_TEMPLATE,
    "lsa":        LSA_TEMPLATE,
    "social_ads": SOCIAL_ADS_TEMPLATE,
}


# Routing pools per skill — built from the agency's own team.json (generalized
# from the hardcoded WEBRIS team). Each member contributes their email to every
# skill pool their `skills` match; falls back to strategy lead / owner / any member.
POOLS = defaultdict(list)
OWNER_EMAIL = None
ALL_EMAILS = []

def _normalize_skill(s):
    return re.sub(r"[^a-z0-9]+", "_", (s or "").lower()).strip("_")

SKILL_FALLBACKS = {
    "ppc":         ["ppc", "paid_media", "google_ads", "analytics", "strategy"],
    "lsa":         ["lsa", "ppc", "paid_media", "strategy"],
    "social_ads":  ["social_ads", "paid_social", "paid_media", "strategy"],
    "creative":    ["creative", "design", "content_writing", "copywriting", "strategy"],
    "analytics":   ["analytics", "technical_seo", "strategy"],
    "copywriting": ["copywriting", "content_writing", "strategy"],
    "strategy":    ["strategy"],
}

def init_team(team_json_path):
    """Populate POOLS / OWNER_EMAIL / ALL_EMAILS from data/team.json (active members)."""
    global OWNER_EMAIL, ALL_EMAILS
    if not team_json_path or not os.path.exists(team_json_path):
        return
    try:
        raw = json.load(open(team_json_path))
    except Exception as e:
        print(f"  ⚠ Could not read team.json ({e}); proceeding unassigned", file=sys.stderr)
        return
    members = [m for m in raw if m.get("active", True) and m.get("email")]
    OWNER_EMAIL = next((m["email"] for m in members if m.get("role") == "owner"), None)
    ALL_EMAILS = [m["email"] for m in members]
    for m in members:
        for sk in (m.get("skills") or []):
            POOLS[_normalize_skill(sk)].append(m["email"])

def pool_for(skill):
    for k in SKILL_FALLBACKS.get(skill, [skill, "strategy"]):
        if POOLS.get(k):
            return POOLS[k]
    if OWNER_EMAIL:
        return [OWNER_EMAIL]
    return ALL_EMAILS or [None]

_rr = {}
def assign_for(skill):
    pool = pool_for(skill)
    idx = _rr.get(skill, 0) % len(pool)
    _rr[skill] = _rr.get(skill, 0) + 1
    return pool[idx]


# ---------------------------------------------------------------------------
# Date helpers (same conventions as build_project_plan.py)
# ---------------------------------------------------------------------------

def month_end(start_date, month_n):
    target = start_date.replace(day=1)
    for _ in range(month_n - 1):
        target = (target.replace(year=target.year + 1, month=1)
                  if target.month == 12 else target.replace(month=target.month + 1))
    last = monthrange(target.year, target.month)[1]
    return target.replace(day=last)


def month_start(start_date, month_n):
    if month_n <= 1:
        return start_date
    return month_end(start_date, month_n - 1) + timedelta(days=1)


def compute_dates(start_date, month_n, *, kind, days=None):
    ms = month_start(start_date, month_n)
    me = month_end(start_date, month_n)
    if kind == "heavy":
        return ms, me
    if kind == "report":
        s = me - timedelta(days=6)
        return (s if s >= ms else ms), me
    # quick — `days` controls the duration; defaults to 7
    d = days or 7
    due = ms + timedelta(days=d)
    return ms, (due if due <= me else me)


# ---------------------------------------------------------------------------
# Plan builder
# ---------------------------------------------------------------------------

def build_plan(client_slug, service_type, start_date, engagement_months, client_id=None):
    template = SERVICE_TEMPLATES.get(service_type)
    if not template:
        sys.exit(f"ERROR: unknown service type {service_type!r}. Options: {list(SERVICE_TEMPLATES.keys())}")

    end_date = month_end(start_date, engagement_months)
    run_ts = _dt.datetime.now(_dt.timezone.utc).isoformat(timespec="seconds")

    # Sprint shells
    sprints = []
    for s in template["sprints"]:
        if s["n"] == 1:
            ss, se = start_date, start_date + timedelta(days=20)
        elif s["n"] == 6:
            ss, se = start_date, end_date
        else:
            ss = month_start(start_date, max(1, s["n"] - 1))
            se = end_date
        sprints.append({
            "sprint_number": s["n"],
            "sprint_type": s["type"],
            "name": f"Sprint {s['n']} ({s['label']})",
            "scheduled_start": ss.isoformat(),
            "scheduled_end": se.isoformat(),
            "status": "active" if s["n"] == 1 else "pending",
            "lead_email": assign_for(s["lead_skill"]),
            "notes": s["notes"],
        })

    deliverables = []

    # --- Sprint 1: kickoff ---
    cursor = start_date
    for kd in template["kickoff_deliverables"]:
        sd = cursor
        dd = sd + timedelta(days=kd["days"])
        d = {
            "id": str(uuid.uuid4()),
            "sprint_number": 1,
            "name": kd["name"],
            "description": kd["description"],
            "deliverable_type": "Kickoff",
            "priority": kd["priority"],
            "assigned_to_email": assign_for(kd["skill"]),
            "start_date": sd.isoformat(),
            "due_date":   dd.isoformat(),
            "scheduled_month": 1,
            "ai_assisted": False,
            "status": "pending",
            "source": {"category": "Kickoff", "action_type": kd["name"]},
        }
        if kd.get("auto_tracked"):
            d["auto_tracked"] = True
            d["auto_complete_artifact"] = kd["artifact"]
        deliverables.append(d)
        cursor = dd + timedelta(days=1)

    # --- Sprints 2-5: build / launch / optimize / scale ---
    for md in template["monthly_deliverables"]:
        starts_m = md.get("starts_month", 1)
        ends_m = md.get("ends_month") or engagement_months
        freq = md.get("frequency", "once")
        if freq == "once":
            months = [starts_m]
        elif freq == "per_quarter":
            months = list(range(starts_m, ends_m + 1, 3))
        else:  # monthly
            months = list(range(starts_m, ends_m + 1))

        for m in months:
            sd, dd = compute_dates(start_date, m, kind=md["kind"])
            label_suffix = f" — Month {m}" if freq != "once" else ""
            deliverables.append({
                "id": str(uuid.uuid4()),
                "sprint_number": md["sprint"],
                "name": md["name"] + label_suffix,
                "description": md["description"],
                "deliverable_type": "Paid Media",
                "priority": md["priority"],
                "assigned_to_email": assign_for(md["skill"]),
                "start_date": sd.isoformat(),
                "due_date":   dd.isoformat(),
                "scheduled_month": m,
                "ai_assisted": False,
                "is_heavy_batch": md["kind"] == "heavy",
                "source": {
                    "category": "Paid Media",
                    "action_type": md["name"],
                    "frequency": freq,
                    "service_type": service_type,
                },
            })

    # --- Sprint 6: monthly reports ---
    rpt = template["monthly_report_template"]
    for m in range(1, engagement_months + 1):
        sd, dd = compute_dates(start_date, m, kind="report")
        deliverables.append({
            "id": str(uuid.uuid4()),
            "sprint_number": 6,
            "name": rpt["name"].format(m=m),
            "description": rpt["description"].format(m=m),
            "deliverable_type": "Monthly Report",
            "priority": "P1",
            "assigned_to_email": assign_for(rpt["skill"]),
            "start_date": sd.isoformat(),
            "due_date":   dd.isoformat(),
            "scheduled_month": m,
            "ai_assisted": True,
            "is_monthly_report": True,
            "source": {"category": "Reporting", "action_type": "Monthly Report", "month": m, "service_type": service_type},
        })

    project = {
        "client_id": client_id,
        "name": f"{template['service_label']} — {start_date.strftime('%B %Y')}",
        "project_type": service_type,
        "service_type": service_type,
        "primary_goal": f"{template['service_label']} engagement: kickoff (M1), build + launch (M1-M2), ongoing optimization + scale (M3+), monthly reporting throughout.",
        "start_date": start_date.isoformat(),
        "target_end_date": end_date.isoformat(),
    }

    plan = {
        "client_slug": client_slug,
        "service_type": service_type,
        "project": project,
        "sprints": sprints,
        "deliverables": deliverables,
        "generated_at": run_ts,
        "summary": {
            "total_deliverables": len(deliverables),
            "by_sprint": {f"Sprint {n}": sum(1 for d in deliverables if d["sprint_number"] == n) for n in (1, 2, 3, 4, 5, 6)},
            "by_assignee": {},
        },
    }
    for d in deliverables:
        email = d.get("assigned_to_email")
        if email:
            plan["summary"]["by_assignee"][email] = plan["summary"]["by_assignee"].get(email, 0) + 1
    return plan


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--workspace-root", default=".")
    p.add_argument("--client-slug", required=True)
    p.add_argument("--service-type", required=True, choices=list(SERVICE_TEMPLATES.keys()))
    p.add_argument("--start-date", required=True, help="YYYY-MM-DD")
    p.add_argument("--engagement-months", type=int, default=12)
    p.add_argument("--client-id")
    p.add_argument("--team-json", help="Path to data/team.json for assignment routing (optional)")
    p.add_argument("--output")
    args = p.parse_args()

    init_team(args.team_json)
    start_date = date.fromisoformat(args.start_date)
    plan = build_plan(args.client_slug, args.service_type, start_date,
                       args.engagement_months, client_id=args.client_id)

    output = args.output or os.path.join(
        args.workspace_root, "clients", args.client_slug, "paid-media",
        f"{args.service_type}-project-plan.json"
    )
    os.makedirs(os.path.dirname(output), exist_ok=True)
    with open(output, "w") as f:
        json.dump(plan, f, indent=2)

    print(f"\nProject plan written to: {output}")
    print(f"\nSummary:")
    print(f"  Service:            {SERVICE_TEMPLATES[args.service_type]['service_label']}")
    print(f"  Engagement:         {start_date} → {plan['project']['target_end_date']}")
    print(f"  Total deliverables: {plan['summary']['total_deliverables']}")
    print(f"\n  By sprint:")
    for k, v in plan["summary"]["by_sprint"].items():
        print(f"    {k}: {v}")
    print(f"\n  By assignee:")
    for email, n in sorted(plan["summary"]["by_assignee"].items(), key=lambda x: -x[1]):
        print(f"    {email}: {n}")


if __name__ == "__main__":
    main()
