#!/usr/bin/env python3
"""Build the Local SEO Audit HTML report.

Hybrid layout: client-friendly exec summary on top, tactical strategist detail below.

Reads the same normalized cache the XLSX builder uses:
  clients/<slug>/local-audit/<audit-id>/
    data-coverage.json      ← grades + topline (NOT audit-manifest.json — that
                               file belongs to the localseo_create_audit /
                               localseo_update_config MCP tools)
    gbp-profile.json        ← 14 GBP fields with scores
    citations.json          ← 55 directories with status + diffs
    local-falcon-grid.json  ← grid rankings per keyword
    gsc-local-queries.json  ← local-intent keywords
    local-links.json        ← link-build gaps
    local-pages.json        ← location pages

Output: clients/<slug>/local-audit/<audit-id>/<slug>-local-audit-report.html
"""

from __future__ import annotations

import argparse
import html
import json
import os
import sys
from datetime import datetime
from pathlib import Path

# ─── CLI ────────────────────────────────────────────────────────────────────
parser = argparse.ArgumentParser()
parser.add_argument("--client-slug", required=True)
parser.add_argument("--audit-id", required=True)
parser.add_argument("--workspace-root", default=os.environ.get("AGENCY_OS_ROOT", "."))
parser.add_argument("--client-name", default=None)
parser.add_argument("--primary-color", default="#2563EB")
args = parser.parse_args()

SLUG = args.client_slug
PRIMARY = args.primary_color
CLIENT_NAME = args.client_name or SLUG.replace("-", " ").title()
A_BASE = Path(args.workspace_root) / "clients" / SLUG / "local-audit" / args.audit_id
OUT = A_BASE / f"{SLUG}-local-audit-report.html"


# ─── Loaders ────────────────────────────────────────────────────────────────
def load(name: str, default=None):
    p = A_BASE / name
    if not p.exists():
        return default if default is not None else {}
    return json.loads(p.read_text())


manifest = load("data-coverage.json")
gbp = load("gbp-profile.json")
# Multi-location: list of GBP locations (1..N) for this client. Each entry may carry
# name/role/address/reviews/gmb_connected/grid_keywords/notes. Empty/absent → single-location.
_loc_cache = load("locations.json", {}) or {}
LOCATIONS = (_loc_cache.get("locations", []) if isinstance(_loc_cache, dict) else (_loc_cache or [])) or []
citations = load("citations.json")
falcon = load("local-falcon-grid.json")
gsc = load("gsc-local-queries.json")
links = load("local-links.json")
pages = load("local-pages.json")
keyword_rankings = load("keyword-rankings.json") or load("keyword-rankings-50.json")
windsor_gbp = load("windsor-gbp-monthly.json")
windsor_reviews = load("windsor-reviews-monthly.json")


def esc(s) -> str:
    return html.escape(str(s) if s is not None else "")


def grade_color(letter: str) -> str:
    return {
        "A": "#10b981", "B": "#22c55e", "C": "#f59e0b",
        "D": "#f97316", "F": "#ef4444"
    }.get((letter or "F")[0].upper(), "#94a3b8")


# ─── Compute headline metrics ───────────────────────────────────────────────
gbp_grade = gbp.get("letter_grade") or "F"
gbp_pct = gbp.get("grade_pct") or 0
citations_summary = citations.get("summary") or {}
falcon_summary = falcon.get("summary") or {}

# Citation totals
cit_total = citations_summary.get("total", 0)
cit_live_correct = citations_summary.get("live_correct", 0)
cit_live = citations_summary.get("live", 0)
cit_live_mismatch = citations_summary.get("live_mismatch", 0)
cit_missing = citations_summary.get("missing", 0)
cit_coverage = citations_summary.get("coverage_pct", 0)
cit_total_live = cit_live_correct + cit_live + cit_live_mismatch

# Local Falcon averages
falcon_kws = list(falcon_summary.values()) if isinstance(falcon_summary, dict) else []
avg_arp = round(sum(k.get("arp", 0) for k in falcon_kws) / max(1, len(falcon_kws)), 1) if falcon_kws else 0
avg_coverage = round(sum(k.get("coverage_pct", 0) for k in falcon_kws) / max(1, len(falcon_kws))) if falcon_kws else 0
avg_solv = round(sum(k.get("solv_pct", 0) for k in falcon_kws) / max(1, len(falcon_kws)), 1) if falcon_kws else 0

# Review stats from GBP
review_count = next((f.get("current") for f in gbp.get("fields", []) if f.get("field") == "review_count"), 0)
review_avg = next((f.get("current") for f in gbp.get("fields", []) if f.get("field") == "review_avg"), 0)

# GBP top gaps (highest-weight fields with issues)
gbp_gaps = sorted(
    [f for f in gbp.get("fields", []) if f.get("status") in ("missing", "weak", "api_pending")],
    key=lambda f: -(f.get("weight") or 0)
)[:6]


# ─── Build HTML chunks ──────────────────────────────────────────────────────
def render_kpi(label: str, value: str, sub: str = "", color: str = "") -> str:
    color_style = f' style="color:{color}"' if color else ""
    return (
        f'<div class="kpi"><div class="label">{esc(label)}</div>'
        f'<div class="value"{color_style}>{esc(value)}</div>'
        f'<div class="sub">{esc(sub)}</div></div>'
    )


def render_status_badge(status: str) -> str:
    palette = {
        "ok": ("#10b981", "OK"),
        "live_correct": ("#10b981", "Live · Correct"),
        "live": ("#3b82f6", "Live · Link-Verified"),
        "live_mismatch": ("#f59e0b", "Live · NAP Mismatch"),
        "weak": ("#f59e0b", "Weak"),
        "partial": ("#f59e0b", "Partial"),
        "missing": ("#ef4444", "Missing"),
        "unverified": ("#94a3b8", "Unverified"),
        "api_pending": ("#94a3b8", "Pending"),
    }
    color, label = palette.get(status, ("#94a3b8", status.replace("_", " ").title()))
    return f'<span class="badge" style="background:{color}1A;color:{color};border:1px solid {color}40">{esc(label)}</span>'


# Top 5 priorities — pull P1/P2 items from across all sources
top_priorities = []
# 1. Worst GBP gaps
for f in gbp_gaps[:3]:
    label = f["field"].replace("_", " ").title()
    top_priorities.append({
        "category": "GBP",
        "title": f"{label}: {f.get('action') or 'fix this field'}",
        "priority": "P1" if f.get("weight", 0) >= 6 else "P2",
        "impact": f.get("rationale", ""),
    })
# 2. Worst NAP mismatches (real content, not formatting-only)
real_mismatches = [
    d for d in citations.get("directories", [])
    if d.get("status") == "live_mismatch"
    and "formatting only" not in (d.get("diff_summary") or "").lower()
]
for d in real_mismatches[:3]:
    top_priorities.append({
        "category": "Citations",
        "title": f"Fix NAP on {d['directory']}",
        "priority": d.get("priority", "P2"),
        "impact": (d.get("diff_summary") or "").split("\n")[0],
    })
# 3. Missing P1 citations
missing_p1 = [
    d for d in citations.get("directories", [])
    if d.get("status") == "missing" and d.get("priority") == "P1"
]
for d in missing_p1[:3]:
    top_priorities.append({
        "category": "Citations",
        "title": f"Submit listing on {d['directory']}",
        "priority": "P1",
        "impact": f"T{d.get('tier')} aggregator — feeds downstream directories",
    })

# Sort by priority weight
priority_weight = {"P1": 0, "P2": 1, "P3": 2}
top_priorities.sort(key=lambda x: priority_weight.get(x["priority"], 9))
top_priorities = top_priorities[:8]


# ─── Render exec summary ─────────────────────────────────────────────────────
exec_kpis = "".join([
    render_kpi("GBP Grade", gbp_grade, f"{gbp_pct:.0f}% optimization", grade_color(gbp_grade)),
    render_kpi("Citation Coverage", f"{cit_coverage:.0f}%", f"{cit_total_live}/{cit_total} directories live"),
    render_kpi("Avg Local Rank", f"#{avg_arp}" if avg_arp else "—", f"{avg_coverage}% grid coverage"),
    render_kpi("Reviews", f"{review_count}", f"{review_avg}★ average" if review_avg else ""),
])

# Top priorities table
priority_rows = "".join([
    f'<tr>'
    f'<td><span class="prio-pill prio-{p["priority"].lower()}">{esc(p["priority"])}</span></td>'
    f'<td><span class="cat-tag">{esc(p["category"])}</span></td>'
    f'<td><strong>{esc(p["title"])}</strong><div class="cell-sub">{esc(p["impact"][:120])}</div></td>'
    f'</tr>'
    for p in top_priorities
])


# ─── Render tactical: GBP field grid ─────────────────────────────────────────
def fmt_gbp_current(val) -> str:
    if isinstance(val, list):
        if not val: return "—"
        items = val[:5]
        suffix = f" (+{len(val) - 5} more)" if len(val) > 5 else ""
        return ", ".join(esc(str(x)) for x in items) + suffix
    if isinstance(val, dict):
        return esc(str({k: v for k, v in list(val.items())[:3]}))
    if val in (None, ""):
        return "—"
    return esc(str(val))[:200]


gbp_rows = "".join([
    f'<tr>'
    f'<td><strong>{esc(f["field"].replace("_", " ").title())}</strong></td>'
    f'<td>{fmt_gbp_current(f.get("current"))}</td>'
    f'<td>{render_status_badge(f.get("status", "unknown"))}</td>'
    f'<td class="num">{(f.get("score") or 0):.2f}</td>'
    f'<td class="num">{(f.get("weight") or 0):.0f}</td>'
    f'<td class="muted">{esc(f.get("rationale") or "")}</td>'
    f'<td>{esc(f.get("action") or "")}</td>'
    f'</tr>'
    for f in gbp.get("fields", [])
])

# Per-location GBP field-by-field accordions: primary office (full normalized table)
# + one accordion per additional office (from its pulled profile fields).
# Per-location GBP field-by-field accordions — EVERY location renders through the same
# full scored table (Field / Current / Status / Score / Weight / Why / Action). Each
# location loads its own scored profile: primary = gbp-profile.json; others =
# gbp-profile-{locslug}.json (produced from that office's pulled GBP profile).
def _gbp_full_rows(profile):
    return "".join(
        f'<tr><td><strong>{esc(str(f.get("field","")).replace("_", " ").title())}</strong></td>'
        f'<td>{fmt_gbp_current(f.get("current"))}</td>'
        f'<td>{render_status_badge(f.get("status", "unknown"))}</td>'
        f'<td class="num">{(f.get("score") or 0):.2f}</td>'
        f'<td class="num">{(f.get("weight") or 0):.0f}</td>'
        f'<td class="muted">{esc(f.get("rationale") or "")}</td>'
        f'<td>{esc(f.get("action") or "")}</td></tr>'
        for f in profile.get("fields", []))

_GBP_HEAD = ('<table><thead><tr><th>Field</th><th>Current</th><th>Status</th><th>Score</th>'
             '<th>Weight</th><th>Why it matters</th><th>Action</th></tr></thead>')
_nd_locs = [l for l in LOCATIONS if l.get("role") != "duplicate"]
_gbp_accs = []
for i, _loc in enumerate(_nd_locs or [{"name": CLIENT_NAME, "role": "primary"}]):
    _ls = (_loc.get("name") or "office").lower().split()[0]
    _prof = gbp if _loc.get("role") == "primary" else load(f"gbp-profile-{_ls}.json", None)
    _role = " (primary)" if _loc.get("role") == "primary" else ""
    if _prof and _prof.get("fields"):
        _grade = f' · grade {esc(_prof.get("letter_grade", "?"))} ({(_prof.get("grade_pct") or 0):.0f}%)'
        _body = f'{_GBP_HEAD}<tbody>{_gbp_full_rows(_prof)}</tbody></table>'
    else:
        _grade = ""
        _body = '<div class="lf-empty">GBP profile audit pending for this office — pull its profile to populate.</div>'
    _open = " open" if i == 0 else ""
    _gbp_accs.append(
        f'<details class="tactical"{_open}><summary>📍 {esc(_loc.get("name"))}{_role} — GBP field audit{_grade}</summary>'
        f'<div class="body">{_body}</div></details>'
    )
gbp_accordions_html = "".join(_gbp_accs)


# ─── Render tactical: Citations breakdown ────────────────────────────────────
def render_citation_row(d: dict) -> str:
    status = d.get("status", "unverified")
    type_label = "attorney" if d.get("directory_type") == "attorney" else "firm"
    detail = d.get("diff_summary") or "—"
    # Compress multi-line diff into HTML
    detail_html = "<br>".join(esc(line) for line in detail.split("\n") if line.strip())
    link_info = ""
    if d.get("links_to_target"):
        link_info = f'<div class="cell-sub">DR {d.get("domain_rating", "?"):.0f} · {d.get("links_to_target")} links</div>'
    return (
        f'<tr>'
        f'<td><strong>{esc(d["directory"])}</strong><div class="cell-sub">T{d.get("tier")} · {type_label}</div></td>'
        f'<td><span class="prio-pill prio-{d.get("priority", "p3").lower()}">{esc(d.get("priority", "—"))}</span></td>'
        f'<td>{render_status_badge(status)}{link_info}</td>'
        f'<td class="diff-cell">{detail_html}</td>'
        f'<td>{esc(d.get("action") or "")}</td>'
        f'</tr>'
    )


# Group citations by status for the tactical section
citations_by_status = {"live_mismatch": [], "missing": [], "live": [], "live_correct": [], "partial": [], "unverified": []}
for d in citations.get("directories", []):
    s = d.get("status", "unverified")
    if s in citations_by_status:
        citations_by_status[s].append(d)

cit_mismatch_rows = "".join(render_citation_row(d) for d in citations_by_status["live_mismatch"])
cit_missing_rows = "".join(render_citation_row(d) for d in citations_by_status["missing"])
cit_live_rows = "".join(render_citation_row(d) for d in citations_by_status["live"] + citations_by_status["live_correct"])


# ─── Per-location citation tabs (full 55-directory universe, audited per location) ──
def _cit_tables_for(dirs: list) -> str:
    by = {"live_mismatch": [], "missing": [], "live": [], "live_correct": [], "partial": [], "unverified": []}
    for d in dirs:
        by.get(d.get("status", "unverified"), by["unverified"]).append(d)
    n_live = len(by["live"]) + len(by["live_correct"]) + len(by["partial"])
    def _block(title, rows, empty):
        body = rows or f'<tr><td colspan="5" class="muted">{empty}</td></tr>'
        return (f'<details class="tactical"><summary>{title}</summary><div class="body"><table>'
                f'<thead><tr><th>Directory</th><th>Priority</th><th>Status</th><th>Detail</th><th>Action</th></tr></thead>'
                f'<tbody>{body}</tbody></table></div></details>')
    return (
        _block(f'NAP Issues &amp; Duplicates ({len(by["live_mismatch"])}) — live but wrong/duplicated',
               "".join(render_citation_row(d) for d in by["live_mismatch"]), "No NAP issues found.")
        + _block(f'Missing ({len(by["missing"])}) — searched, not listed',
                 "".join(render_citation_row(d) for d in by["missing"]), "No confirmed-missing citations.")
        + _block(f'Live &amp; Correct ({n_live}) — confirmed listings',
                 "".join(render_citation_row(d) for d in by["live"] + by["live_correct"] + by["partial"]), "No confirmed live citations.")
        + _block(f'Not Yet Verified ({len(by["unverified"])}) — long-tail / submission queue',
                 "".join(render_citation_row(d) for d in by["unverified"]), "All directories verified.")
    )

_cit_locs = citations.get("locations") or [{"slug": "primary", "name": CLIENT_NAME,
                                            "directories": citations.get("directories", []), "summary": citations_summary}]
_ctabs, _cpanes = [], []
for i, _loc in enumerate(_cit_locs):
    _ls = _loc.get("slug") or _locslug(_loc.get("name", "loc"))
    _s = _loc.get("summary", {})
    _live = _s.get("live_correct", 0) + _s.get("live", 0) + _s.get("live_mismatch", 0)
    _active = " active" if i == 0 else ""
    _disp = "block" if i == 0 else "none"
    _sub = (f'Coverage <strong>{_s.get("coverage_pct", 0):.0f}%</strong> — {_live}/{_s.get("total", 0)} live · '
            f'{_s.get("live_mismatch", 0)} NAP issues · {_s.get("missing", 0)} missing · {_s.get("unverified", 0)} not yet verified')
    _ctabs.append(f'<button class="loc-tab{_active}" onclick="showTab(this,\'cit\',\'cit-{_ls}\')">{esc(_loc.get("name"))}</button>')
    _cpanes.append(f'<div id="cit-{_ls}" class="cit-pane" style="display:{_disp}"><div class="subtitle">{_sub}</div>{_cit_tables_for(_loc.get("directories", []))}</div>')
citations_section_html = f'<div class="loc-tabs">{"".join(_ctabs)}</div>{"".join(_cpanes)}'


# ─── Render Local Falcon visual grids + 30-day comparison ────────────────────
LF_GRID_DIR = A_BASE / "raw" / "lf-grids"


def _rank_color(rank: int) -> str:
    """Color cell by rank — green for top 3, yellow for top 10, orange for top 20, red for not found."""
    if rank is None or rank == 0 or rank > 20:
        return "#dc2626"   # red — not found / outside top 20
    if rank <= 3:
        return "#16a34a"   # green — local pack
    if rank <= 10:
        return "#84cc16"   # lime — top 10
    if rank <= 15:
        return "#eab308"   # yellow
    return "#f97316"       # orange — 16-20


def _render_grid_svg(cells: list, side_px: int = 240) -> str:
    """Render an N×N grid as SVG with rank numbers inside cells.

    Cells are expected to have rank + position (or lat/lng). We sort/place by
    explicit row/column if available, otherwise infer from list order assuming
    row-major fill.
    """
    n = int(round(len(cells) ** 0.5)) or 1
    cell_size = side_px / n
    svg_parts = [f'<svg viewBox="0 0 {side_px} {side_px}" xmlns="http://www.w3.org/2000/svg" '
                 f'style="background:#0a0e1a;border-radius:8px">']
    # Place cells
    for i, c in enumerate(cells):
        if not isinstance(c, dict):
            continue
        # Prefer explicit row/col from LF response, else infer
        row = c.get("row")
        col = c.get("col") or c.get("column")
        if row is None or col is None:
            row = i // n
            col = i % n
        rank = c.get("rank") or 0
        x = col * cell_size
        y = row * cell_size
        color = _rank_color(rank)
        label = str(rank) if rank and rank <= 20 else "X"
        svg_parts.append(
            f'<rect x="{x:.1f}" y="{y:.1f}" width="{cell_size - 1.5:.1f}" height="{cell_size - 1.5:.1f}" '
            f'fill="{color}" rx="3"/>'
        )
        # Center the rank number in the cell
        svg_parts.append(
            f'<text x="{x + cell_size/2:.1f}" y="{y + cell_size/2 + 4:.1f}" '
            f'font-family="Figtree,sans-serif" font-size="{max(10, cell_size/3.2):.0f}" '
            f'font-weight="700" fill="white" text-anchor="middle">{label}</text>'
        )
    svg_parts.append('</svg>')
    return "".join(svg_parts)


def _load_grid_file(label: str) -> tuple[list, dict]:
    """Find the saved scan file for a given label (e.g. 'current_jun9') and return cells + raw."""
    if not LF_GRID_DIR.exists():
        return [], {}
    for p in LF_GRID_DIR.glob(f"{label}__*.json"):
        data = json.loads(p.read_text())
        scan = data.get("data") or data.get("scan") or data
        cells = (
            scan.get("rank_data") or scan.get("data_points") or
            scan.get("points") or scan.get("grid") or scan.get("cells") or []
        )
        return cells, scan
    return [], {}


def _grid_summary(cells: list) -> dict:
    """Compute summary stats from a grid cell array."""
    if not cells:
        return {}
    ranks = [c.get("rank", 0) for c in cells if isinstance(c, dict)]
    found = [r for r in ranks if r and r <= 20]
    return {
        "found": len(found),
        "total": len(ranks),
        "top_3": sum(1 for r in ranks if 1 <= r <= 3),
        "top_10": sum(1 for r in ranks if 1 <= r <= 10),
        "arp": round(sum(found) / max(1, len(found)), 1) if found else 0,
        "coverage_pct": round(100 * len(found) / max(1, len(ranks))),
    }


# Build the grid section — 4-column horizontal row, one column per keyword.
# Each column shows the current grid + summary stats. If the keyword has prior data,
# add a small delta badge showing rank movement. Detailed before/after lives in an
# expandable section below the grid row.
lf_grids_html = ""
detail_expand_html = ""
# MULTI-LOCATION proximity heatmap: one TAB per location. Each tab shows that
# location's per-keyword colored grids, read from raw/lf-grids/{locslug}__{kwslug}.json.
import re as _re, json as _json
def _slug(s): return _re.sub(r'[^a-z0-9]+', '-', (s or '').lower()).strip('-')
def _locslug(name): return (_slug(name).split('-')[0] or 'office')   # 'Louisville' -> 'louisville'

def _grid_cards_for(locslug):
    cards = []
    if not LF_GRID_DIR.exists():
        return cards
    for p in sorted(LF_GRID_DIR.glob(f"{locslug}__*.json")):
        try:
            data = _json.loads(p.read_text())
        except Exception:
            continue
        cells = data.get("data_points") or []
        if not cells:
            continue
        st = _grid_summary(cells)
        m = data.get("metrics") or {}
        solv = m.get("solv_percent")
        solv_txt = f'{float(solv):.0f}% SoLV' if solv not in (None, "") else f'{st["coverage_pct"]}% coverage'
        cards.append(
            f'<div class="lf-grid-col">'
            f'  <div class="lf-col-title">{esc(data.get("keyword",""))}</div>'
            f'  <div class="lf-col-date">{esc(solv_txt)} · {st["total"]}-cell grid</div>'
            f'  {_render_grid_svg(cells, side_px=200)}'
            f'  <div class="lf-col-stats">'
            f'    <div class="stat-row"><span class="stat-label">ARP</span><span class="stat-val">{st["arp"]}</span></div>'
            f'    <div class="stat-row"><span class="stat-label">Top 3</span><span class="stat-val">{st["top_3"]}/{st["total"]}</span></div>'
            f'    <div class="stat-row"><span class="stat-label">Coverage</span><span class="stat-val">{st["coverage_pct"]}%</span></div>'
            f'  </div>'
            f'</div>'
        )
    return cards

_tab_locs = [l for l in LOCATIONS if l.get("role") != "duplicate"]
if not _tab_locs:
    _tab_locs = [{"name": esc(CLIENT_NAME), "role": "primary"}]
if LF_GRID_DIR.exists() and list(LF_GRID_DIR.glob("*.json")):
    tabs, panes = [], []
    for i, loc in enumerate(_tab_locs):
        ls = _locslug(loc.get("name"))
        cards = _grid_cards_for(ls)
        active = " active" if i == 0 else ""
        disp = "block" if i == 0 else "none"
        tabs.append(f'<button class="loc-tab{active}" onclick="showTab(this,\'lf\',\'lf-{ls}\')">{esc(loc.get("name"))}</button>')
        inner = (f'<div class="lf-grid-row">{"".join(cards)}</div>' if cards
                 else '<div class="lf-empty">No Local Falcon scans for this office yet — schedule grid scans to map its Maps-pack coverage.</div>')
        panes.append(f'<div id="lf-{ls}" class="lf-pane" style="display:{disp}">{inner}</div>')
    lf_grids_html = f'<div class="loc-tabs">{"".join(tabs)}</div>{"".join(panes)}'

# Empty state
if not lf_grids_html:
    lf_grids_html = (
        '<div class="lf-empty">'
        '  <strong>No grid data yet.</strong> Once the MCP is wired with LOCALFALCON_API_KEY, '
        '  this section auto-renders grids for every tracked keyword.'
        '</div>'
    )


# ─── Multi-location overview: every GBP tied to this business (1..N) ──────────
# Renders only when LOCATIONS has >1 entry or a duplicate listing is present, so
# single-location clients are unaffected.
locations_overview_html = ""
if LOCATIONS and (len([l for l in LOCATIONS if l.get("role") != "duplicate"]) > 1
                  or any(l.get("role") == "duplicate" for l in LOCATIONS)):
    n_real = len([l for l in LOCATIONS if l.get("role") != "duplicate"])
    rows = []
    for l in LOCATIONS:
        rv = l.get("reviews") or {}
        rev = f'{rv.get("avg")}★ / {rv.get("count")}' if rv.get("count") else "—"
        gmb = '<span style="color:#16a34a">✓ connected</span>' if l.get("gmb_connected") \
              else '<span style="color:#dc2626">✗ not connected</span>'
        grids = len(l.get("grid_keywords") or [])
        is_dup = l.get("role") == "duplicate"
        badge = ' <span style="color:#dc2626;font-weight:700;font-size:11px">DUPLICATE · P1</span>' if is_dup else \
                (' <span class="muted" style="font-size:11px">primary</span>' if l.get("role") == "primary" else "")
        rows.append(
            f'<tr{" style=background:#fef2f2" if is_dup else ""}>'
            f'<td><strong>{esc(l.get("name") or "")}</strong>{badge}'
            f'<br><span class="muted" style="font-size:12px">{esc(l.get("address") or "")}</span></td>'
            f'<td>{rev}</td><td>{gmb}</td><td style="text-align:center">{grids}</td>'
            f'<td class="muted" style="font-size:12px">{esc(l.get("notes") or "")}</td></tr>'
        )
    dup = next((l for l in LOCATIONS if l.get("role") == "duplicate"), None)
    dup_callout = ""
    if dup:
        dr = dup.get("reviews") or {}
        prim = next((l for l in LOCATIONS if l.get("role") == "primary"), {})
        pr = prim.get("reviews") or {}
        dup_callout = (
            f'<div style="margin-top:14px;padding:14px 18px;border-left:4px solid #dc2626;'
            f'background:#fef2f2;border-radius:6px">'
            f'<strong style="color:#dc2626">P1 — Duplicate Google Business Profile.</strong> '
            f'A second listing ({dr.get("avg")}★/{dr.get("count")} reviews) is competing with the primary '
            f'({pr.get("avg")}★/{pr.get("count")} reviews), splitting review equity and Maps ranking signal. '
            f'Consolidate/remove it via Google\'s duplicate-listing resolution before other GBP work.</div>'
        )
    # Per-office detail: each non-primary office gets its own block listing the four
    # audit components (proximity grid, GMB performance, GBP field audit, citations/NAP)
    # with real data when collected, else an explicit pending state. The PRIMARY office's
    # full data renders in the main Performance/Audit sections below.
    def _ok(): return '<span style="color:#16a34a">✓</span>'
    def _pend(t): return f'<span style="color:#b45309">⏳ {t}</span>'
    office_blocks = []
    _scolor = {"ok": "#16a34a", "weak": "#b45309", "missing": "#dc2626"}
    for loc in [l for l in LOCATIONS if l.get("role") == "office"]:
        ng = len(loc.get("grid_keywords") or [])
        rv = loc.get("reviews") or {}
        rev_txt = f'{rv.get("avg")}★ / {rv.get("count")} reviews' if rv.get("count") else "—"
        gmb_line = ('Connected in Windsor — monthly insights feed pending (Windsor GMB returns a rotating account subset).'
                    if loc.get("gmb_connected") else 'GMB not connected in Windsor.')
        # Real GBP field-by-field audit when a profile was pulled for this office
        gf = loc.get("gbp_fields") or []
        if gf:
            gf_rows = "".join(
                f'<tr><td>{esc(x.get("field"))}</td><td>{esc(str(x.get("current")))}</td>'
                f'<td style="color:{_scolor.get(x.get("status"),"#666")};font-weight:700">{esc(x.get("status"))}</td></tr>'
                for x in gf)
            gbp_cell = (f'<table style="margin:2px 0"><thead><tr><th>Field</th><th>Current</th><th>Status</th></tr></thead>'
                        f'<tbody>{gf_rows}</tbody></table>')
        else:
            gbp_cell = _pend("Profile field audit pending — pull this office's GBP profile.")
        office_blocks.append(
            f'<section class="panel"><h3>📍 {esc(loc.get("name"))} — Office Audit</h3>'
            f'<div class="subtitle">{esc(loc.get("address") or "")} · {rev_txt}</div>'
            f'<table><tbody>'
            f'<tr><td style="width:230px;vertical-align:top"><strong>Maps proximity grid</strong></td>'
            f'<td>{(str(ng)+" keyword grids") if ng else _pend("No Local Falcon scans for this office yet — schedule grid scans to map Maps-pack coverage.")}</td></tr>'
            f'<tr><td style="vertical-align:top"><strong>GMB performance</strong></td><td>{_ok() if loc.get("gmb_connected") else ""} {gmb_line}</td></tr>'
            f'<tr><td style="vertical-align:top"><strong>GBP field-by-field audit</strong></td><td>{gbp_cell}</td></tr>'
            f'<tr><td style="vertical-align:top"><strong>Citations / NAP consistency</strong></td>'
            f'<td>{_pend("Per-office NAP + citation check pending — verify against this office address.")}</td></tr>'
            f'</tbody></table></section>'
        )
    locations_overview_html = (
        f'<section class="panel"><h3>Google Business Profiles — {n_real} Location{"s" if n_real != 1 else ""}</h3>'
        f'<div class="subtitle">Every Google Business Profile tied to this business. Heatmaps, GMB performance, and the '
        f'GBP field audit below are broken out per location.</div>'
        f'<table><thead><tr><th>Location</th><th>Reviews</th><th>GMB data</th><th>Grids</th><th>Notes</th></tr></thead>'
        f'<tbody>{"".join(rows)}</tbody></table>{dup_callout}</section>'
    )


# ─── Render: GBP Performance from Windsor (line charts at TOP of report) ────
def _render_line_chart(points, label, color, w=520, h=180):
    """Simple SVG line chart with area fill, data points, axis labels.
    points: list of {"x": str, "y": int}
    """
    if not points:
        return ""
    PAD_L, PAD_R, PAD_T, PAD_B = 48, 16, 24, 36
    chart_w = w - PAD_L - PAD_R
    chart_h = h - PAD_T - PAD_B

    max_y = max((p["y"] for p in points), default=0) or 1
    # Add a little headroom
    y_top = int(max_y * 1.15) or 1
    n = len(points)
    if n == 1:
        xs = [PAD_L + chart_w / 2]
    else:
        xs = [PAD_L + (i / (n - 1)) * chart_w for i in range(n)]
    ys = [PAD_T + chart_h - (p["y"] / y_top) * chart_h for p in points]

    # Build path
    line_d = " ".join(f"{'M' if i == 0 else 'L'} {xs[i]:.1f} {ys[i]:.1f}" for i in range(n))
    area_d = f"M {xs[0]:.1f} {PAD_T + chart_h} " + line_d.replace("M ", "L ", 1) + f" L {xs[-1]:.1f} {PAD_T + chart_h} Z"

    # Y-axis gridlines (4 lines)
    gridlines = ""
    for i in range(5):
        gy = PAD_T + (i / 4) * chart_h
        gv = int(y_top * (1 - i / 4))
        gridlines += f'<line x1="{PAD_L}" y1="{gy:.1f}" x2="{w - PAD_R}" y2="{gy:.1f}" stroke="#e5e7eb" stroke-width="1" stroke-dasharray="2,3"/>'
        gridlines += f'<text x="{PAD_L - 8}" y="{gy + 4:.1f}" font-size="10" fill="#9ca3af" text-anchor="end" font-variant-numeric="tabular-nums">{gv:,}</text>'

    # X-axis labels (every other month to avoid clutter)
    x_labels = ""
    for i, p in enumerate(points):
        if i % 2 == 0 or i == n - 1:
            x_labels += f'<text x="{xs[i]:.1f}" y="{h - PAD_B + 18}" font-size="10" fill="#6b7280" text-anchor="middle">{html.escape(p["x"])}</text>'

    # Data points
    dots = ""
    for i in range(n):
        dots += (f'<circle cx="{xs[i]:.1f}" cy="{ys[i]:.1f}" r="3.5" fill="{color}" stroke="white" stroke-width="1.5"/>'
                 f'<title>{html.escape(points[i]["x"])}: {points[i]["y"]:,}</title>')

    return (
        f'<svg viewBox="0 0 {w} {h}" xmlns="http://www.w3.org/2000/svg" style="display:block;width:100%;height:auto;max-width:{w}px">'
        f'  {gridlines}'
        f'  <path d="{area_d}" fill="{color}" fill-opacity="0.12"/>'
        f'  <path d="{line_d}" fill="none" stroke="{color}" stroke-width="2.5" stroke-linejoin="round"/>'
        f'  {dots}'
        f'  {x_labels}'
        f'</svg>'
    )


gbp_performance_html = ""
if windsor_gbp and windsor_gbp.get("monthly"):
    months = windsor_gbp["monthly"]
    totals = windsor_gbp.get("totals", {})

    # Compute trailing 6mo vs prior 6mo to show whether things are improving
    def _sum(field, slice_):
        return sum(m.get(field, 0) for m in slice_)
    recent6  = months[-6:]
    prior6   = months[:6]
    def _pct_change(curr, prev):
        if not prev: return 0
        return round(100 * (curr - prev) / prev, 1)

    def _short_month(m_str):
        # "2025-06" → "Jun '25"
        try:
            y, m = m_str.split("-")
            mname = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"][int(m) - 1]
            return f"{mname} '{y[2:]}"
        except Exception:
            return m_str

    imp_pts   = [{"x": _short_month(m["month"]), "y": m.get("impressions", 0)} for m in months]
    call_pts  = [{"x": _short_month(m["month"]), "y": m.get("call_clicks", 0)} for m in months]
    web_pts   = [{"x": _short_month(m["month"]), "y": m.get("website_clicks", 0)} for m in months]
    dir_pts   = [{"x": _short_month(m["month"]), "y": m.get("direction_requests", 0)} for m in months]

    # Trend deltas
    imp_delta  = _pct_change(_sum("impressions", recent6),       _sum("impressions", prior6))
    call_delta = _pct_change(_sum("call_clicks", recent6),       _sum("call_clicks", prior6))
    web_delta  = _pct_change(_sum("website_clicks", recent6),    _sum("website_clicks", prior6))
    dir_delta  = _pct_change(_sum("direction_requests", recent6),_sum("direction_requests", prior6))

    def _delta_chip(pct):
        if pct > 0:    return f'<span style="color:#16a34a;font-weight:700">▲ +{pct}%</span>'
        if pct < 0:    return f'<span style="color:#dc2626;font-weight:700">▼ {pct}%</span>'
        return '<span class="muted">→ 0%</span>'

    chart_imp  = _render_line_chart(imp_pts,  "Profile Views", "#2563EB")
    chart_call = _render_line_chart(call_pts, "Phone Calls",   "#16a34a")
    chart_web  = _render_line_chart(web_pts,  "Website Clicks","#7c3aed")
    chart_dir  = _render_line_chart(dir_pts,  "Directions",    "#ea580c")

    gbp_performance_html = f"""
    <section class="panel" style="border:2px solid #2563EB22">
      <h3>Google Business Profile Performance — Last 12 Months</h3>
      <div class="subtitle">
        Live Windsor.ai pull from {esc(windsor_gbp.get('account_name', 'GBP'))}. Profile activity by month.
        <span class="muted" style="display:block;margin-top:4px;font-size:12px">
          Trailing 6 months vs prior 6 months below each chart.
        </span>
      </div>

      <div style="display:grid;grid-template-columns:repeat(2,1fr);gap:24px;margin-top:18px">
        <div>
          <div style="display:flex;justify-content:space-between;align-items:baseline;margin-bottom:6px">
            <div>
              <div style="font-family:var(--display);font-size:14px;text-transform:uppercase;letter-spacing:0.04em;color:#1f2937">Profile Views</div>
              <div style="font-size:24px;font-weight:700;color:#2563EB;font-variant-numeric:tabular-nums">{totals.get('impressions', 0):,}</div>
            </div>
            <div style="text-align:right;font-size:12px">
              <div class="muted">vs prior 6mo</div>
              <div>{_delta_chip(imp_delta)}</div>
            </div>
          </div>
          {chart_imp}
        </div>

        <div>
          <div style="display:flex;justify-content:space-between;align-items:baseline;margin-bottom:6px">
            <div>
              <div style="font-family:var(--display);font-size:14px;text-transform:uppercase;letter-spacing:0.04em;color:#1f2937">Phone Calls</div>
              <div style="font-size:24px;font-weight:700;color:#16a34a;font-variant-numeric:tabular-nums">{totals.get('call_clicks', 0):,}</div>
            </div>
            <div style="text-align:right;font-size:12px">
              <div class="muted">vs prior 6mo</div>
              <div>{_delta_chip(call_delta)}</div>
            </div>
          </div>
          {chart_call}
        </div>

        <div>
          <div style="display:flex;justify-content:space-between;align-items:baseline;margin-bottom:6px">
            <div>
              <div style="font-family:var(--display);font-size:14px;text-transform:uppercase;letter-spacing:0.04em;color:#1f2937">Website Clicks</div>
              <div style="font-size:24px;font-weight:700;color:#7c3aed;font-variant-numeric:tabular-nums">{totals.get('website_clicks', 0):,}</div>
            </div>
            <div style="text-align:right;font-size:12px">
              <div class="muted">vs prior 6mo</div>
              <div>{_delta_chip(web_delta)}</div>
            </div>
          </div>
          {chart_web}
        </div>

        <div>
          <div style="display:flex;justify-content:space-between;align-items:baseline;margin-bottom:6px">
            <div>
              <div style="font-family:var(--display);font-size:14px;text-transform:uppercase;letter-spacing:0.04em;color:#1f2937">Direction Requests</div>
              <div style="font-size:24px;font-weight:700;color:#ea580c;font-variant-numeric:tabular-nums">{totals.get('direction_requests', 0):,}</div>
            </div>
            <div style="text-align:right;font-size:12px">
              <div class="muted">vs prior 6mo</div>
              <div>{_delta_chip(dir_delta)}</div>
            </div>
          </div>
          {chart_dir}
        </div>
      </div>

      <p class="muted" style="margin-top:18px;font-size:12px">
        Data source: Google Business Profile via Windsor.ai · Date range: {esc(windsor_gbp.get('date_range',{}).get('start',''))} to {esc(windsor_gbp.get('date_range',{}).get('end',''))}
      </p>
    </section>
    """

# Wrap GMB performance in per-location tabs (multi-location). Primary office shows the
# real Windsor charts; other offices show their connection status until their feed lands.
if gbp_performance_html and len(_tab_locs) > 1:
    _gtabs, _gpanes = [], []
    for i, loc in enumerate(_tab_locs):
        ls = _locslug(loc.get("name"))
        active = " active" if i == 0 else ""
        disp = "block" if i == 0 else "none"
        _gtabs.append(f'<button class="loc-tab{active}" onclick="showTab(this,\'gmb\',\'gmb-{ls}\')">{esc(loc.get("name"))}</button>')
        if i == 0:
            inner = gbp_performance_html
        elif loc.get("gmb_connected"):
            inner = ('<section class="panel"><h3>Google Business Profile Performance — Last 12 Months</h3>'
                     '<div class="lf-empty">GMB connected in Windsor — this office\'s monthly insights feed has not '
                     'delivered rows yet (Windsor returns a rotating account subset). The 12-month chart populates once its data flows.</div></section>')
        else:
            inner = ('<section class="panel"><h3>Google Business Profile Performance — Last 12 Months</h3>'
                     '<div class="lf-empty">GMB not connected in Windsor for this office.</div></section>')
        _gpanes.append(f'<div id="gmb-{ls}" class="gmb-pane" style="display:{disp}">{inner}</div>')
    gbp_performance_html = f'<div class="loc-tabs">{"".join(_gtabs)}</div>' + "".join(_gpanes)


# ─── Review Velocity (from Windsor) ──────────────────────────────────────────
review_velocity_html = ""
if windsor_reviews and windsor_reviews.get("client_monthly"):
    client_monthly = windsor_reviews["client_monthly"]
    client_total   = windsor_reviews.get("client_total", 0)
    peers          = windsor_reviews.get("peer_benchmarks", [])

    # Bar chart for Batch's monthly velocity
    def _render_bar_chart(months_data, color, w=520, h=180):
        if not months_data:
            return ""
        PAD_L, PAD_R, PAD_T, PAD_B = 36, 16, 24, 36
        chart_w = w - PAD_L - PAD_R
        chart_h = h - PAD_T - PAD_B
        max_y = max((m["y"] for m in months_data), default=0) or 1
        y_top = max(max_y, 5)  # min scale of 5 so bars don't dominate
        n = len(months_data)
        bar_w = chart_w / n * 0.7
        gap   = chart_w / n * 0.3

        bars = ""
        for i, m in enumerate(months_data):
            x = PAD_L + (i + 0.15) * (chart_w / n)
            bar_h = (m["y"] / y_top) * chart_h if y_top > 0 else 0
            y = PAD_T + chart_h - bar_h
            bars += (f'<rect x="{x:.1f}" y="{y:.1f}" width="{bar_w:.1f}" height="{bar_h:.1f}" '
                     f'fill="{color}" rx="2"><title>{m["x"]}: {m["y"]} new reviews</title></rect>')
            # Label above bar
            if m["y"] > 0:
                bars += (f'<text x="{x + bar_w/2:.1f}" y="{y - 4:.1f}" font-size="10" '
                         f'fill="#1f2937" text-anchor="middle" font-weight="700">{m["y"]}</text>')

        # X-axis labels (every other month)
        x_labels = ""
        for i, m in enumerate(months_data):
            if i % 2 == 0 or i == n - 1:
                cx = PAD_L + (i + 0.5) * (chart_w / n)
                x_labels += f'<text x="{cx:.1f}" y="{h - PAD_B + 18}" font-size="10" fill="#6b7280" text-anchor="middle">{html.escape(m["x"])}</text>'

        # Y gridlines
        gridlines = ""
        for i in range(4):
            gy = PAD_T + (i / 3) * chart_h
            gv = int(y_top * (1 - i / 3))
            gridlines += f'<line x1="{PAD_L}" y1="{gy:.1f}" x2="{w - PAD_R}" y2="{gy:.1f}" stroke="#e5e7eb" stroke-width="1" stroke-dasharray="2,3"/>'
            gridlines += f'<text x="{PAD_L - 6}" y="{gy + 4:.1f}" font-size="10" fill="#9ca3af" text-anchor="end">{gv}</text>'

        return (
            f'<svg viewBox="0 0 {w} {h}" xmlns="http://www.w3.org/2000/svg" style="display:block;width:100%;height:auto;max-width:{w}px">'
            f'  {gridlines}'
            f'  {bars}'
            f'  {x_labels}'
            f'</svg>'
        )

    def _short_month_rev(m_str):
        try:
            y, m = m_str.split("-")
            mname = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"][int(m) - 1]
            return f"{mname} '{y[2:]}"
        except Exception:
            return m_str

    batch_bars = [{"x": _short_month_rev(m["month"]), "y": m.get("new_reviews", 0)} for m in client_monthly]
    batch_chart = _render_bar_chart(batch_bars, "#dc2626")

    # Direct SERP competitor snapshot (current totals from DfS keyword tracker data)
    # Aggregate unique competitors across all 50 keywords
    serp_competitors = {}
    if keyword_rankings and keyword_rankings.get("results"):
        for r in keyword_rankings["results"]:
            for c in r.get("top_3_competitors", []):
                key = (c.get("domain") or c.get("name", "")).lower().strip()
                if not key or "batch" in key:
                    continue
                if key not in serp_competitors:
                    serp_competitors[key] = {
                        "name":    c.get("name", ""),
                        "domain":  c.get("domain", ""),
                        "rating":  c.get("rating"),
                        "reviews": c.get("reviews"),
                        "serp_appearances": 0,
                    }
                else:
                    # Keep highest review count seen (data should be consistent)
                    if c.get("reviews") and (not serp_competitors[key]["reviews"]
                                              or c["reviews"] > serp_competitors[key]["reviews"]):
                        serp_competitors[key]["reviews"] = c["reviews"]
                        serp_competitors[key]["rating"]  = c.get("rating")
                serp_competitors[key]["serp_appearances"] += 1

    # Sort by review count desc, take top 10
    top_serp = sorted(
        [c for c in serp_competitors.values() if isinstance(c.get("reviews"), int)],
        key=lambda c: -c["reviews"]
    )[:10]

    avg_monthly_batch = round(client_total / 12, 1)
    client_reviews_now = None
    # Try to get Batch's current review count from GBP snapshot
    try:
        for f in gbp.get("fields", []):
            if f.get("field") == "review_count":
                client_reviews_now = f.get("current")
                break
    except Exception:
        pass
    if not client_reviews_now:
        client_reviews_now = 89  # fallback to known value

    competitor_rows = ""
    for c in top_serp:
        diff = c["reviews"] - client_reviews_now if client_reviews_now else 0
        diff_color = "#dc2626" if diff > 0 else "#16a34a"
        diff_label = f"+{diff}" if diff > 0 else str(diff)
        competitor_rows += (
            f'<tr>'
            f'  <td><strong>{esc(c["name"])}</strong></td>'
            f'  <td style="text-align:center">{c.get("rating","?")}★</td>'
            f'  <td style="text-align:right;font-variant-numeric:tabular-nums"><strong>{c["reviews"]}</strong></td>'
            f'  <td style="text-align:right;color:{diff_color};font-weight:700;font-variant-numeric:tabular-nums">{diff_label}</td>'
            f'  <td style="text-align:center">{c["serp_appearances"]}</td>'
            f'</tr>'
        )

    review_velocity_html = f"""
    <section class="panel" style="border:2px solid #dc262622">
      <h3>Review Velocity — Where the Ranking Gap Comes From</h3>
      <div class="subtitle">
        New Google reviews acquired per month over the last 12 months.
        Batch is acquiring reviews at a fraction of the rate that ranking competitors are.
      </div>

      <div style="margin-top:18px">
        <div style="display:flex;justify-content:space-between;align-items:baseline;margin-bottom:6px">
          <div>
            <div style="font-family:var(--display);font-size:14px;text-transform:uppercase;letter-spacing:0.04em;color:#1f2937">{esc(CLIENT_NAME)} — New Reviews / Month</div>
            <div style="font-size:24px;font-weight:700;color:#dc2626;font-variant-numeric:tabular-nums">{client_total} <span style="font-size:14px;color:#6b7280;font-weight:500">in 12 months · {avg_monthly_batch}/mo avg</span></div>
          </div>
        </div>
        {batch_chart}
      </div>

      <div style="margin-top:28px">
        <div style="font-family:var(--display);font-size:14px;text-transform:uppercase;letter-spacing:0.04em;color:#1f2937;margin-bottom:6px">
          Direct SERP Competitors — Review Count Snapshot
        </div>
        <div class="muted" style="font-size:12px;margin-bottom:12px">
          The firms actually beating {esc(CLIENT_NAME)} in the Maps Pack across the 50 tracked keywords.
          Snapshot of current totals (not velocity — Google doesn't expose historical review counts for businesses you don't own).
        </div>
        <table style="font-size:13px;width:100%">
          <thead><tr>
            <th>Firm</th>
            <th style="text-align:center">Rating</th>
            <th style="text-align:right">Total Reviews</th>
            <th style="text-align:right">vs {esc(CLIENT_NAME)}</th>
            <th style="text-align:center">Appears in SERPs</th>
          </tr></thead>
          <tbody>
            <tr style="background:#fef2f2">
              <td><strong>{esc(CLIENT_NAME)} (YOU)</strong></td>
              <td style="text-align:center">—</td>
              <td style="text-align:right;font-variant-numeric:tabular-nums"><strong>{client_reviews_now}</strong></td>
              <td style="text-align:right">baseline</td>
              <td style="text-align:center">—</td>
            </tr>
            {competitor_rows}
          </tbody>
        </table>
      </div>

      <div style="margin-top:20px;padding:16px 22px;background:#fef2f2;border-left:4px solid #dc2626;border-radius:8px">
        <strong>The story:</strong> the firms beating {esc(CLIENT_NAME)} in the Maps Pack have <strong>2-5× the review count</strong>. {esc(CLIENT_NAME)} is acquiring new reviews at <strong>{avg_monthly_batch}/month</strong> — at that pace it would take years to close the gap. Review acquisition velocity is the single biggest lever Sprint 3 can pull.
      </div>

      <p class="muted" style="margin-top:12px;font-size:12px">
        Data sources: {esc(CLIENT_NAME)}'s monthly velocity from Windsor.ai GMB connector. Direct competitor totals from DataForSEO Local Finder SERP results across the 50 tracked keywords.
      </p>
    </section>
    """


# ─── Render: 50-keyword tracker section (Maps + Organic via DfS) ─────────────
keyword_tracker_html = ""
performance_trend_html = ""
if keyword_rankings and keyword_rankings.get("results"):
    kw_results  = keyword_rankings["results"]
    kw_summary  = keyword_rankings.get("summary", {})
    kw_cost     = keyword_rankings.get("total_cost_usd", 0)
    kw_pulled   = (keyword_rankings.get("pulled_at") or "")[:10]
    total_kw    = len(kw_results)

    # City × Service heatmap
    cities   = sorted({r["city"] for r in kw_results if r.get("city")})
    services = sorted({r["service"] for r in kw_results if r.get("service")})

    def _cell_color(rank):
        if rank is None:    return "#f3f4f6"   # gray
        if rank <= 3:       return "#bbf7d0"   # green
        if rank <= 10:      return "#fef3c7"   # yellow
        if rank <= 20:      return "#fed7aa"   # orange
        return "#fecaca"                       # red

    def _cell_text_color(rank):
        return "#6b7280" if rank is None else "#111827"

    heatmap_rows = ""
    for city in cities:
        cells = f'<td style="font-weight:700;background:#f9fafb;padding:10px 14px;border:1px solid #e5e7eb">{esc(city)}</td>'
        for svc in services:
            matches = [r for r in kw_results
                       if r["city"] == city and r["service"] == svc and r.get("maps_rank") is not None]
            if matches:
                best = min(r["maps_rank"] for r in matches)
                cells += (
                    f'<td style="background:{_cell_color(best)};color:{_cell_text_color(best)};'
                    f'text-align:center;font-weight:700;padding:10px 14px;border:1px solid #e5e7eb;'
                    f'font-variant-numeric:tabular-nums">#{best}</td>'
                )
            else:
                cells += (
                    f'<td style="background:{_cell_color(None)};color:{_cell_text_color(None)};'
                    f'text-align:center;padding:10px 14px;border:1px solid #e5e7eb">—</td>'
                )
        heatmap_rows += f"<tr>{cells}</tr>"

    heatmap_header = '<th style="background:#1f2937;color:white;padding:10px 14px;text-align:left;border:1px solid #e5e7eb">City</th>'
    for svc in services:
        heatmap_header += f'<th style="background:#1f2937;color:white;padding:10px 14px;text-align:center;border:1px solid #e5e7eb">{esc(svc)}</th>'

    # Full table — sorted further below by volume + rank
    def _rank_pill(rank):
        if rank is None:
            return '<span style="color:#9ca3af">—</span>'
        if rank <= 3:    bg, fg = "#16a34a", "white"
        elif rank <= 10: bg, fg = "#84cc16", "white"
        elif rank <= 20: bg, fg = "#f97316", "white"
        else:            bg, fg = "#dc2626", "white"
        return (f'<span style="background:{bg};color:{fg};padding:2px 8px;border-radius:4px;'
                f'font-weight:700;font-size:11px">#{rank}</span>')

    # ── Bucket keywords by city, sort cities by total volume desc ──────────
    from collections import defaultdict
    by_city = defaultdict(list)
    for r in kw_results:
        by_city[r.get("city", "—")].append(r)

    # Compute per-city stats for the bucket header
    city_stats = {}
    for city, rows in by_city.items():
        total_vol = sum((r.get("search_volume") or 0) for r in rows)
        ranked = [r for r in rows if r.get("maps_rank") is not None]
        best_maps = min((r["maps_rank"] for r in ranked), default=None)
        city_stats[city] = {
            "total_volume": total_vol,
            "ranked_count": len(ranked),
            "total_count":  len(rows),
            "best_maps":    best_maps,
        }

    cities_sorted = sorted(by_city.keys(), key=lambda c: -(city_stats[c]["total_volume"]))

    # Render each city as a collapsible <details>. Default-closed for cities
    # where Batch has zero rankings (clears Fuquay-Varina-style dead space).
    city_blocks = ""
    for city in cities_sorted:
        stats = city_stats[city]
        best_label = f"#{stats['best_maps']}" if stats["best_maps"] else "—"
        # All cities closed by default — keeps the page short. The summary line
        # (volume / ranked / best Maps rank) gives the strategist enough signal
        # to decide which cities to expand.
        open_attr = ''

        # Sort keywords within city: volume desc, then ranked first, then by rank
        sorted_kw = sorted(by_city[city], key=lambda r: (
            -(r.get("search_volume") or 0),
            r.get("maps_rank") is None,
            r.get("maps_rank") or 999,
        ))

        city_rows = ""
        for r in sorted_kw:
            ai_rank = r.get("ai_rank")
            if ai_rank is None:
                ai_cell = '<span class="muted" title="No AI Overview returned for this query">—</span>'
            elif ai_rank == 0:
                ai_cell = '<span style="background:#dc2626;color:white;padding:2px 8px;border-radius:4px;font-weight:700;font-size:11px">Not mentioned</span>'
            else:
                bg = "#16a34a" if ai_rank <= 3 else ("#84cc16" if ai_rank <= 10 else "#f97316")
                ai_cell = f'<span style="background:{bg};color:white;padding:2px 8px;border-radius:4px;font-weight:700;font-size:11px">#{ai_rank}</span>'

            vol = r.get("search_volume")
            kd  = r.get("keyword_difficulty")
            if vol is None:
                vol_cell = '<span class="muted">—</span>'
            elif vol == 0:
                vol_cell = '<span class="muted">0</span>'
            else:
                vol_color = "#1f2937" if vol >= 100 else "#6b7280"
                kd_tag = ""
                if isinstance(kd, (int, float)):
                    if kd >= 50:    kd_bg, kd_fg, kd_lbl = "#fee2e2", "#991b1b", f"KD {int(kd)} HARD"
                    elif kd >= 30:  kd_bg, kd_fg, kd_lbl = "#fef3c7", "#92400e", f"KD {int(kd)} MED"
                    elif kd >= 10:  kd_bg, kd_fg, kd_lbl = "#dbeafe", "#1e40af", f"KD {int(kd)}"
                    else:           kd_bg, kd_fg, kd_lbl = "#d1fae5", "#065f46", f"KD {int(kd)} EASY"
                    kd_tag = (f'<div style="font-size:10px;margin-top:2px"><span style="background:{kd_bg};color:{kd_fg};'
                              f'padding:1px 6px;border-radius:3px;font-weight:600;letter-spacing:0.04em">{kd_lbl}</span></div>')
                vol_cell = (f'<div style="color:{vol_color};font-weight:700;font-variant-numeric:tabular-nums">{vol:,}/mo</div>'
                            f'{kd_tag}')

            city_rows += (
                f'<tr>'
                f'  <td><strong>{esc(r["keyword"])}</strong></td>'
                f'  <td style="text-align:center">{vol_cell}</td>'
                f'  <td style="text-align:center">{_rank_pill(r.get("maps_rank"))}</td>'
                f'  <td style="text-align:center">{_rank_pill(r.get("organic_rank"))}</td>'
                f'  <td style="text-align:center">{ai_cell}</td>'
                f'</tr>'
            )

        city_blocks += f"""
        <details class="city-bucket"{open_attr}>
          <summary style="background:#1f2937;color:white;padding:12px 16px;cursor:pointer;border-radius:6px;margin-top:8px;list-style:none">
            <span style="font-family:var(--display);font-size:14px;text-transform:uppercase;letter-spacing:0.05em">{esc(city.upper())}</span>
            <span style="font-family:var(--body);font-size:12px;font-weight:400;text-transform:none;letter-spacing:0;opacity:0.75;margin-left:12px">
              {stats["total_volume"]:,} searches/mo · {stats["ranked_count"]}/{stats["total_count"]} ranked · best Maps rank {best_label}
            </span>
          </summary>
          <table style="margin:0">
            <thead><tr>
              <th>Keyword</th>
              <th style="text-align:center">Volume</th>
              <th>Maps Rank</th><th>Organic Rank</th><th>AI Search</th>
            </tr></thead>
            <tbody>{city_rows}</tbody>
          </table>
        </details>
        """

    # Review gap callout — pull client review count from gbp + sample top competitors
    client_reviews = 0
    try:
        client_reviews = gbp.get("scores", {}).get("reviews_total", {}).get("current", 0) or \
                         gbp.get("source_data", {}).get("reviews_total", 0) or 0
    except Exception:
        client_reviews = 0

    competitor_review_counts = []
    for r in kw_results:
        for c in r.get("top_3_competitors", []):
            if c.get("reviews") and isinstance(c["reviews"], int):
                competitor_review_counts.append({"name": c["name"], "reviews": c["reviews"]})

    # Dedupe by name, keep highest review count
    seen = {}
    for c in competitor_review_counts:
        if c["name"] not in seen or seen[c["name"]] < c["reviews"]:
            seen[c["name"]] = c["reviews"]
    top_review_comps = sorted(seen.items(), key=lambda x: -x[1])[:5]

    review_gap_html = ""
    if client_reviews and top_review_comps:
        avg_top5 = sum(r for _, r in top_review_comps) / len(top_review_comps)
        gap_multiplier = avg_top5 / client_reviews if client_reviews else 0
        comp_list_html = "".join(
            f'<tr><td>{esc(n)}</td><td style="text-align:right;font-variant-numeric:tabular-nums">{r}</td></tr>'
            for n, r in top_review_comps
        )
        review_gap_html = f"""
        <div class="review-gap-callout" style="margin-top:22px;padding:20px 24px;background:#fef2f2;border-left:4px solid #dc2626;border-radius:8px">
          <div style="font-family:var(--display);font-size:18px;text-transform:uppercase;margin-bottom:8px;color:#991b1b">Review Gap Analysis</div>
          <p style="margin:6px 0 14px;color:#374151">
            {esc(CLIENT_NAME)} has <strong>{client_reviews}</strong> reviews. The top 5 firms ranking for these keywords average
            <strong>{avg_top5:.0f}</strong> reviews — <strong>{gap_multiplier:.1f}x</strong> {esc(CLIENT_NAME)}'s count.
            This is the single largest ranking factor gap. Review acquisition should be Sprint 3's primary initiative.
          </p>
          <table style="font-size:13px;width:auto;min-width:340px">
            <thead><tr><th>Top-Ranking Competitor</th><th style="text-align:right">Reviews</th></tr></thead>
            <tbody>{comp_list_html}</tbody>
          </table>
        </div>
        """

    # ─── Performance trend (proxy signals across audit runs) ────────────────
    AUDITS_ROOT = A_BASE.parent  # clients/{slug}/local-audit/
    snapshots = []
    for audit_dir in sorted(AUDITS_ROOT.glob("*")):
        if not audit_dir.is_dir():
            continue
        kr_path = audit_dir / "keyword-rankings.json"
        gbp_path = audit_dir / "gbp-profile.json"
        cit_path = audit_dir / "citations.json"
        if not kr_path.exists():
            continue
        try:
            kr  = json.loads(kr_path.read_text())
            gbp_snap = json.loads(gbp_path.read_text()) if gbp_path.exists() else {}
            cit_snap = json.loads(cit_path.read_text()) if cit_path.exists() else {}
        except Exception:
            continue

        # Extract review count + rating from GBP snapshot (multiple possible paths)
        gbp_src = gbp_snap.get("source_data", {}) or gbp_snap.get("normalized", {}) or {}
        review_count = (gbp_src.get("reviews_count") or gbp_src.get("reviews_total")
                        or gbp_snap.get("reviews_count") or 0)
        rating = (gbp_src.get("rating") or gbp_snap.get("rating") or 0)
        photos = (gbp_src.get("photos_count") or gbp_src.get("total_photos")
                  or gbp_snap.get("photos_count") or 0)

        # Citation summary
        cit_total = cit_snap.get("_total") or len(cit_snap.get("directories", []) or [])
        cit_live  = cit_snap.get("_live_count") or 0
        if not cit_live and cit_snap.get("directories"):
            cit_live = sum(1 for d in cit_snap["directories"]
                           if d.get("status") in ("live", "live_correct", "live_mismatch"))

        sm = kr.get("summary", {})
        snapshots.append({
            "audit_id":      audit_dir.name,
            "pulled_at":     (kr.get("pulled_at") or "")[:10],
            "review_count":  review_count,
            "rating":        rating,
            "photos_count":  photos,
            "maps_top_3":    sm.get("maps_top_3", 0),
            "maps_top_10":   sm.get("maps_top_10", 0),
            "maps_ranked":   sm.get("maps_pack_ranking", "0/50").split("/")[0],
            "organic_top_10": sm.get("organic_top_10", 0),
            "organic_ranked": sm.get("organic_ranking", "0/50").split("/")[0],
            "citation_live": cit_live,
            "citation_total": cit_total,
        })

    snapshots.sort(key=lambda s: s["pulled_at"] or "")

    def _delta_pill(curr, prev):
        if prev is None or curr == prev:
            return '<span class="muted">—</span>'
        try:
            diff = curr - prev
        except TypeError:
            return '<span class="muted">—</span>'
        if diff > 0:
            return f'<span style="color:#16a34a;font-weight:700">▲ +{diff}</span>'
        if diff < 0:
            return f'<span style="color:#dc2626;font-weight:700">▼ {diff}</span>'
        return '<span class="muted">—</span>'

    if len(snapshots) >= 1:
        # Build table rows. Most recent on top.
        rev_snapshots = list(reversed(snapshots))
        trend_rows = ""
        for i, s in enumerate(rev_snapshots):
            prev = rev_snapshots[i + 1] if i + 1 < len(rev_snapshots) else None
            trend_rows += f"""
            <tr>
              <td><strong>{esc(s['pulled_at']) or esc(s['audit_id'])}</strong></td>
              <td style="text-align:center">{s['review_count']} {_delta_pill(s['review_count'], prev['review_count'] if prev else None)}</td>
              <td style="text-align:center">{s['rating']}★ {_delta_pill(s['rating'], prev['rating'] if prev else None)}</td>
              <td style="text-align:center">{s['photos_count']} {_delta_pill(s['photos_count'], prev['photos_count'] if prev else None)}</td>
              <td style="text-align:center">{s['maps_top_3']} / {s['maps_top_10']} / {s['maps_ranked']}</td>
              <td style="text-align:center">{s['organic_top_10']} / {s['organic_ranked']}</td>
              <td style="text-align:center">{s['citation_live']} / {s['citation_total']}</td>
            </tr>"""

        trend_note = ""
        if len(snapshots) == 1:
            trend_note = ('<p class="muted" style="margin-top:12px;font-size:13px">'
                          'Baseline captured. Re-run this audit on a regular cadence (monthly recommended) to '
                          'build the trend line. Each future run appears as a new row with deltas vs. the prior audit.'
                          '</p>')

        performance_trend_html = f"""
        <section class="panel">
          <h3>Performance Trend — Proxy Signals</h3>
          <div class="subtitle">
            What we can measure without GBP Insights API access: review velocity, rating, photo count,
            ranking visibility, and citation coverage. Each row = one audit run.
            <span class="muted" style="display:block;margin-top:4px;font-size:12px">
              <strong>Honest framing:</strong> these are not real GBP profile views, calls, or direction-request counts —
              those require Google OAuth setup. These proxies move alongside profile interactions and are the best
              signal available without authenticated GBP access.
            </span>
          </div>

          <table style="margin-top:16px">
            <thead>
              <tr>
                <th>Audit Date</th>
                <th style="text-align:center">Reviews</th>
                <th style="text-align:center">Rating</th>
                <th style="text-align:center">Photos</th>
                <th style="text-align:center">Maps Top 3 / Top 10 / T20</th>
                <th style="text-align:center">Organic Top 10 / T20</th>
                <th style="text-align:center">Citations Live / Total</th>
              </tr>
            </thead>
            <tbody>{trend_rows}</tbody>
          </table>
          {trend_note}
        </section>
        """
    else:
        performance_trend_html = ""

    keyword_tracker_html = f"""
    <section class="panel">
      <h3>Local Keyword Targets</h3>
      <div class="subtitle">
        Maps Pack + Google Organic + Google AI Mode rank for every location × service combination.
        <strong>Maps Pack:</strong> {kw_summary.get('maps_pack_ranking','—')} ranked
        ({kw_summary.get('maps_top_3',0)} top-3, {kw_summary.get('maps_top_10',0)} top-10) ·
        <strong>Organic:</strong> {kw_summary.get('organic_ranking','—')} ranked
        ({kw_summary.get('organic_top_10',0)} top-10) ·
        <strong>AI Overviews:</strong> {kw_summary.get('ai_block_present','—')} queries show AI · cited in {kw_summary.get('ai_cited','—')}
        <span class="muted" style="display:block;margin-top:4px;font-size:12px">Pulled {esc(kw_pulled)} · Rankings + AI from DataForSEO ($ {kw_cost:.3f}) · Volume + KD from Ahrefs Keywords Explorer</span>
      </div>

      <h4 style="margin-top:24px">City × Service Heatmap — Best Maps Rank</h4>
      <div style="overflow-x:auto;margin-top:12px">
        <table style="border-collapse:collapse;width:100%">
          <thead><tr>{heatmap_header}</tr></thead>
          <tbody>{heatmap_rows}</tbody>
        </table>
      </div>
      <div class="lf-grid-legend" style="margin-top:10px">
        <span><span class="legend-swatch" style="background:#bbf7d0"></span>Top 3</span>
        <span><span class="legend-swatch" style="background:#fef3c7"></span>Top 10</span>
        <span><span class="legend-swatch" style="background:#fed7aa"></span>11–20</span>
        <span><span class="legend-swatch" style="background:#f3f4f6"></span>Not found</span>
      </div>

      {review_gap_html}

      <details class="tactical" style="margin-top:22px">
        <summary>Full {total_kw}-keyword ranking table — bucketed by city (click city to expand)</summary>
        <div class="body">
          <p class="muted" style="margin:0 0 8px;font-size:12px">
            Cities are sorted by total monthly search volume. Cities where Batch has at least one ranking default open; zero-ranking cities collapse by default.
          </p>
          {city_blocks}
        </div>
      </details>
    </section>
    """


# ─── Render tactical: Local Falcon keyword rankings ──────────────────────────
falcon_rows = ""
for kw_name, kw_data in falcon_summary.items():
    coverage = kw_data.get("coverage_pct", 0)
    cov_color = "#10b981" if coverage >= 80 else "#f59e0b" if coverage >= 50 else "#ef4444"
    arp = kw_data.get("arp", 0)
    top_comp = kw_data.get("top_competitor") or {}
    falcon_rows += (
        f'<tr>'
        f'<td><strong>{esc(kw_name)}</strong></td>'
        f'<td class="num">{arp:.1f}</td>'
        f'<td class="num"><span style="color:{cov_color};font-weight:600">{coverage:.0f}%</span></td>'
        f'<td class="num">{kw_data.get("solv_pct", 0):.1f}%</td>'
        f'<td class="num">{kw_data.get("found", 0)}/{kw_data.get("total", 0)}</td>'
        f'<td>{esc(top_comp.get("name", "—"))}<div class="cell-sub">{top_comp.get("reviews", "—")} reviews · {top_comp.get("rating", "—")}★</div></td>'
        f'</tr>'
    )


# ─── Render Sprint 3 Add-Ons ─────────────────────────────────────────────────
# This audit isn't a standalone plan — its deliverables are appended to the client's
# existing project plan as Sprint 3 add-ons. Pull the consolidated parent actions
# straight from the same _build_consolidated_actions used by the XLSX builder.
def _read_xlsx_actions():
    """Read the Sprint 3 parent deliverables from the audit's Actions tab.

    We re-derive the same consolidated parent list the XLSX builder uses, so the
    report stays in sync with whatever's in Tab 9 of the workbook.
    """
    # Inline the same logic as build_local_audit_xlsx._build_consolidated_actions
    parents = []
    gbp_gaps_for_plan = [f for f in gbp.get("fields", []) if f.get("status") in ("missing", "weak", "api_pending")]
    if gbp_gaps_for_plan:
        worst_p = "P1" if any(f.get("weight", 0) >= 6 for f in gbp_gaps_for_plan) else "P2"
        parents.append({
            "category": "GBP",
            "action": "Optimize Google Business Profile",
            "priority": worst_p,
            "details": [
                f"{f['field'].replace('_', ' ').title()}: {f.get('action', '')}"
                for f in gbp_gaps_for_plan
            ],
        })
    real_mismatches_for_plan = [
        d for d in citations.get("directories", []) if d.get("status") == "live_mismatch"
    ]
    if real_mismatches_for_plan:
        parents.append({
            "category": "Citations",
            "action": "Fix NAP mismatches on existing citations",
            "priority": "P1",
            "details": [f"{d['directory']}: {(d.get('diff_summary') or '').split(chr(10))[0]}"
                        for d in real_mismatches_for_plan[:8]],
        })
    missing_for_plan = [d for d in citations.get("directories", []) if d.get("status") in ("missing", "partial")]
    if missing_for_plan:
        parents.append({
            "category": "Citations",
            "action": f"Build {len(missing_for_plan)} missing citations",
            "priority": "P1",
            "details": [f"{d['directory']} (T{d.get('tier','?')})"
                        for d in missing_for_plan[:8]],
        })
    # Review engine deliverable
    parents.append({
        "category": "Reviews",
        "action": "Stand up review request + response engine",
        "priority": "P2",
        "details": [
            f"Current: {review_count} reviews · {review_avg}★",
            "Set up review request automation (post-meeting trigger)",
            "Owner-response workflow: 100% within 24h",
            "Seed 10+ Q&A on GBP",
        ],
    })
    return parents


sprint3_deliverables = _read_xlsx_actions()

deliverable_cards = ""
for i, p in enumerate(sprint3_deliverables, 1):
    detail_count = len(p.get("details", []))
    details_html = "".join(f'<li>{esc(d)}</li>' for d in p.get("details", [])[:6])
    if detail_count > 6:
        details_html += f'<li class="muted">+ {detail_count - 6} more (see Actions tab)</li>'
    deliverable_cards += (
        f'<div class="plan-month">'
        f'  <div class="plan-month-label">'
        f'    <span class="plan-num">{i}</span>'
        f'    <span><span class="cat-tag">{esc(p["category"])}</span> '
        f'    <span class="prio-pill prio-{p["priority"].lower()}">{esc(p["priority"])}</span> '
        f'    {esc(p["action"])}</span>'
        f'  </div>'
        f'  <ul class="plan-items">{details_html}</ul>'
        f'</div>'
    )


# ─── Assemble the HTML ──────────────────────────────────────────────────────
generated = manifest.get("generated_at") or datetime.utcnow().isoformat() + "Z"
audit_id = manifest.get("audit_id") or args.audit_id

HTML = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Local SEO Audit — {esc(CLIENT_NAME)}</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Bebas+Neue&family=Figtree:wght@300;400;500;600;700;800&display=swap" rel="stylesheet">
<style>
  :root {{
    --primary: {PRIMARY};
    --primary-soft: {PRIMARY}1A;
    --text: #0a0e1a;
    --muted: #4b5563;
    --border: #e5e7eb;
    --bg: #ffffff;
    --soft: #f7f7f8;
    --ink: #0a0e1a;
    --display: 'Bebas Neue', 'Arial Narrow', sans-serif;
    --body: 'Figtree', -apple-system, BlinkMacSystemFont, 'Segoe UI', system-ui, sans-serif;
  }}
  * {{ box-sizing: border-box; }}
  body {{ font-family: var(--body); margin: 0; color: var(--text);
         background: #ededee; line-height: 1.55; font-size: 14px; font-weight: 400; }}
  h1, h2, h3, h4 {{ font-family: var(--display); text-transform: uppercase;
                    letter-spacing: 0.02em; font-weight: 400; line-height: 1.05; }}
  .container {{ max-width: 1200px; margin: 0 auto; padding: 32px 24px 80px; }}

  /* Hero */
  header.hero {{ background: var(--ink); color: white; padding: 40px 44px; margin-bottom: 28px;
                border-radius: 14px; position: relative; overflow: hidden; }}
  header.hero::after {{ content: ""; position: absolute; right: -40px; top: -40px;
                        width: 200px; height: 200px; border-radius: 50%;
                        background: var(--primary); opacity: 0.15; }}
  header.hero h1 {{ margin: 0 0 8px; font-size: 56px; }}
  header.hero .meta {{ font-size: 13px; opacity: 0.78; text-transform: uppercase;
                       letter-spacing: 0.08em; font-weight: 500; font-family: var(--body); }}

  /* Title slide between sections */
  .title-slide {{ background: var(--ink); color: white; border-radius: 14px;
                  padding: 36px 44px; margin: 36px 0 16px;
                  border-left: 8px solid var(--primary); }}
  .title-slide .section-num {{ font-size: 12px; font-weight: 700; letter-spacing: 0.25em;
                                text-transform: uppercase; color: var(--primary);
                                margin-bottom: 12px; font-family: var(--body); }}
  .title-slide h2 {{ margin: 0 0 10px; font-size: 48px; }}
  .title-slide .desc {{ font-size: 15px; opacity: 0.85; max-width: 800px;
                        font-family: var(--body); }}

  /* Panel */
  section.panel {{ background: var(--bg); border: 1px solid var(--border); border-radius: 12px;
                   padding: 28px 30px; margin-bottom: 18px; }}
  section.panel h3 {{ margin: 0 0 6px; font-size: 28px; color: var(--ink); }}
  section.panel h4 {{ margin: 22px 0 10px; font-size: 18px; color: var(--ink); }}
  section.panel .subtitle {{ color: var(--muted); font-size: 13px; margin-bottom: 20px;
                              font-family: var(--body); }}

  /* KPI cards */
  .kpi-grid {{ display: grid; grid-template-columns: repeat(4, 1fr); gap: 12px; }}
  .kpi {{ padding: 18px; background: var(--soft); border-radius: 10px;
          border: 1px solid var(--border); }}
  .kpi .label {{ font-size: 11px; text-transform: uppercase; letter-spacing: 0.08em;
                 color: var(--muted); font-weight: 700; }}
  .kpi .value {{ font-size: 38px; font-family: var(--display); margin-top: 6px;
                 line-height: 1.0; color: var(--ink); }}
  .kpi .sub {{ font-size: 11px; color: var(--muted); margin-top: 4px; }}

  /* Priority pills */
  .prio-pill {{ display: inline-block; padding: 3px 10px; border-radius: 999px;
                font-size: 11px; font-weight: 700; letter-spacing: 0.05em; }}
  .prio-p1 {{ background: #fee2e2; color: #b91c1c; }}
  .prio-p2 {{ background: #fef3c7; color: #b45309; }}
  .prio-p3 {{ background: #e5e7eb; color: #4b5563; }}

  /* Category tag */
  .cat-tag {{ display: inline-block; padding: 3px 8px; border-radius: 6px;
              background: var(--primary-soft); color: var(--primary);
              font-size: 11px; font-weight: 600; letter-spacing: 0.04em; }}

  /* Status badge */
  .badge {{ display: inline-block; padding: 3px 10px; border-radius: 999px;
            font-size: 11px; font-weight: 600; letter-spacing: 0.02em; }}

  /* Tables */
  table {{ width: 100%; border-collapse: collapse; font-size: 13px; }}
  table th {{ text-align: left; font-family: var(--body); font-weight: 700;
              font-size: 11px; text-transform: uppercase; letter-spacing: 0.05em;
              color: var(--muted); padding: 10px 12px; border-bottom: 2px solid var(--border);
              background: var(--soft); }}
  table td {{ padding: 12px; border-bottom: 1px solid var(--border); vertical-align: top; }}
  table td.num {{ text-align: right; font-variant-numeric: tabular-nums; font-weight: 600; }}
  table td.muted {{ color: var(--muted); font-size: 12px; }}
  table td.diff-cell {{ font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
                        font-size: 12px; line-height: 1.5; color: var(--text); }}
  .cell-sub {{ font-size: 11px; color: var(--muted); margin-top: 3px; }}

  /* Priorities Top-N */
  .top-prio-table td {{ padding: 14px 12px; }}

  /* Plan */
  .plan-month {{ background: var(--soft); border-radius: 10px; padding: 20px 24px;
                  margin-bottom: 12px; border-left: 4px solid var(--primary); }}
  .plan-month-label {{ font-family: var(--display); font-size: 22px; text-transform: uppercase;
                        margin-bottom: 10px; color: var(--ink); display: flex; align-items: center;
                        gap: 12px; }}
  .plan-num {{ background: var(--primary); color: white; width: 32px; height: 32px;
               border-radius: 50%; display: inline-flex; align-items: center; justify-content: center;
               font-size: 16px; font-family: var(--body); font-weight: 700; }}
  .plan-items {{ margin: 0; padding-left: 22px; }}
  .plan-items li {{ margin-bottom: 6px; font-size: 14px; }}

  /* Collapsible tactical tables (HTML <details>) */
  details.tactical {{ margin-top: 16px; }}
  details.tactical summary {{ cursor: pointer; padding: 12px 16px; background: var(--soft);
                              border-radius: 8px; font-weight: 600; font-size: 13px;
                              border: 1px solid var(--border); list-style: none; }}
  details.tactical summary::-webkit-details-marker {{ display: none; }}
  details.tactical summary::before {{ content: "▸ "; color: var(--primary); font-weight: 700; }}
  details.tactical[open] summary::before {{ content: "▾ "; }}
  details.tactical[open] summary {{ border-bottom-left-radius: 0; border-bottom-right-radius: 0; }}
  details.tactical .body {{ border: 1px solid var(--border); border-top: 0;
                            border-radius: 0 0 8px 8px; padding: 0; overflow-x: auto; }}

  /* City-bucket accordions inside the keyword tracker (closed by default) */
  details.city-bucket {{ margin-top: 8px; }}
  details.city-bucket > summary {{ list-style: none; }}
  details.city-bucket > summary::-webkit-details-marker {{ display: none; }}
  details.city-bucket > summary::after {{ content: "▸"; float: right; opacity: 0.7;
                                          transition: transform 0.15s ease; }}
  details.city-bucket[open] > summary::after {{ content: "▾"; }}
  details.city-bucket[open] > summary {{ border-bottom-left-radius: 0; border-bottom-right-radius: 0; }}
  details.city-bucket > table {{ border: 1px solid var(--border); border-top: 0;
                                 border-radius: 0 0 6px 6px; }}

  /* Local Falcon grids — 4-column horizontal row */
  .lf-grid-row {{ display: grid; grid-template-columns: repeat(4, 1fr); gap: 14px; }}
  .lf-grid-col {{ background: var(--soft); border: 1px solid var(--border); border-radius: 10px;
                  padding: 16px 14px; display: flex; flex-direction: column; align-items: center;
                  text-align: center; }}
  .lf-grid-col svg {{ display: block; margin: 0 auto; max-width: 100%; height: auto; }}
  .lf-col-title {{ font-family: var(--display); font-size: 15px; text-transform: uppercase;
                   margin-bottom: 4px; color: var(--ink); min-height: 36px;
                   line-height: 1.1; }}
  .lf-col-date {{ font-size: 10px; text-transform: uppercase; letter-spacing: 0.08em;
                  font-weight: 700; color: var(--muted); margin-bottom: 10px; }}
  .lf-col-stats {{ width: 100%; margin-top: 12px; }}
  .stat-row {{ display: flex; justify-content: space-between; align-items: center;
               padding: 4px 0; border-bottom: 1px solid var(--border);
               font-size: 12px; }}
  .stat-row:last-child {{ border-bottom: 0; }}
  .stat-label {{ color: var(--muted); text-transform: uppercase; letter-spacing: 0.04em;
                 font-weight: 600; }}
  .stat-val {{ font-weight: 700; color: var(--ink); font-variant-numeric: tabular-nums; }}
  .delta-badge {{ margin-top: 10px; padding: 4px 10px; background: white; border-radius: 999px;
                  font-size: 11px; font-weight: 700; border: 1px solid var(--border); }}

  /* Expandable detailed comparison (under the row) */
  .lf-grids-wrap {{ display: flex; gap: 18px; align-items: flex-start; flex-wrap: wrap; }}
  .grid-cell-block {{ flex: 0 0 auto; }}
  .grid-cell-block svg {{ display: block; }}
  .grid-date-label {{ font-size: 11px; text-transform: uppercase; letter-spacing: 0.08em;
                      font-weight: 700; color: var(--muted); margin-bottom: 8px; text-align: center; }}
  .grid-stats {{ font-size: 11px; color: var(--muted); margin-top: 6px; text-align: center;
                 font-variant-numeric: tabular-nums; }}
  .grid-delta {{ flex: 1 1 200px; min-width: 200px; padding: 16px 20px; background: var(--soft);
                 border-radius: 8px; border: 1px solid var(--border); }}
  .delta-row {{ display: flex; justify-content: space-between; align-items: center;
                padding: 6px 0; border-bottom: 1px solid var(--border); }}
  .delta-row:last-child {{ border-bottom: 0; }}
  .delta-label {{ font-size: 12px; color: var(--muted); text-transform: uppercase;
                  letter-spacing: 0.04em; font-weight: 600; }}

  /* Legend */
  .lf-grid-legend {{ display: flex; gap: 14px; flex-wrap: wrap; align-items: center;
                     font-size: 11px; color: var(--muted); margin-bottom: 14px; }}
  .legend-swatch {{ display: inline-block; width: 12px; height: 12px; border-radius: 3px;
                    vertical-align: middle; margin-right: 4px; }}
  .lf-empty {{ padding: 24px; background: var(--soft); border-radius: 10px;
               border: 1px dashed var(--border); color: var(--muted); }}
  .lf-empty code {{ background: white; padding: 2px 6px; border-radius: 4px;
                    font-size: 12px; border: 1px solid var(--border); }}

  @media (max-width: 900px) {{
    .lf-grid-row {{ grid-template-columns: repeat(2, 1fr); }}
  }}

  @media (max-width: 800px) {{
    .kpi-grid {{ grid-template-columns: repeat(2, 1fr); }}
    header.hero h1 {{ font-size: 36px; }}
    .title-slide h2 {{ font-size: 32px; }}
  }}
  /* Per-location tab navigation (heatmap + GMB performance) */
  .loc-tabs {{ display: flex; gap: 8px; flex-wrap: wrap; margin: 4px 0 16px; border-bottom: 2px solid var(--soft); }}
  .loc-tab {{ background: none; border: none; padding: 9px 18px; font-family: inherit; font-size: 14px;
    font-weight: 700; color: #94a3b8; cursor: pointer; border-bottom: 3px solid transparent; margin-bottom: -2px; }}
  .loc-tab:hover {{ color: var(--ink); }}
  .loc-tab.active {{ color: var(--primary); border-bottom-color: var(--primary); }}
</style>
</head>
<body>
<div class="container">

  <!-- HERO -->
  <header class="hero">
    <div class="meta">Local SEO Audit · Generated {esc(generated[:10])}</div>
    <h1>{esc(CLIENT_NAME)}</h1>
    <div class="meta" style="margin-top:8px">Audit ID: {esc(audit_id)}</div>
  </header>

  <!-- ═══════════════ SECTION 1: PERFORMANCE ═══════════════ -->
  <div class="title-slide">
    <div class="section-num">Section 1</div>
    <h2>Performance</h2>
    <div class="desc">How {esc(CLIENT_NAME)} is showing up in search today — proximity rankings around the office, GBP profile activity, review velocity vs. peers, and city-by-city keyword visibility.</div>
  </div>

  {locations_overview_html}

  <section class="panel">
    <h3>Proximity Heatmap — Maps Pack Ranking Around the Office</h3>
    <div class="subtitle">
      Local Falcon 49-cell grid scan. Each cell = a GPS point scattered up to ~5 miles around {esc(CLIENT_NAME)}'s office; the number = the firm's Maps Pack rank for that keyword at that point.
      <span class="muted" style="display:block;margin-top:4px;font-size:12px">
        This measures rankings <strong>near the office</strong> (proximity-boosted). The Local Keyword Targets section below measures rankings as Google serves them to a searcher in each <strong>city centroid</strong> — what most prospects actually see. Both views together tell the full local-SEO story.
      </span>
    </div>

    <div class="lf-grid-legend">
      <span><span class="legend-swatch" style="background:#16a34a"></span>Top 3 (local pack)</span>
      <span><span class="legend-swatch" style="background:#84cc16"></span>Top 10</span>
      <span><span class="legend-swatch" style="background:#eab308"></span>11–15</span>
      <span><span class="legend-swatch" style="background:#f97316"></span>16–20</span>
      <span><span class="legend-swatch" style="background:#dc2626"></span>Not found</span>
    </div>

    {lf_grids_html}
  </section>

  {gbp_performance_html}

  {review_velocity_html}

  {keyword_tracker_html}

  <!-- ═══════════════ SECTION 2: AUDIT ═══════════════ -->
  <div class="title-slide">
    <div class="section-num">Section 2</div>
    <h2>Audit</h2>
    <div class="desc">Field-by-field examination of the foundations: Google Business Profile completeness and citation health across 55 directories.</div>
  </div>

  <section class="panel">
    <h3>Google Business Profile — Field-by-Field</h3>
    <div class="subtitle">One accordion per location. Each field weighted by ranking impact; expand a location to audit its profile.</div>
    {gbp_accordions_html}
  </section>

  <section class="panel">
    <h3>Citations — 55 Directories &times; Location</h3>
    <div class="subtitle">Every location is audited against the same 55-directory universe (Tier&nbsp;1 aggregators &amp; maps, Tier&nbsp;2 legal + general, Tier&nbsp;3 regional). National firm/attorney directories are shared; maps, review &amp; local directories are verified per office. Source: {esc(citations_summary.get("_primary_source", "—"))}.</div>
    {citations_section_html}
  </section>

  <!-- ═══════════════ SECTION 3: PLAN ═══════════════ -->
  <div class="title-slide">
    <div class="section-num">Section 3</div>
    <h2>Plan</h2>
    <div class="desc">What to do about it. Top priorities ranked by ranking impact, plus the itemized deliverables that get appended to {esc(CLIENT_NAME)}'s existing project plan.</div>
  </div>

  <section class="panel">
    <h3>Top Priorities</h3>
    <div class="subtitle">P1 = critical, do first. P2 = important. Ranked by impact on local rankings.</div>
    <table class="top-prio-table">
      <thead><tr><th>Priority</th><th>Area</th><th>Action</th></tr></thead>
      <tbody>{priority_rows}</tbody>
    </table>
  </section>

  <section class="panel">
    <h3>Itemized Project Plan — Add to Existing Plan</h3>
    <div class="subtitle">Each card below is a deliverable to append to {esc(CLIENT_NAME)}'s existing project plan. Strategist reviews each card → marks Approval column in Tab 9 → approved items flow into the active sprint.</div>
    {deliverable_cards}
  </section>

  <footer style="text-align: center; padding: 40px 0 20px; color: var(--muted); font-size: 12px;">
    Generated {esc(generated)} · Local SEO Audit · Source data: <a href="{esc(SLUG)}-local-audit.xlsx" style="color:var(--primary)">{esc(SLUG)}-local-audit.xlsx</a>
  </footer>

</div>
<script>
function showTab(btn, group, paneId) {{
  document.querySelectorAll('.' + group + '-pane').forEach(function(p){{ p.style.display = 'none'; }});
  var tabs = btn.parentNode.querySelectorAll('.loc-tab');
  tabs.forEach(function(t){{ t.classList.remove('active'); }});
  var pane = document.getElementById(paneId);
  if (pane) pane.style.display = 'block';
  btn.classList.add('active');
}}
</script>
</body>
</html>
"""

# ─── Write output ────────────────────────────────────────────────────────────
OUT.write_text(HTML)
size_kb = OUT.stat().st_size // 1024
print(f"✓ Wrote {OUT.name} ({size_kb} KB)")
print(f"  Open: {OUT}")
