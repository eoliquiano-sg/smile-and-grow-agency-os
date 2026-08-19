#!/usr/bin/env python3
"""
build_local_audit_data.py — Local SEO Audit data orchestrator.

Companion to WQA's data flow. Reads raw MCP outputs cached to disk by Claude
during the /agency-os-delivery-local-seo-audit skill run, normalizes them into
clean cache files that build_local_audit_xlsx.py + build_local_audit_report.py
consume.

Raw input layout (Claude writes these via MCP calls during the skill). Files MUST
live under raw/ (not the audit root) — this script only looks in raw/. Each row
below is the exact filename this script expects, and the MCP tool call whose
output it holds; recognized aliases (legacy/vendor-prefixed names) are in
brackets and are accepted interchangeably via load_raw_any():
  clients/{slug}/local-audit/{audit_id}/raw/
    ├── local-falcon-scans.json       localfalcon_scan_report, aggregated  [alias: local-falcon-grid.json]
    ├── local-falcon-competitors.json localfalcon_competitors, top 5 per scan
    ├── local-falcon-trend.json       localfalcon_trend, 12-week trend for primary keyword
    ├── gbp-profile.json              dataforseo_business_data OR live listing (browser)  [alias: dataforseo-business-data.json]
    ├── gbp-reviews.json              dataforseo_reviews OR live listing (browser)  [alias: dataforseo-reviews.json]
    ├── gsc-local-queries.json        windsor_query, local-intent queries (current + prior)
    ├── keyword-rankings.json         local_keyword_track_batch (Maps + organic + AI Overview ranks)
    ├── citations-checks.json         citation_scan output  [alias: citations.json]
    ├── ahrefs-refdomains-client.json ahrefs_backlinks_raw, client's referring domains  [aliases: ahrefs-local-links.json, ahrefs-backlinks-raw.json]
    ├── ahrefs-refdomains-comp1.json  ahrefs_backlinks_raw, competitor 1's referring domains
    ├── ahrefs-refdomains-comp2.json  ahrefs_backlinks_raw, competitor 2
    └── ahrefs-refdomains-comp3.json  ahrefs_backlinks_raw, competitor 3

  Not yet consumed by this normalizer (ahrefs_keywords_overview /
  ahrefs_keywords_raw output for the xlsx's Keyword Performance tab) — saving
  these under raw/ is harmless but they have no normalize step here yet.

  IMPORTANT — do not confuse this raw/ layout with clients/{slug}/local-audit/
  {audit_id}/audit-manifest.json one level up: that file is owned exclusively
  by the localseo_create_audit / localseo_update_config MCP tools (checkpoint
  state, locations, keywords, competitors, provider flags). This script never
  reads or writes it — see "data-coverage.json" below.

Clean output layout (this script writes):
  clients/{slug}/local-audit/{audit_id}/
    ├── local-falcon-grid.json        Normalized 250-cell rankings matrix
    ├── gbp-profile.json              Validated + scored field-by-field
    ├── gsc-local-queries.json        Aggregated by query, period-over-period
    ├── citations.json                50 rows with status + NAP diff + priority
    ├── local-links.json              Per-domain client vs competitor matrix
    ├── local-pages.json              Site crawl filtered to local pages
    └── data-coverage.json            Counts, freshness, source coverage scores —
                                       NOT audit-manifest.json (that file belongs to
                                       the MCP tools; overwriting it destroys
                                       checkpoint/location/keyword state — see above)

CLI:
  python build_local_audit_data.py \\
    --client-slug batch-williams \\
    --audit-id b4a66be6-3f40-4b02-87ae-ebcef08ec0b5 \\
    --workspace-root /path/to/workspace
"""

import argparse
import json
import os
import re
import sys
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

parser = argparse.ArgumentParser(description="Normalize Local SEO Audit raw data into clean cache files.")
parser.add_argument("--client-slug", required=True, help="Client folder slug (e.g. batch-williams)")
parser.add_argument("--audit-id", required=True, help="Audit UUID (matches the WQA audit_id pattern)")
parser.add_argument("--workspace-root", default=os.getcwd(),
                    help="Workspace root containing clients/ directory (default: cwd)")
parser.add_argument("--strict", action="store_true",
                    help="Fail if any raw input is missing. Default: tolerate missing sources with warnings.")
args = parser.parse_args()

ROOT = Path(args.workspace_root)
AUDIT_DIR = ROOT / "clients" / args.client_slug / "local-audit" / args.audit_id
RAW = AUDIT_DIR / "raw"

if not RAW.is_dir():
    sys.exit(f"ERROR: raw input dir not found: {RAW}\n  Did Claude run the data-pull phase yet?")

# Filenames THIS script itself writes as clean output (see write_clean() calls
# in main()) — and therefore must NEVER be treated as a misplaced raw-root
# fallback candidate (see _find_raw_path). Without this exclusion, re-running
# the normalize step a second time (e.g. after a re-pull) would find its own
# previous clean output sitting at the audit root and silently feed it back in
# as if it were a fresh raw pull. "audit-manifest.json" is excluded too, even
# though this script doesn't write it — it's the MCP tools' file, never a raw
# input under any name this script looks for.
_CLEAN_OUTPUT_NAMES = {
    "local-falcon-grid.json", "gbp-profile.json", "gsc-local-queries.json",
    "citations.json", "local-links.json", "local-pages.json",
    "ai-geo-findings.json", "locations.json", "data-coverage.json",
    "audit-manifest.json",
}

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

WARNINGS: list[str] = []


def _find_raw_path(name: str) -> Path | None:
    """Resolve `name` to an actual file path, tolerating the #1 real-world
    mistake: Claude saves an MCP pull at the audit root instead of raw/.
    Checks raw/ first (correct location); falls back to the audit root — but
    NEVER for a name in _CLEAN_OUTPUT_NAMES, so this can't match this script's
    own (or a previous run's) clean output — with a warning, so a genuinely
    misplaced pull still gets picked up instead of silently producing an empty
    normalize run."""
    p = RAW / name
    if p.exists():
        return p
    if name in _CLEAN_OUTPUT_NAMES:
        return None
    p_root = AUDIT_DIR / name
    if p_root.exists():
        WARNINGS.append(
            f"{name} was found at the audit root, not raw/ — using it anyway, "
            f"but future pulls should be saved under raw/{name}"
        )
        return p_root
    return None


def load_raw(name: str) -> Any:
    """Load a raw JSON file. Returns None if missing (unless --strict)."""
    p = _find_raw_path(name)
    if p is None:
        msg = f"missing: raw/{name}"
        if args.strict:
            sys.exit(f"ERROR (strict mode): {msg}")
        WARNINGS.append(msg)
        return None
    try:
        return json.loads(p.read_text())
    except json.JSONDecodeError as e:
        sys.exit(f"ERROR: raw/{name} is not valid JSON: {e}")


def load_raw_any(*names: str) -> Any:
    """Load the first raw JSON file in `names` that exists.

    The SKILL.md spec uses vendor-agnostic filenames (gbp-profile.json,
    ahrefs-local-links.json, citations.json, local-falcon-grid.json) while
    this script historically reads vendor-prefixed names. This helper accepts
    both — try the spec name first (what users actually save), then fall back
    to legacy names — without re-warning on each miss.
    """
    for n in names:
        p = _find_raw_path(n)
        if p is not None:
            try:
                return json.loads(p.read_text())
            except json.JSONDecodeError as e:
                sys.exit(f"ERROR: raw/{n} is not valid JSON: {e}")
    if args.strict:
        sys.exit(f"ERROR (strict mode): missing all of: raw/{', raw/'.join(names)}")
    WARNINGS.append(f"missing: raw/{names[0]} (and {len(names)-1} alternates)")
    return None


def _unwrap_dfs_envelope(d: Any) -> Any:
    """If `d` is wrapped in our `{items_count, items: [...]}` envelope (what
    `dataforseo_business_data` MCP returns) OR the raw DfS `{tasks: [...]}`
    shape, drill into the actual business-item dict. Otherwise return as-is."""
    if not isinstance(d, dict):
        return d
    if "tasks" in d:
        try:
            items = (d["tasks"][0].get("result") or [])[0].get("items") or []
        except (KeyError, IndexError, TypeError):
            return d
        return items[0] if items else d
    if "items" in d and isinstance(d.get("items"), list) and d["items"]:
        return d["items"][0]
    return d


def write_clean(name: str, payload: Any) -> None:
    p = AUDIT_DIR / name
    p.write_text(json.dumps(payload, indent=2, default=str))
    print(f"  wrote {name}  ({p.stat().st_size:,} bytes)")


def now() -> str:
    return datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")


# ---------------------------------------------------------------------------
# Citation directory universe — loaded from the agency's own sheet (vertical-
# agnostic), NOT hardcoded. Falls back to the bundled legal sheet with a
# warning. See citation_directory_loader.py.
# ---------------------------------------------------------------------------
sys.path.insert(0, str(Path(__file__).resolve().parent))
try:
    from citation_directory_loader import resolve_directories as _resolve_dirs
except Exception:  # pragma: no cover - loader optional
    _resolve_dirs = None


def load_citation_universe() -> tuple[dict, dict]:
    """Resolve the directory universe from the agency citation sheet.

    Search order: client audit folder → client folder → workspace root →
    connected-folder root (workspace parent). Falls back to the bundled legal
    sheet (with warning) when none is found.
    """
    if _resolve_dirs is None:
        return dict(DIRECTORY_LIST), {"total": len(DIRECTORY_LIST), "is_fallback": False,
                                      "source_name": "built-in DIRECTORY_LIST"}
    search = [
        AUDIT_DIR,
        ROOT / "clients" / args.client_slug,
        ROOT,
        ROOT.parent,
    ]
    dirs, meta = _resolve_dirs(search, allow_fallback=True)
    if not dirs:  # absolute last resort
        return dict(DIRECTORY_LIST), {"total": len(DIRECTORY_LIST), "is_fallback": False,
                                      "source_name": "built-in DIRECTORY_LIST"}
    return dirs, meta


# Map the DfS citation_scan per-row status onto the audit's citation status.
_SCAN_STATUS = {
    "found_correct": "live_correct",
    "found_mismatch": "live_mismatch",
    "found_unverified": "live",
    "missing": "missing",
}


_ADDR_ABBR = {
    "ave": "avenue", "av": "avenue", "st": "street", "str": "street", "rd": "road",
    "blvd": "boulevard", "ct": "court", "dr": "drive", "ln": "lane", "hwy": "highway",
    "pkwy": "parkway", "ste": "suite", "ofc": "office", "fl": "floor", "rm": "room",
    "n": "north", "s": "south", "e": "east", "w": "west",
}
# Walled-garden / aggregator platforms whose listings are NOT indexed by Google,
# so a site: SERP query can never confirm them. These must never be reported
# "missing" off a SERP scan — they need the platform's own API or a manual check.
SERP_BLIND_DOMAINS = {
    "maps.apple.com", "apple.com", "bingplaces.com", "bing.com", "foursquare.com",
    "data-axle.com", "localeze.com", "neustarlocaleze.biz", "infogroup.com",
}
SERP_BLIND_NAMES = {
    "apple maps", "bing places", "foursquare", "data axle", "neustar/localeze", "infogroup",
}
_PHONE_RE = re.compile(r"\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}")
_ADDR_RE = re.compile(r"\d{2,6}\s+[A-Za-z].*?\b(?:ave|avenue|st|street|rd|road|blvd|boulevard|ct|court|dr|drive|ln|lane|hwy|highway|pkwy|parkway|way|place|pl|cir|circle)\b", re.I)


def _addr_core(addr: str):
    """Return (street_number, set_of_normalized_street_name_tokens) — the parts
    that actually identify an address, ignoring unit/suite, punctuation, and
    abbreviation/format differences (Ave vs Avenue, comma/space, Ste #17)."""
    s = (addr or "").lower()
    s = re.sub(r"\b(?:suite|ste|unit|apt|#)\s*\.?\s*\w+", " ", s)  # drop unit designators
    s = re.sub(r"[^a-z0-9\s]", " ", s)
    toks = [t for t in s.split() if t]
    num = ""
    names = set()
    for t in toks:
        if t.isdigit() and not num:
            num = t  # first number = street number
            continue
        if t.isdigit():
            continue  # zip/other numbers ignored for the name set
        if t in ("avenue", "ave", "street", "st", "road", "rd", "blvd", "boulevard",
                 "court", "ct", "drive", "dr", "lane", "ln", "highway", "hwy",
                 "parkway", "pkwy", "suite", "ste", "ky", "kentucky", "us", "united", "states"):
            continue
        names.add(_ADDR_ABBR.get(t, t))
    return num, names


def grade_nap_from_snippet(snippet: str, canon_phone: str, canon_address: str) -> dict:
    """Grade a citation's NAP from its SERP snippet. Tri-state per field
    (match / conflict / absent) + a severity ranking that treats a genuinely
    DIFFERENT street address as the worst issue, a different phone next, and
    pure formatting differences as NOT a mismatch.

    Returns: {status, phone_match, address_match, severity, issue, detail}
      status   ∈ live_correct | live_mismatch | live (found, ungradable)
      severity ∈ address | phone | minor | none
    """
    hay = snippet or ""
    low = hay.lower()

    # ---- phone ----
    canon10 = re.sub(r"\D", "", canon_phone or "")[-10:]
    found_phones = {re.sub(r"\D", "", p)[-10:] for p in _PHONE_RE.findall(hay)}
    if not found_phones:
        phone_match = None
    elif canon10 and canon10 in found_phones:
        phone_match = True
    else:
        phone_match = False  # a phone is shown, but not the canonical one

    # ---- address ----
    cnum, cnames = _addr_core(canon_address)
    addr_present = bool(_ADDR_RE.search(hay))
    if not (cnum or cnames):
        address_match = None
    elif cnum and cnum in re.findall(r"\d{2,6}", hay) and any(n in low for n in cnames):
        address_match = True   # canonical street number + street name both present (format-agnostic)
    elif addr_present:
        # a real street address is shown but it isn't the canonical one
        address_match = False
    else:
        address_match = None   # no address visible in snippet → can't grade

    # ---- verdict + severity ----
    if address_match is False:
        return {"status": "live_mismatch", "phone_match": phone_match, "address_match": False,
                "severity": "address", "issue": "wrong_address",
                "detail": "Listing shows a DIFFERENT street address than canonical."}
    if phone_match is False:
        return {"status": "live_mismatch", "phone_match": False, "address_match": address_match,
                "severity": "phone", "issue": "wrong_phone",
                "detail": "Listing shows a different phone number than canonical."}
    if address_match is True or phone_match is True:
        return {"status": "live_correct", "phone_match": phone_match, "address_match": address_match,
                "severity": "none", "issue": "",
                "detail": "NAP matches canonical (formatting differences ignored)."}
    return {"status": "live", "phone_match": None, "address_match": None,
            "severity": "none", "issue": "",
            "detail": "Listing live; NAP not visible in snippet — confirm manually."}


def _refdomains_set(rd: dict) -> set:
    """Flatten an Ahrefs referring-domains payload into a lowercased domain set."""
    out = set()
    if not isinstance(rd, dict):
        return out
    for x in rd.get("referring_domains", []) or rd.get("refdomains", []) or []:
        if isinstance(x, str):
            out.add(x.lower())
        elif isinstance(x, dict):
            dom = x.get("domain") or x.get("refdomain") or x.get("referring_domain")
            if dom:
                out.add(str(dom).lower())
    return out


def _citations_from_scan(scan: dict, universe: dict, canonical: dict, refdomains: set | None = None) -> dict:
    """Build the per-location citations.json from citation_scan output + the
    directory universe. SERP detection is primary; Ahrefs referring domains are
    a FAILSAFE that confirms listings the SERP scan couldn't surface.
    """
    refdomains = refdomains or set()
    def _action(status, prio, submit, severity=""):
        tag = {"address": "P1·ADDRESS", "phone": "P1·PHONE"}.get(severity, prio)
        if status == "missing":
            return f"[{prio}] Submit/claim listing" + (f" — {submit}" if submit else "")
        if status == "live_mismatch":
            return f"[{tag}] Fix NAP / dedupe" + (f" — {submit}" if submit else "")
        if status == "unverified":
            return f"[{prio}] Verify listing + NAP"
        return ""

    # Distinctive name token for the precision gate (e.g. "O'Bryan Law Offices" -> "obryan")
    _bn = (scan.get("business_name") or canonical.get("name") or "").lower().split()
    biz_key = re.sub(r"[^a-z0-9]", "", _bn[0]) if _bn else ""

    locations_out = []
    for loc in scan.get("locations", []):
        scan_by_name = {}
        for r in loc.get("directories", []):
            scan_by_name[(r.get("directory") or "").strip().lower()] = r
        loc_nap = {**canonical, **(loc.get("nap") or {})}
        rows = []
        for name, meta in universe.items():
            r = scan_by_name.get(name.strip().lower(), {})
            severity = "none"
            _dom = (meta.get("domain") or "").lower()
            _bad_dom = (not _dom) or ("." not in _dom) or (" " in _dom)
            if _dom in SERP_BLIND_DOMAINS or name.strip().lower() in SERP_BLIND_NAMES:
                # SERP can't see walled-garden platforms — never call these missing.
                status, note = "needs_manual", (
                    "Walled-garden platform — not indexed by Google, so the SERP scan can't "
                    "detect it. Verify on the platform directly (e.g. Apple Business Connect) "
                    "or via its own API.")
            elif _bad_dom:
                # No resolvable domain in the citation sheet (e.g. "search by individual state").
                status, note = "needs_manual", (
                    "No resolvable domain in the citation list — can't auto-scan. Needs a "
                    "manual / per-state lookup (e.g. the state bar directory).")
            elif not r:
                status, note = "unverified", "Not scanned."
            elif r.get("found") is None:
                status, note = "unverified", (r.get("error") or "Scan error.")
            elif r.get("found") is False:
                status, note = "missing", "No listing found via SERP."
            else:
                # Precision gate: a site: query can surface OTHER businesses on the
                # same directory. Only trust the result if the business name actually
                # appears in the title/snippet — otherwise the firm isn't listed there.
                _txt = re.sub(r"[^a-z0-9]", "", ((r.get("title") or "") + " " + (r.get("snippet") or "")).lower())
                if biz_key and biz_key not in _txt:
                    status, note = "missing", "No matching listing — a different business ranked for this directory."
                else:
                    # Found + confirmed name → grade NAP (format-agnostic, severity-ranked)
                    g = grade_nap_from_snippet(r.get("snippet", ""), loc_nap.get("phone", ""), loc_nap.get("address", ""))
                    status, severity, note = g["status"], g["severity"], g["detail"]
            # FAILSAFE: if SERP couldn't confirm it but Ahrefs shows a backlink from
            # this directory's domain, the listing exists — upgrade to live.
            if status in ("missing", "needs_manual", "unverified") and _dom and any(
                    _dom == rd or _dom.endswith("." + rd) or rd.endswith("." + _dom) for rd in refdomains):
                status, severity = "live", "none"
                note = "Confirmed live via Ahrefs backlink (SERP couldn't surface it). NAP not graded — confirm manually."
            rows.append({
                "directory": name,
                "tier": meta.get("tier"),
                "priority": meta.get("priority", "P2"),
                "directory_type": meta.get("directory_type", "firm"),
                "category": meta.get("category"),
                "status": status,
                "severity": severity,           # address | phone | minor | none
                "url": r.get("url") or meta.get("url"),
                "diff_summary": note,
                "snippet": r.get("snippet", ""),
                "submission_link": meta.get("submission_link"),
                "tf": meta.get("tf"),
                "traffic": meta.get("traffic"),
                "action": _action(status, meta.get("priority", "P2"), meta.get("submission_link"), severity),
            })
        from collections import Counter
        c = Counter(x["status"] for x in rows)
        lc, lm, lv = c.get("live_correct", 0), c.get("live_mismatch", 0), c.get("live", 0)
        miss, unv = c.get("missing", 0), c.get("unverified", 0)
        needs_manual = c.get("needs_manual", 0)
        addr_bad = sum(1 for x in rows if x.get("severity") == "address")
        phone_bad = sum(1 for x in rows if x.get("severity") == "phone")
        tot = len(rows)
        # Sort: critical issues first (wrong address → wrong phone → other mismatch →
        # missing → live → unverified), then by directory priority, then tier.
        _sev_rank = {"address": 0, "phone": 1}
        _stat_rank = {"live_mismatch": 0, "missing": 1, "live_correct": 2, "live": 2, "unverified": 3}
        rows.sort(key=lambda x: (_stat_rank.get(x["status"], 4),
                                 _sev_rank.get(x.get("severity"), 2),
                                 {"P1": 0, "P2": 1, "P3": 2}.get(x.get("priority"), 3),
                                 x.get("tier", 9)))
        locations_out.append({
            "slug": re.sub(r"[^a-z0-9]+", "-", (loc.get("location") or "loc").lower()).strip("-"),
            "name": loc.get("location"),
            "nap": {**canonical, **(loc.get("nap") or {})},
            "directories": rows,
            "summary": {"total": tot, "live": lv, "live_correct": lc, "live_mismatch": lm,
                        "address_mismatches": addr_bad, "phone_mismatches": phone_bad,
                        "missing": miss, "unverified": unv, "needs_manual": needs_manual,
                        "coverage_pct": round(100 * (lc + lm + lv) / tot, 1) if tot else 0},
        })
    primary = locations_out[0] if locations_out else {"directories": [], "summary": {}}
    return {
        "canonical_nap": canonical,
        "scope": "per_location",
        "locations": locations_out,
        "directories": primary["directories"],  # back-compat (primary location)
        "summary": {**primary.get("summary", {}),
                    "_primary_source": "DataForSEO organic SERP citation scan (per location)"},
    }


# ===========================================================================
# 1. LOCAL FALCON GRID — normalize 250-cell rankings matrix
# ===========================================================================

def normalize_local_falcon() -> dict:
    """Pivot raw Local Falcon scans into a per-keyword × per-cell rankings grid.

    Output shape:
      {
        "config":    { "grid_size": "5x5", "radius_miles": 2.0, "center": {...} },
        "keywords":  ["miami injury lawyer", ...],
        "grid":      { keyword: { "0,0": {pos, found}, "0,1": {...}, ... } },
        "summary":   { keyword: { avg_rank, found_count, top_3_count, top_10_count } },
        "competitors": { keyword: [{domain, avg_rank, appearances}, ...] },
        "trend":     { keyword: [{week, avg_rank}, ...] }      // 12-week
      }
    """
    raw_scans = load_raw_any("local-falcon-scans.json", "local-falcon-grid.json")
    raw_comps = load_raw("local-falcon-competitors.json") or {}
    raw_trend = load_raw("local-falcon-trend.json") or {}

    if not raw_scans:
        return {"_skipped": True, "reason": "no raw local-falcon-scans.json"}

    # Honor explicit api-not-connected sentinel
    if raw_scans.get("_api_status", "").startswith("NOT_CONNECTED"):
        return {
            "_skipped": True,
            "_api_status": raw_scans["_api_status"],
            "reason": "Local Falcon API not connected — apply MCP patches and re-run",
            "config": raw_scans.get("config", {}),
        }

    # Local Falcon returns scans as a list of { keyword, grid_cell, rank, ...}
    # We pivot into { keyword: { "row,col": {pos, found} } }
    grid_by_kw: dict[str, dict[str, dict]] = defaultdict(dict)
    for entry in raw_scans.get("scans", []):
        kw = entry["keyword"]
        cell = f"{entry['row']},{entry['col']}"
        rank = entry.get("rank")
        grid_by_kw[kw][cell] = {
            "pos": rank,                     # null if not in top 20
            "found": rank is not None and rank <= 20,
            "lat": entry.get("lat"),
            "lng": entry.get("lng"),
        }

    # Per-keyword summary — prefer report-level metadata (truth) over reconstructing
    # from partial cells. The Local Falcon report response includes found_in /
    # data_points / arp / solv as authoritative values; the per-cell grid is for
    # the heatmap. When per-cell parse is partial (e.g. due to WebFetch size cap),
    # the cell-based numbers are wrong but the report-level ones stay correct.
    reports_by_kw: dict[str, dict] = {}
    for r in raw_scans.get("reports", []):
        kw = r.get("keyword", "")
        # If same keyword appears in multiple reports, prefer the MOST RECENT
        # (last in the list — caller orders newest-last)
        if kw and kw not in reports_by_kw:
            reports_by_kw[kw] = r

    # Iterate every keyword we have evidence for — both ones with per-cell scans
    # and ones we only have report metadata for (which is the common case when the
    # caller doesn't pull the full grid).
    summary: dict[str, dict] = {}
    all_keywords = set(grid_by_kw.keys()) | set(reports_by_kw.keys())
    for kw in all_keywords:
        report = reports_by_kw.get(kw, {})
        # Authoritative numbers from the LF API report metadata.
        # LF returns `solv_percent` from list_reports and `solv` from trend reports
        # — accept either. `grid_size` is e.g. "7" → 49 cells.
        try:
            grid_dim = int(str(report.get("grid_size", "7")).split("x")[0])
            expected_default = grid_dim * grid_dim
        except (ValueError, TypeError):
            expected_default = 49
        found_in = int(report.get("found_in") or 0)
        # LF raw scan reports expose `data_points` as the total cell count;
        # legacy reports used `expected_cells`. Use whichever is present.
        expected = int(report.get("expected_cells") or report.get("data_points") or expected_default)
        arp = report.get("arp")
        solv = report.get("solv_percent")
        if solv is None:
            solv = report.get("solv")

        # Fallback to cell-derived numbers ONLY if we don't have report-level data
        cells = grid_by_kw[kw] if kw in grid_by_kw else {}
        ranks_observed = [c["pos"] for c in cells.values() if c["pos"] is not None]

        # If found_in isn't reported, infer from SoLV (solv > 0 means client appeared
        # in the pack at least once; precise cell count is unknown without per-cell data).
        if not found_in and solv is not None and float(solv) > 0:
            found_in = max(1, round(float(solv) / 100.0 * expected))

        summary[kw] = {
            "avg_rank":     float(arp) if arp is not None else (
                round(sum(ranks_observed) / len(ranks_observed), 2) if ranks_observed else None
            ),
            "found_count":  found_in or sum(1 for c in cells.values() if c["found"]),
            "total_cells":  expected,
            "top_3_count":  sum(1 for c in cells.values() if c["pos"] is not None and c["pos"] <= 3),
            "top_10_count": sum(1 for c in cells.values() if c["pos"] is not None and c["pos"] <= 10),
            "coverage_pct": round(100 * found_in / expected, 1) if expected else 0,
            "solv_pct":     float(solv) if solv is not None else None,
            "_source":      "Local Falcon API report metadata" if report else "computed from partial cells",
        }

    # Top competitors per keyword. Source priority:
    #   1. local-falcon-competitors.json (richest — has avg_rank + appearances per cell)
    #   2. keyword-rankings.json `top_3_competitors` (DfS Local Finder — narrower scope)
    competitors_by_kw: dict[str, list[dict]] = {}
    if isinstance(raw_comps, dict) and not raw_comps.get("_api_status"):
        for kw, comps in raw_comps.items():
            if not isinstance(comps, list):
                continue
            # comps is list of { domain, gbp_id, appearances, avg_rank }
            ranked = sorted(comps, key=lambda c: (c.get("avg_rank") or 99, -c.get("appearances", 0)))[:5]
            competitors_by_kw[kw] = ranked

    # Fallback: derive from DfS keyword-rankings top_3_competitors when LF didn't supply
    # per-keyword competitor data.
    if not competitors_by_kw:
        rankings = load_raw("keyword-rankings.json")
        if isinstance(rankings, dict):
            for r in rankings.get("results", []):
                kw = r.get("keyword")
                top3 = r.get("top_3_competitors") or []
                if not kw or not top3:
                    continue
                competitors_by_kw[kw] = [
                    {
                        "domain":     c.get("domain"),
                        "name":       c.get("name"),
                        "place_id":   c.get("place_id"),  # usually absent
                        "rating":     c.get("rating"),
                        "reviews":    c.get("reviews"),
                        "appearances": 1,                  # one appearance per top_3 entry
                        "avg_rank":   c.get("rank"),
                        "_source":    "DfS Local Finder top_3",
                    }
                    for c in top3
                ]

    # Per-(office × keyword) breakdown — preserves EVERY scan so a multi-location
    # client shows ALL offices, not one collapsed row per keyword. Built from the
    # raw `reports` list (each carries `office`), which is why report-dedup-by-keyword
    # above must NOT be the only view of the data.
    by_office: list[dict] = []
    for r in raw_scans.get("reports", []):
        kw = r.get("keyword", "")
        try:
            gd = int(str(r.get("grid_size", "7")).split("x")[0])
            exp = gd * gd
        except (ValueError, TypeError):
            exp = 49
        solv = r.get("solv_percent")
        if solv is None:
            solv = r.get("solv")
        found = int(r.get("found_in") or 0)
        if not found and solv is not None and float(solv) > 0:
            found = max(1, round(float(solv) / 100.0 * exp))
        by_office.append({
            "office":       r.get("office"),
            "keyword":      kw,
            "solv_pct":     float(solv) if solv is not None else None,
            "avg_rank":     float(r["arp"]) if r.get("arp") is not None else None,
            "found_count":  found,
            "total_cells":  exp,
            "coverage_pct": round(100 * found / exp, 1) if exp else 0,
            "grid_size":    r.get("grid_size"),
            "report_key":   r.get("report_key"),
        })

    return {
        "config": raw_scans.get("config", {"grid_size": "5x5"}),
        "keywords": list(set(grid_by_kw.keys()) | set(reports_by_kw.keys())),
        "grid": dict(grid_by_kw),
        "summary": summary,
        "by_office": by_office,
        "offices": raw_scans.get("offices", []),
        "competitors": competitors_by_kw,
        "trend": raw_trend,
        "pulled_at": raw_scans.get("pulled_at", now()),
    }


# ===========================================================================
# 2. GBP PROFILE — validate + score field-by-field
# ===========================================================================

GBP_REQUIRED_FIELDS = {
    "primary_category":        {"weight": 10, "rationale": "Primary category is the #1 GBP ranking signal."},
    "secondary_categories":    {"weight": 5,  "rationale": "Additional relevant categories expand keyword coverage."},
    "business_description":    {"weight": 6,  "rationale": "750-char description, keyword-rich, fact-dense."},
    "services":                {"weight": 8,  "rationale": "Service list maps to GBP query matching."},
    # Note: 'products' field intentionally omitted — DfS Business Data API does not expose
    # GBP Products. Reading them requires GBP OAuth (out of scope for current audit).
    "photos_count":            {"weight": 5,  "rationale": "Minimum 10 photos (logo, exterior, interior, team, work)."},
    "attributes":              {"weight": 3,  "rationale": "Wheelchair access, free WiFi, etc."},
    "hours":                   {"weight": 4,  "rationale": "Must match website + signage exactly."},
    "service_area":            {"weight": 3,  "rationale": "Required for service-area businesses."},
    "phone":                   {"weight": 5,  "rationale": "Local area code preferred. Must match NAP."},
    "website":                 {"weight": 5,  "rationale": "Should point to location-specific page if multi-location."},
    "posts_last_90d":          {"weight": 4,  "rationale": "Weekly cadence preferred. Boosts engagement signals."},
    "qa_count":                {"weight": 2,  "rationale": "Seeded Q&A reduces friction + improves CTR."},
    "review_count":            {"weight": 8,  "rationale": "Volume relative to competitors."},
    "review_avg":              {"weight": 6,  "rationale": "≥4.5 is competitive in most verticals."},
    "review_response_rate":    {"weight": 5,  "rationale": "100% response is the bar. Boosts trust signals."},
}


def _normalize_dfs_business_data(dfs: dict) -> dict:
    """Map DataForSEO Business Data (Google) response into our gbp-profile shape.

    DfS response example shape (tasks[0].result[0]):
      {
        "title": "Acme Law Group, PC",
        "category": "Family law attorney",
        "additional_categories": [...],
        "description": "...",
        "address": "...", "phone": "...", "url": "...",
        "rating": {"rating_type": "Max5", "value": 4.5, "votes_count": 90},
        "photos_count": 24,
        "questions_count": 3,
        "local_business_links": [...],
        "attributes": {...},
        "work_hours": {...},
        "place_id": "...",
        "snippet": "...",
        "additional_information": {...},
      }
    """
    # DfS returns service items as a list of dicts: [{"category":..., "title":...}, ...]
    services_raw = dfs.get("services") or []
    if isinstance(services_raw, list):
        services = [s.get("title") for s in services_raw if isinstance(s, dict) and s.get("title")]
    else:
        services = []

    # Attributes are nested: {available_attributes: {category: [items]}, unavailable_attributes: ...}
    attr_root = dfs.get("attributes") or {}
    available = attr_root.get("available_attributes") if isinstance(attr_root, dict) else None
    if isinstance(available, dict):
        attributes = []
        for cat, items in available.items():
            if isinstance(items, list):
                attributes.extend(items)
    else:
        attributes = list(attr_root.keys()) if isinstance(attr_root, dict) else []

    # Hours: DfS nests the per-day timetable at work_time.work_hours.timetable,
    # but older payloads expose work_time.timetable or work_time.actual_working_hours
    # directly. Accept all three.
    work_time = dfs.get("work_time") or {}
    work_hours = work_time.get("work_hours") or {}
    hours = (
        work_hours.get("timetable")
        or work_time.get("actual_working_hours")
        or work_time.get("timetable")
        or {}
    )
    hours_summary = ""
    if isinstance(hours, dict) and hours:
        DAYS = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
        ABBR = {"monday": "Mon", "tuesday": "Tue", "wednesday": "Wed", "thursday": "Thu",
                "friday": "Fri", "saturday": "Sat", "sunday": "Sun"}
        parts = []
        for d in DAYS:
            entries = hours.get(d)
            if not entries:
                parts.append(f"{ABBR[d]}: closed")
                continue
            ranges = []
            for e in entries if isinstance(entries, list) else [entries]:
                if not isinstance(e, dict):
                    continue
                o, c = e.get("open") or {}, e.get("close") or {}
                if isinstance(o, dict) and isinstance(c, dict):
                    ranges.append(f"{o.get('hour', 0):02d}:{o.get('minute', 0):02d}-{c.get('hour', 0):02d}:{c.get('minute', 0):02d}")
            parts.append(f"{ABBR[d]}: {', '.join(ranges) if ranges else 'closed'}")
        hours_summary = " | ".join(parts)

    return {
        "name":                 dfs.get("title"),
        "address":              dfs.get("address"),
        "place_id":             dfs.get("place_id"),
        "hours_summary":        hours_summary,
        "primary_category":     dfs.get("category"),
        "secondary_categories": dfs.get("additional_categories", []) or [],
        "business_description": dfs.get("description") or (dfs.get("snippet") or ""),
        "services":             services,
        # 'products' intentionally not extracted — DfS Business Data API doesn't expose
        # GBP Products. See GBP_REQUIRED_FIELDS comment for context.
        "photos_count":         dfs.get("total_photos") or 0,           # DfS key is total_photos
        "attributes":           attributes,
        "hours":                hours,
        "phone":                dfs.get("phone"),
        "website":              dfs.get("url"),
        "service_area":         dfs.get("local_business_links") or [],
        "posts_last_90d":       0,    # DfS doesn't expose posts directly
        "qa_count":             dfs.get("questions_and_answers_count") or 0,  # DfS key is _and_answers_
        "review_count":         (dfs.get("rating") or {}).get("votes_count") or 0,
        "review_avg":           (dfs.get("rating") or {}).get("value") or 0,
        "review_response_rate": None,  # populate from dataforseo-reviews.json
        "_dfs_pulled_at":       dfs.get("_pulled_at"),
    }


def _enrich_from_dfs_reviews(profile: dict, dfs_reviews: dict) -> dict:
    """Compute review response rate from DfS reviews data."""
    reviews = dfs_reviews.get("reviews", []) if isinstance(dfs_reviews, dict) else []
    if not reviews:
        return profile
    with_response = sum(1 for r in reviews if r.get("owner_response") or r.get("response_text"))
    profile["review_response_rate"] = round(100 * with_response / len(reviews), 1)
    # Optionally also recompute posts cadence from DfS local-posts if exposed
    return profile


def normalize_gbp() -> dict:
    # Source priority: DataForSEO > manual gbp-profile.json > nothing.
    # Both filenames are accepted because SKILL.md tells users to save as
    # `gbp-profile.json` (vendor-agnostic) while the legacy script convention
    # was `dataforseo-business-data.json`. Either works.
    dfs_bd = load_raw_any("dataforseo-business-data.json", "gbp-profile.json")
    dfs_rv = load_raw_any("dataforseo-reviews.json", "gbp-reviews.json")
    # `raw` is the optional manual override layer — only load if it's a separate
    # file from what we already have above.
    raw = load_raw("gbp-profile.json") if dfs_bd is not None and "items" in dfs_bd else None

    # If DfS data available, use as primary
    if dfs_bd and isinstance(dfs_bd, dict) and not dfs_bd.get("_unavailable"):
        # Handle every envelope shape: raw DfS API ({tasks: [...]}), our MCP
        # wrapper ({items_count, items: [...]}), or a pre-extracted item dict.
        dfs_data = _unwrap_dfs_envelope(dfs_bd)
        # If the wrapper held multiple items, prefer the canonical place_id match
        if isinstance(dfs_bd, dict) and isinstance(dfs_bd.get("items"), list) and len(dfs_bd["items"]) > 1:
            place_id = CANONICAL_NAP.get("place_id") if "CANONICAL_NAP" in globals() else None
            if place_id:
                match = next((x for x in dfs_bd["items"] if x.get("place_id") == place_id), None)
                if match:
                    dfs_data = match

        dfs_profile = _normalize_dfs_business_data(dfs_data)
        if dfs_rv:
            dfs_profile = _enrich_from_dfs_reviews(dfs_profile, dfs_rv)

        # Merge with fallback gbp-profile.json: DfS wins, fallback fills gaps.
        # IMPORTANT: don't overwrite DfS 0 with manual "api_pending" sentinel —
        # 0 from DfS is a real answer (e.g. 0 Q&A, 0 photos). Only fill when DfS is None/empty.
        if raw:
            for k, v in raw.items():
                if k.startswith("_"):
                    continue
                dfs_val = dfs_profile.get(k)
                # Only fall back when DfS gave us literally nothing AND fallback isn't the api_pending sentinel
                if dfs_val in (None, "", []) and v != "api_pending":
                    dfs_profile[k] = v

        # Add Windsor performance data passthrough
        if raw and raw.get("windsor_performance_90d"):
            dfs_profile["windsor_performance_90d"] = raw["windsor_performance_90d"]

        raw = dfs_profile
        raw["_primary_source"] = "DataForSEO Business Data API"
    elif raw:
        raw = dict(raw)
        raw["_primary_source"] = "manual gbp-profile.json (fallback — DfS not configured)"
    else:
        return {"_skipped": True, "reason": "no GBP data available — neither DataForSEO nor manual entry"}

    fields: list[dict] = []
    total_weight = 0
    total_score = 0

    for field, meta in GBP_REQUIRED_FIELDS.items():
        value = raw.get(field)
        weight = meta["weight"]
        # api_pending sentinel — field couldn't be pulled because GBP API isn't connected yet
        if value == "api_pending":
            score = 0.0  # don't credit toward grade
            status = "api_pending"
        # Score 0-1 based on presence + adequacy
        elif value is None or value == "" or value == 0 or value == []:
            score = 0.0
            status = "missing"
        elif field == "business_description" and isinstance(value, str):
            score = min(1.0, len(value) / 750.0)
            status = "ok" if score >= 0.85 else "weak"
        elif field == "photos_count" and isinstance(value, int):
            score = min(1.0, value / 10.0)
            status = "ok" if value >= 10 else "weak"
        elif field == "review_count" and isinstance(value, int):
            score = min(1.0, value / 100.0)
            status = "ok" if value >= 50 else "weak"
        elif field == "review_avg" and isinstance(value, (int, float)):
            score = min(1.0, max(0.0, (value - 3.5) / 1.5))  # 3.5→0, 5.0→1
            status = "ok" if value >= 4.5 else "weak"
        elif field == "review_response_rate" and isinstance(value, (int, float)):
            score = min(1.0, value / 100.0)
            status = "ok" if value >= 95 else "weak"
        elif field == "posts_last_90d" and isinstance(value, int):
            score = min(1.0, value / 12.0)  # ~weekly = 12 in 90d
            status = "ok" if value >= 12 else "weak"
        elif field == "secondary_categories" and isinstance(value, list):
            score = min(1.0, len(value) / 3.0)
            status = "ok" if len(value) >= 3 else "weak"
        elif field == "services" and isinstance(value, list):
            score = min(1.0, len(value) / 5.0)
            status = "ok" if len(value) >= 5 else "weak"
        else:
            score = 1.0
            status = "ok"

        total_weight += weight
        total_score += weight * score
        fields.append({
            "field": field,
            "current": value,
            "status": status,
            "score": round(score, 2),
            "weight": weight,
            "rationale": meta["rationale"],
            "action": _gbp_action(field, status, value),
        })

    grade_pct = round(100 * total_score / max(1, total_weight), 1)
    return {
        "fields": fields,
        "grade_pct": grade_pct,
        "letter_grade": _letter_grade(grade_pct),
        # Top-level NAP — surfaced for the xlsx NAP Consistency tab. These aren't
        # graded fields (the GBP grade is about content depth, not NAP) but the
        # NAP tab cross-checks them against on-site + citation sources.
        "name":           raw.get("name"),
        "address":        raw.get("address"),
        "phone":          raw.get("phone"),
        "website":        raw.get("website"),
        "hours_summary":  raw.get("hours_summary"),
        "place_id":       raw.get("place_id"),
        "windsor_performance_90d": raw.get("windsor_performance_90d"),
        "data_sources": raw.get("_data_sources"),
        "_primary_source": raw.get("_primary_source"),
        "pulled_at": raw.get("pulled_at", now()),
    }


def _gbp_action(field: str, status: str, value) -> str:
    """Suggested action for a GBP field gap."""
    if status == "ok":
        return ""
    if status == "api_pending":
        return "Pull live value via dataforseo_business_data or the live Google listing (browser)"
    actions = {
        "primary_category":     "Set primary category to match the client's main practice area",
        "secondary_categories": "Add 2-3 additional relevant categories",
        "business_description": "Write a 750-char keyword-rich description with NAP at the bottom",
        "services":             "Add 5+ services covering each practice area",
        "photos_count":         "Upload at least 10 photos (logo, exterior, interior, team, practice areas)",
        "attributes":           "Set all applicable attributes (parking, accessibility, etc.)",
        "hours":                "Set business hours to match website + signage",
        "service_area":         "Define service area for SAB or service-radius businesses",
        "phone":                "Set local-area-code primary number; must match NAP",
        "website":              "Set canonical website URL; multi-location: point to location-specific page",
        "posts_last_90d":       "Set up weekly GBP Posts cadence (auto-pull from blog/YouTube uploads)",
        "qa_count":             "Seed 5-10 Q&A entries for common queries",
        "review_count":         "Set up NPS funnel + drip sequence to drive review velocity",
        "review_avg":           "Improve service or filter requests via NPS gate (≥4 stars only to public)",
        "review_response_rate": "Set up response automation; aim for 100% response within 48h",
    }
    return actions.get(field, "")


# ===========================================================================
# 3. GSC LOCAL QUERIES — aggregate by query, period-over-period
# ===========================================================================

def normalize_gsc_local() -> dict:
    raw = load_raw("gsc-local-queries.json")
    if not raw:
        return {"_skipped": True, "reason": "no raw gsc-local-queries.json"}

    current = raw.get("current", [])
    prior = raw.get("prior", [])

    # Each is a list of { query, clicks, impressions, ctr, position }
    by_query_current = {r["query"]: r for r in current}
    by_query_prior = {r["query"]: r for r in prior}

    rows = []
    all_queries = set(by_query_current) | set(by_query_prior)
    for q in all_queries:
        c = by_query_current.get(q, {})
        p = by_query_prior.get(q, {})
        rows.append({
            "query": q,
            "clicks_current": c.get("clicks", 0),
            "clicks_prior":   p.get("clicks", 0),
            "clicks_delta":   c.get("clicks", 0) - p.get("clicks", 0),
            "impr_current":   c.get("impressions", 0),
            "impr_prior":     p.get("impressions", 0),
            "ctr_current":    round(c.get("ctr", 0) * 100, 2) if c.get("ctr") else 0,
            "pos_current":    round(c.get("position", 0), 1) if c.get("position") else None,
            "pos_prior":      round(p.get("position", 0), 1) if p.get("position") else None,
        })

    # Sort by clicks_current desc
    rows.sort(key=lambda r: -r["clicks_current"])

    return {
        "period_current": raw.get("period_current"),
        "period_prior":   raw.get("period_prior"),
        "rows": rows,
        "totals": {
            "clicks_current": sum(r["clicks_current"] for r in rows),
            "clicks_prior":   sum(r["clicks_prior"] for r in rows),
            "impr_current":   sum(r["impr_current"] for r in rows),
            "impr_prior":     sum(r["impr_prior"] for r in rows),
        },
        "pulled_at": raw.get("pulled_at", now()),
    }


# ===========================================================================
# 4. CITATIONS — 50-directory audit (replaces WhiteSpark)
# ===========================================================================

# The 50-directory list is the audit's source of truth. Tier 1 = primary
# aggregators that downstream-feed Apple/Bing/GPS. Tier 2 = vertical-specific
# (legal in this case but easily configurable). Tier 3 = local/regional.
DIRECTORY_LIST = {
    # ───── Tier 1: Data aggregators (feed everything downstream) ─────
    "Data Axle":          {"tier": 1, "url": "https://www.data-axle.com", "priority": "P1", "directory_type": "firm"},
    "Neustar/Localeze":   {"tier": 1, "url": "https://localeze.com",      "priority": "P1", "directory_type": "firm"},
    "Foursquare":         {"tier": 1, "url": "https://foursquare.com",    "priority": "P1", "directory_type": "firm"},
    "Infogroup":          {"tier": 1, "url": "https://infogroup.com",     "priority": "P1", "directory_type": "firm"},
    # ───── Tier 1: Search engines + maps ─────
    "Google Business Profile": {"tier": 1, "url": "https://business.google.com", "priority": "P1", "directory_type": "firm"},
    "Apple Maps":         {"tier": 1, "url": "https://mapsconnect.apple.com",    "priority": "P1", "directory_type": "firm"},
    "Bing Places":        {"tier": 1, "url": "https://www.bingplaces.com",       "priority": "P1", "directory_type": "firm"},
    # ───── Tier 2: Legal-specific — split firm-level vs attorney-level ─────
    # Attorney-level directories DON'T have firm profiles. You create individual
    # attorney profiles. The audit check is "do all named attorneys have profiles."
    "Avvo":               {"tier": 2, "url": "https://www.avvo.com",          "vertical": "legal", "priority": "P1", "directory_type": "attorney"},
    "Justia":             {"tier": 2, "url": "https://www.justia.com",        "vertical": "legal", "priority": "P1", "directory_type": "attorney"},
    "Nolo":               {"tier": 2, "url": "https://www.nolo.com",          "vertical": "legal", "priority": "P2", "directory_type": "attorney"},
    "HG.org":             {"tier": 2, "url": "https://www.hg.org",            "vertical": "legal", "priority": "P3", "directory_type": "attorney"},
    "Lawyer.com":         {"tier": 2, "url": "https://www.lawyer.com",        "vertical": "legal", "priority": "P3", "directory_type": "attorney"},
    "BestLawyers":        {"tier": 2, "url": "https://www.bestlawyers.com",   "vertical": "legal", "priority": "P3", "directory_type": "attorney"},
    # Firm-level legal directories — firm profile is the right unit.
    "FindLaw":            {"tier": 2, "url": "https://www.findlaw.com",       "vertical": "legal", "priority": "P1", "directory_type": "firm"},
    "Super Lawyers":      {"tier": 2, "url": "https://www.superlawyers.com",  "vertical": "legal", "priority": "P1", "directory_type": "firm"},
    "Martindale-Hubbell": {"tier": 2, "url": "https://www.martindale.com",    "vertical": "legal", "priority": "P2", "directory_type": "firm"},
    "Lawyers.com":        {"tier": 2, "url": "https://www.lawyers.com",       "vertical": "legal", "priority": "P2", "directory_type": "firm"},
    # ───── Tier 2: General business directories (always relevant) ─────
    "Yelp":               {"tier": 2, "url": "https://www.yelp.com",          "priority": "P1", "directory_type": "firm"},
    "BBB":                {"tier": 2, "url": "https://www.bbb.org",           "priority": "P1", "directory_type": "firm"},
    "Yellow Pages":       {"tier": 2, "url": "https://www.yellowpages.com",   "priority": "P2", "directory_type": "firm"},
    "MapQuest":           {"tier": 2, "url": "https://www.mapquest.com",      "priority": "P2", "directory_type": "firm"},
    "Manta":              {"tier": 2, "url": "https://www.manta.com",         "priority": "P3", "directory_type": "firm"},
    "Hotfrog":            {"tier": 2, "url": "https://www.hotfrog.com",       "priority": "P3", "directory_type": "firm"},
    "Brownbook":          {"tier": 2, "url": "https://www.brownbook.net",     "priority": "P3", "directory_type": "firm"},
    "Cylex":              {"tier": 2, "url": "https://www.cylex.us.com",      "priority": "P3", "directory_type": "firm"},
    "EZLocal":            {"tier": 2, "url": "https://www.ezlocal.com",       "priority": "P3", "directory_type": "firm"},
    "Expertise.com":      {"tier": 2, "url": "https://www.expertise.com",     "priority": "P2", "directory_type": "firm"},
    # ───── Tier 2: Social + review-anchored ─────
    "Facebook":           {"tier": 2, "url": "https://www.facebook.com",      "priority": "P1"},
    "LinkedIn Company":   {"tier": 2, "url": "https://www.linkedin.com",      "priority": "P2"},
    "Instagram Business": {"tier": 2, "url": "https://www.instagram.com",     "priority": "P3"},
    "Twitter/X Business": {"tier": 2, "url": "https://x.com",                 "priority": "P3"},
    # ───── Tier 3: Local / regional ─────
    "Chamber of Commerce":     {"tier": 3, "url": "lookup",                   "priority": "P1"},
    "City Business Directory": {"tier": 3, "url": "lookup",                   "priority": "P2"},
    "Local Chamber Member List":{"tier": 3, "url": "lookup",                  "priority": "P2"},
    "Patch.com":               {"tier": 3, "url": "https://patch.com",        "priority": "P3"},
    "Local.com":               {"tier": 3, "url": "https://www.local.com",    "priority": "P3"},
    "MerchantCircle":          {"tier": 3, "url": "https://www.merchantcircle.com", "priority": "P3"},
    "CitySearch":              {"tier": 3, "url": "https://www.citysearch.com",     "priority": "P3"},
    "Insider Pages":           {"tier": 3, "url": "https://www.insiderpages.com",   "priority": "P3"},
    "Kudzu":                   {"tier": 3, "url": "https://www.kudzu.com",          "priority": "P3"},
    "Switchboard":             {"tier": 3, "url": "https://www.switchboard.com",    "priority": "P3"},
    "Whitepages":              {"tier": 3, "url": "https://www.whitepages.com",     "priority": "P3"},
    "411.com":                 {"tier": 3, "url": "https://www.411.com",            "priority": "P3"},
    "DexKnows":                {"tier": 3, "url": "https://www.dexknows.com",       "priority": "P3"},
    "AngiesList":              {"tier": 3, "url": "https://www.angi.com",           "priority": "P3"},
    "Trustpilot":              {"tier": 3, "url": "https://www.trustpilot.com",     "priority": "P3"},
    "Google Maps":             {"tier": 1, "url": "https://www.google.com/maps",    "priority": "P1"},
    "Waze":                    {"tier": 3, "url": "https://www.waze.com",           "priority": "P3"},
    "TomTom":                  {"tier": 3, "url": "https://www.tomtom.com",         "priority": "P3"},
    "HERE Maps":               {"tier": 3, "url": "https://www.here.com",           "priority": "P3"},
    "GuideStar":               {"tier": 3, "url": "https://www.guidestar.org",      "priority": "P3"},
    "ZoomInfo":                {"tier": 3, "url": "https://www.zoominfo.com",       "priority": "P3", "directory_type": "firm"},
    # ───── Bonus citations surfaced during verification ─────
    "Birdeye":                 {"tier": 2, "url": "https://www.birdeye.com",        "priority": "P2", "directory_type": "firm"},
    "LawInfo":                 {"tier": 2, "url": "https://www.lawinfo.com",        "vertical": "legal", "priority": "P2", "directory_type": "firm"},
    "FindGlocal":              {"tier": 3, "url": "https://www.findglocal.com",     "priority": "P3", "directory_type": "firm"},
}


def _merge_dfs_citations(directory_results: dict, dfs_listings: dict, canonical: dict) -> dict:
    """Merge DataForSEO Business Listings Search results into the per-directory checks.

    DfS response shape: { listings: [{ source: 'yelp', url: '...', title: '...', address: '...',
    phone: '...', verified: bool, found_at: '...' }, ...] }

    For each listing in DfS, try to match it to a directory in DIRECTORY_LIST by domain.
    Listings matched to known directories OVERRIDE the web-search 'found' status.
    Listings on unknown sources are added as bonus entries.
    """
    listings = dfs_listings.get("listings", []) if isinstance(dfs_listings, dict) else []
    if not listings:
        return directory_results

    # Map well-known domain fragments to directory keys
    DOMAIN_TO_DIR = {
        "yelp.com": "Yelp", "bbb.org": "BBB", "yellowpages.com": "Yellow Pages",
        "facebook.com": "Facebook", "linkedin.com": "LinkedIn Company",
        "instagram.com": "Instagram Business", "twitter.com": "Twitter/X Business",
        "x.com": "Twitter/X Business", "google.com/maps": "Google Maps",
        "business.google.com": "Google Business Profile",
        "mapsconnect.apple.com": "Apple Maps", "bingplaces.com": "Bing Places",
        "foursquare.com": "Foursquare", "mapquest.com": "MapQuest",
        "avvo.com": "Avvo", "justia.com": "Justia", "findlaw.com": "FindLaw",
        "superlawyers.com": "Super Lawyers", "martindale.com": "Martindale-Hubbell",
        "lawyers.com": "Lawyers.com", "nolo.com": "Nolo", "hg.org": "HG.org",
        "lawyer.com": "Lawyer.com", "bestlawyers.com": "BestLawyers",
        "manta.com": "Manta", "hotfrog.com": "Hotfrog", "brownbook.net": "Brownbook",
        "cylex.us.com": "Cylex", "ezlocal.com": "EZLocal", "expertise.com": "Expertise.com",
        "chamberofcommerce.com": "Chamber of Commerce", "patch.com": "Patch.com",
        "local.com": "Local.com", "merchantcircle.com": "MerchantCircle",
        "citysearch.com": "CitySearch", "insiderpages.com": "Insider Pages",
        "kudzu.com": "Kudzu", "switchboard.com": "Switchboard",
        "whitepages.com": "Whitepages", "411.com": "411.com", "dexknows.com": "DexKnows",
        "angi.com": "AngiesList", "trustpilot.com": "Trustpilot", "waze.com": "Waze",
        "data-axle.com": "Data Axle", "localeze.com": "Neustar/Localeze",
        "infogroup.com": "Infogroup", "guidestar.org": "GuideStar", "zoominfo.com": "ZoomInfo",
        "birdeye.com": "Birdeye", "lawinfo.com": "LawInfo", "findglocal.com": "FindGlocal",
    }

    merged = dict(directory_results)
    for listing in listings:
        url = (listing.get("url") or "").lower()
        if not url:
            continue
        # Find which directory this URL belongs to
        matched_dir = None
        for domain_frag, dir_name in DOMAIN_TO_DIR.items():
            if domain_frag in url:
                matched_dir = dir_name
                break
        if not matched_dir:
            continue  # Skip listings on directories not in our list

        # Override our previous check with DfS truth
        merged[matched_dir] = {
            "found": True,
            "url": listing.get("url"),
            "nap": {
                "name":    listing.get("title") or listing.get("name"),
                "address": listing.get("address"),
                "phone":   listing.get("phone"),
                "website": listing.get("website") or listing.get("domain"),
            },
            "_source": "DataForSEO Business Listings Search",
            "_verified_at": listing.get("found_at") or listing.get("crawled_at"),
        }

    return merged


def _merge_dfs_backlinks(directory_results: dict, dfs_backlinks: dict, ahrefs_refdomains: dict = None) -> dict:
    """Cross-reference referring-domains data against DIRECTORY_LIST.

    Any directory whose domain shows up as a referring domain → confirmed live citation.
    This is the most reliable citation signal we have: if directory.com links to
    client.com, the citation exists. No WebSearch needed.

    Accepts data from either source (Ahrefs has better coverage; DfS is fallback):
    - Ahrefs: {refdomains: [{domain, domain_rating, links_to_target, ...}, ...]}
    - DfS:    tasks[0].result[0].items[N] = {domain, rank, backlinks, ...}
    """
    items = []
    # Prefer Ahrefs if present (much better coverage for small/local domains)
    if ahrefs_refdomains and isinstance(ahrefs_refdomains, dict):
        items = (
            ahrefs_refdomains.get("refdomains")
            or ahrefs_refdomains.get("domains")
            or []
        )
        # Spec filename `ahrefs-local-links.json` returns full backlinks
        # (`{backlinks: [{source_url, ...}]}`) instead of pre-aggregated
        # refdomains. Project per-link `source_url` → host so the merge
        # below can match against DIR_TO_DOMAIN.
        if not items and isinstance(ahrefs_refdomains.get("backlinks"), list):
            from urllib.parse import urlparse
            seen: set[str] = set()
            for bl in ahrefs_refdomains["backlinks"]:
                url = bl.get("source_url") or bl.get("url_from") or ""
                try:
                    host = urlparse(url).hostname or ""
                except Exception:
                    host = ""
                host = host.lower().lstrip(".")
                if host and host not in seen:
                    seen.add(host)
                    items.append({
                        "domain": host,
                        "domain_rating": bl.get("source_dr") or bl.get("domain_rating_source"),
                        "links_to_target": 1,
                    })
        signal_source = "Ahrefs site-explorer-referring-domains"
    elif dfs_backlinks and isinstance(dfs_backlinks, dict):
        try:
            items = dfs_backlinks["tasks"][0]["result"][0].get("items") or []
            signal_source = "DataForSEO referring_domains"
        except (KeyError, IndexError, TypeError):
            items = []
            signal_source = ""
    if not items:
        return directory_results

    # Build a set of referring domains for fast lookup
    referring_domains = {(it.get("domain") or "").lower() for it in items if it.get("domain")}

    # Map each directory name to its primary domain (subset of DOMAIN_TO_DIR above)
    DIR_TO_DOMAIN = {
        "Yelp": "yelp.com", "BBB": "bbb.org", "Yellow Pages": "yellowpages.com",
        "Facebook": "facebook.com", "LinkedIn Company": "linkedin.com",
        "Instagram Business": "instagram.com", "Twitter/X Business": "x.com",
        "Apple Maps": "apple.com", "Bing Places": "bing.com",
        "Foursquare": "foursquare.com", "MapQuest": "mapquest.com",
        "Avvo": "avvo.com", "Justia": "justia.com", "FindLaw": "findlaw.com",
        "Super Lawyers": "superlawyers.com", "Martindale-Hubbell": "martindale.com",
        "Lawyers.com": "lawyers.com", "Nolo": "nolo.com", "HG.org": "hg.org",
        "Lawyer.com": "lawyer.com", "BestLawyers": "bestlawyers.com",
        "Manta": "manta.com", "Hotfrog": "hotfrog.com", "Brownbook": "brownbook.net",
        "Cylex": "cylex.us.com", "EZLocal": "ezlocal.com", "Expertise.com": "expertise.com",
        "Chamber of Commerce": "chamberofcommerce.com", "Patch.com": "patch.com",
        "Local.com": "local.com", "MerchantCircle": "merchantcircle.com",
        "CitySearch": "citysearch.com", "Insider Pages": "insiderpages.com",
        "Kudzu": "kudzu.com", "Switchboard": "switchboard.com",
        "Whitepages": "whitepages.com", "411.com": "411.com", "DexKnows": "dexknows.com",
        "AngiesList": "angi.com", "Trustpilot": "trustpilot.com", "Waze": "waze.com",
        "Data Axle": "data-axle.com", "Neustar/Localeze": "localeze.com",
        "Infogroup": "infogroup.com", "GuideStar": "guidestar.org", "ZoomInfo": "zoominfo.com",
        "Birdeye": "birdeye.com", "LawInfo": "lawinfo.com", "FindGlocal": "findglocal.com",
    }

    # Build a lookup of source_url(s) per source domain so we can later fetch
    # the listing page for NAP verification. The Ahrefs shape we receive at the
    # top of this function may already be aggregated (no per-link URLs); fall
    # back to scanning the raw `ahrefs_refdomains.backlinks` if present.
    listing_urls_by_domain: dict[str, list[str]] = {}
    raw_backlinks = (
        ahrefs_refdomains.get("backlinks")
        if isinstance(ahrefs_refdomains, dict) else None
    ) or []
    for bl in raw_backlinks:
        url = bl.get("source_url") or bl.get("url_from") or ""
        try:
            from urllib.parse import urlparse
            host = (urlparse(url).hostname or "").lower().lstrip(".")
        except Exception:
            host = ""
        if host and url:
            listing_urls_by_domain.setdefault(host, []).append(url)

    merged = dict(directory_results)
    confirmed_count = 0
    for dir_name, domain in DIR_TO_DOMAIN.items():
        # Match either exact or subdomain (e.g. business.yelp.com → yelp.com)
        match = next((d for d in referring_domains if d == domain or d.endswith("." + domain)), None)
        if match:
            # Pull the link count for that domain for richer reporting
            link_info = next((it for it in items if (it.get("domain") or "").lower() == match), {})
            existing = merged.get(dir_name, {})
            # Collect the actual listing page URLs from this host (and subdomains)
            urls = []
            for host, host_urls in listing_urls_by_domain.items():
                if host == match or host.endswith("." + match):
                    urls.extend(host_urls)
            merged[dir_name] = {
                **existing,
                "found": True,
                "_source": f"{signal_source} (link verified)",
                "_referring_domain": match,
                "_listing_urls": urls[:5],  # cap to avoid storing thousands of variant URLs
                "_signal_strength": "high",
                "_dr": link_info.get("domain_rating"),
                "_links_to_target": link_info.get("links_to_target") or link_info.get("backlinks"),
            }
            confirmed_count += 1
    if confirmed_count:
        print(f"  ↳ {signal_source} confirmed {confirmed_count} live citations via link signal")
    return merged


def _verify_listing_nap(url: str, canonical: dict, timeout: float = 6.0) -> dict:
    """Fetch a directory listing page and score how well the on-page NAP matches
    the canonical NAP. Returns a verdict + the specific fields that matched."""
    try:
        import urllib.request, urllib.error, re
        req = urllib.request.Request(
            url,
            headers={
                "User-Agent": "Mozilla/5.0 (compatible; agency-os-local-seo-audit/1.0)",
                "Accept": "text/html,application/xhtml+xml",
            },
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            charset = resp.headers.get_content_charset() or "utf-8"
            html = resp.read(500_000).decode(charset, errors="replace")  # cap to 500 KB
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, ValueError, OSError) as e:
        return {"status": "fetch_failed", "error": str(e)[:160], "url": url}

    # Strip tags + normalize whitespace
    import re
    text = re.sub(r"<[^>]+>", " ", html)
    text = re.sub(r"\s+", " ", text).lower()

    def _norm_digits(s: str) -> str:
        return re.sub(r"\D", "", s or "")

    name = (canonical.get("name") or "").lower().strip()
    address = (canonical.get("address") or "").lower().strip()
    phone_digits = _norm_digits(canonical.get("phone") or "")

    checks = {}
    if name:
        # Substring of the first 3 name tokens is enough — directories often
        # truncate "Law Offices of Richard C. McConathy" to "Richard McConathy".
        head = " ".join(name.split()[:3])
        checks["name"] = head and head in text
    if address:
        # Match on the street number + first street word (most distinctive).
        m = re.match(r"\s*(\d+)\s+([a-z0-9.]+)", address)
        if m:
            number, street_word = m.group(1), m.group(2)
            checks["address"] = number in text and street_word in text
    if phone_digits:
        # Look for the last 7 digits of the phone (area code may be split out).
        checks["phone"] = phone_digits[-7:] in _norm_digits(text)

    matches = [k for k, ok in checks.items() if ok]
    missing = [k for k, ok in checks.items() if not ok]

    if not checks:
        verdict = "no_canonical_nap"
    elif not missing:
        verdict = "verified_correct"
    elif matches:
        verdict = "verified_mismatch"
    else:
        verdict = "no_match"

    return {
        "status": verdict,
        "url": url,
        "matched": matches,
        "missing": missing,
    }


def normalize_citations() -> dict:
    """Read Claude's per-directory web-search results and structure them.

    For firm-level directories: check is "does the firm profile exist + NAP correct"
    For attorney-level directories: check is "do all named attorneys have profiles"
       (a firm profile concept doesn't exist on these — Avvo, Justia, Nolo, etc.)

    Raw input shape:
      {
        "canonical_nap": {...},
        "attorneys": ["Jane Doe", "John Smith", ...],  # for attorney-level dirs
        "results": {
          "Yelp": { found: bool, url, nap },                          # firm-level
          "Avvo": { attorneys: { "Jane Doe": {found, url, ...}, ... } }  # attorney-level
        }
      }
    """
    raw = load_raw_any("citations-checks.json", "citations.json")
    dfs_citations = load_raw("dataforseo-citations.json")
    dfs_backlinks = load_raw("dataforseo-backlinks.json")
    ahrefs_refdomains = load_raw_any("ahrefs-refdomains-client.json", "ahrefs-local-links.json", "ahrefs-backlinks-raw.json")
    # Skip the stale "PARTIAL" cache if that's all we have
    if ahrefs_refdomains and isinstance(ahrefs_refdomains, dict):
        status = ahrefs_refdomains.get("_status", "")
        if status.startswith("PARTIAL"):
            ahrefs_refdomains = None

    # citations.json from the spec is a flat array shape — not the per-directory
    # `{results: {...}}` structure this builder expects. Treat it as "no manual
    # checks file" and rely on the backlink-merge path; an Ahrefs-only citation
    # pass is the documented happy path when DfS Business Listings isn't run.
    if raw and isinstance(raw, dict) and "results" not in raw:
        raw = None  # flat citations.json — discard, let backlink merge drive the result set

    if not raw and not dfs_citations and not ahrefs_refdomains:
        return {"_skipped": True, "reason": "no citation data — neither DataForSEO, Ahrefs, nor manual checks"}

    if not raw:
        # DfS-only mode — synthesize a checks frame from DfS data
        raw = {"canonical_nap": (dfs_citations.get("canonical_nap") if isinstance(dfs_citations, dict) else {}),
               "attorneys": [], "results": {}}

    canonical = dict(raw.get("canonical_nap") or {})
    # Fall back to the normalized gbp-profile.json (written by the previous
    # normalize step). Strategists rarely populate canonical_nap by hand; the
    # GBP profile is the canonical NAP for almost every audit.
    if not canonical.get("name") or not canonical.get("phone"):
        gbp_path = AUDIT_DIR / "gbp-profile.json"
        if gbp_path.exists():
            try:
                gbp_clean = json.loads(gbp_path.read_text())
            except json.JSONDecodeError:
                gbp_clean = {}
            for src, dest in (("name", "name"), ("address", "address"), ("phone", "phone"), ("website", "website")):
                if not canonical.get(dest) and gbp_clean.get(src):
                    canonical[dest] = gbp_clean[src]
    raw["canonical_nap"] = canonical
    all_attorneys = raw.get("attorneys", [])
    primary_source = "manual web-search checks (DfS not configured)"

    # PRIMARY PATH: if the DfS citation_scan tool has run, build the per-location
    # citations directly from its output against the agency directory universe.
    # The tool writes citations-scan.json to the audit-dir root; prefer that,
    # then fall back to raw/ for older runs.
    scan = None
    _scan_root = AUDIT_DIR / "citations-scan.json"
    if _scan_root.exists():
        try:
            scan = json.loads(_scan_root.read_text())
        except json.JSONDecodeError:
            scan = None
    if not (scan and isinstance(scan, dict) and scan.get("locations")):
        scan = load_raw_any("citations-scan.json")
    if scan and isinstance(scan, dict) and scan.get("locations"):
        universe, uni_meta = load_citation_universe()
        _rd = load_raw_any("ahrefs-refdomains-client.json", "ahrefs-local-links.json", "ahrefs-backlinks-raw.json")
        out = _citations_from_scan(scan, universe, canonical, _refdomains_set(_rd))
        out["_directory_source"] = uni_meta.get("source_name")
        out["_directory_count"] = uni_meta.get("total")
        if uni_meta.get("is_fallback"):
            out["_fallback_warning"] = uni_meta.get("fallback_warning")
            WARNINGS.append("citations: " + uni_meta.get("fallback_warning", "using fallback directory list"))
        return out

    # If Ahrefs OR DfS backlinks data is available, use it to confirm citations.
    # Any directory that links to the client domain = verified live citation.
    # Prefer Ahrefs (200 domains for batchwilliams.com vs DfS's 0).
    if (ahrefs_refdomains and isinstance(ahrefs_refdomains, dict)) or \
       (dfs_backlinks and isinstance(dfs_backlinks, dict) and not dfs_backlinks.get("_unavailable")):
        raw["results"] = _merge_dfs_backlinks(raw.get("results", {}), dfs_backlinks, ahrefs_refdomains)
        if ahrefs_refdomains:
            primary_source = "Ahrefs referring domains (link-verified)"
        else:
            primary_source = "DataForSEO Backlinks (link-verified)"

    # Verify NAP on each found citation by fetching its actual listing page.
    # Cap at 25 fetches and 6s timeout each — bounds total wall time at ~2.5min.
    if canonical and isinstance(raw.get("results"), dict):
        verified_count = 0
        for dir_name, entry in raw["results"].items():
            if verified_count >= 25:
                break
            if not isinstance(entry, dict) or not entry.get("found"):
                continue
            urls = entry.get("_listing_urls") or []
            if not urls:
                continue
            verdict = _verify_listing_nap(urls[0], canonical)
            entry["_nap_verification"] = verdict
            verified_count += 1
        if verified_count:
            print(f"  ↳ NAP-verified {verified_count} live citations by fetching listing pages")

    # If DfS citation data is available, merge it in (only if link-verified source didn't already win)
    if dfs_citations and isinstance(dfs_citations, dict) and not dfs_citations.get("_unavailable"):
        raw["results"] = _merge_dfs_citations(raw.get("results", {}), dfs_citations, canonical)
        # Only demote to "Business Listings Search" if we didn't already have a higher-confidence link-verified source
        if "link-verified" not in primary_source:
            primary_source = "DataForSEO Business Listings Search"

    rows = []
    _legacy_universe, _ = load_citation_universe()
    for directory, meta in _legacy_universe.items():
        check = raw.get("results", {}).get(directory, {})
        dir_type = meta.get("directory_type", "firm")

        if dir_type == "attorney":
            # Attorney-level: count how many named attorneys have profiles
            attorneys_data = check.get("attorneys") or {}
            found_attorneys = [name for name, d in attorneys_data.items() if d.get("found")]
            missing_attorneys = [n for n in all_attorneys if n not in found_attorneys]

            if not all_attorneys:
                status = "unknown"
                diff_summary = "No attorney list configured — set custom_fields.attorneys"
                action = "Configure attorney list to enable per-attorney audit"
            elif not missing_attorneys:
                status = "live_correct"
                diff_summary = f"All {len(all_attorneys)} attorneys have profiles"
                action = ""
            elif len(found_attorneys) == 0:
                status = "missing"
                diff_summary = f"No attorneys listed (need {len(all_attorneys)})"
                action = f"Create attorney profiles for: {', '.join(all_attorneys)}"
            else:
                status = "partial"
                diff_summary = f"{len(found_attorneys)}/{len(all_attorneys)} attorneys listed; missing: {', '.join(missing_attorneys)}"
                action = f"Add profiles for: {', '.join(missing_attorneys)}"

            rows.append({
                "directory":      directory,
                "tier":           meta["tier"],
                "priority":       meta["priority"],
                "directory_type": "attorney",
                "status":         status,
                "url":            check.get("url"),
                "diff_summary":   diff_summary,
                "action":         action,
                "attorneys_found":   found_attorneys,
                "attorneys_missing": missing_attorneys,
            })
            continue

        # Firm-level
        found = check.get("found")  # True / False / None (unverified)
        listing_nap = check.get("nap") or {}
        unverified = check.get("_unverified", False)
        # Link-verified flag: Ahrefs/DfS backlinks confirmed a link without NAP data
        link_verified = check.get("_signal_strength") == "high" and not listing_nap

        if unverified or found is None:
            status = "unverified"
            diff_summary = check.get("_note") or "Not yet checked"
            action = "Run web search or pull citation report to confirm"
        elif found is False:
            status = "missing"
            diff_summary = ""
            action = _citation_action("missing", meta["priority"])
        elif link_verified:
            # Link-verified live citation. If we managed to fetch the listing page
            # and check NAP, promote the verdict; otherwise fall back to the old
            # "exists but unverified" wording.
            link_count = check.get("_links_to_target") or "?"
            dr = check.get("_dr") or "?"
            ref_domain = check.get("_referring_domain", "")
            nv = check.get("_nap_verification") or {}
            nv_status = nv.get("status")
            if nv_status == "verified_correct":
                status = "live_correct"
                diff_summary = (
                    f"✓ Confirmed live + NAP matches canonical\n"
                    f"    Source:    {ref_domain} (DR {dr})\n"
                    f"    Verified:  fetched {nv.get('url','')[:80]} — name, address, phone all match"
                )
                action = ""
            elif nv_status == "verified_mismatch":
                status = "live_mismatch"
                missing = ", ".join(nv.get("missing") or []) or "—"
                diff_summary = (
                    f"⚠ Confirmed live but NAP mismatch\n"
                    f"    Source:    {ref_domain} (DR {dr})\n"
                    f"    Missing:   {missing} did not match canonical on the live page\n"
                    f"    URL:       {nv.get('url','')[:80]}"
                )
                action = _citation_action("live_mismatch", meta["priority"])
            elif nv_status == "no_match":
                status = "live_mismatch"
                diff_summary = (
                    f"⚠ Confirmed live but none of name/address/phone matched the on-page text\n"
                    f"    Source:    {ref_domain} (DR {dr})\n"
                    f"    URL:       {nv.get('url','')[:80]}\n"
                    f"    Note:      The listing might be a stub or a different business — manual review recommended"
                )
                action = _citation_action("live_mismatch", meta["priority"])
            else:
                # fetch_failed / no_canonical_nap / no listing URL → unverified
                status = "live"
                detail = nv.get("error") if nv_status == "fetch_failed" else "no listing URL available"
                diff_summary = (
                    f"✓ Confirmed live via backlink signal\n"
                    f"    Source:    {ref_domain} (DR {dr})\n"
                    f"    Links:     {link_count} dofollow links to client domain\n"
                    f"    Note:      Listing exists but NAP auto-verification was inconclusive ({detail})"
                )
                action = "Open the live listing and confirm NAP matches the correct values"
        else:
            diffs = _nap_diff(canonical, listing_nap)
            if not diffs:
                status = "live_correct"
                diff_summary = "✓ Listed with correct NAP"
                action = ""
            else:
                status = "live_mismatch"
                # Join each diff with a blank line for readability
                diff_summary = "⚠ NAP mismatch on live listing:\n\n" + "\n\n".join(diffs)
                action = _citation_action("live_mismatch", meta["priority"])

        rows.append({
            "directory":          directory,
            "tier":               meta["tier"],
            "priority":           meta["priority"],
            "directory_type":     "firm",
            "status":             status,
            "url":                check.get("url") or (check.get("_nap_verification") or {}).get("url"),
            "diff_summary":       diff_summary,
            "action":             action,
            "links_to_target":    check.get("_links_to_target"),
            "domain_rating":      check.get("_dr"),
            "signal_source":      check.get("_source"),
            "nap_verification":   check.get("_nap_verification"),
        })

    # Summary
    by_status = defaultdict(int)
    for r in rows:
        by_status[r["status"]] += 1

    # Coverage % calculated against verified entries only (don't penalize unverifieds)
    verified_count = sum(1 for r in rows if r["status"] != "unverified")
    # Count link-verified "live" as found (the listing exists; NAP just needs manual check)
    live_total = by_status["live_correct"] + by_status["live"] + by_status["live_mismatch"]
    return {
        "canonical_nap": canonical,
        "directories": rows,
        "summary": {
            "total":               len(rows),
            "verified":            verified_count,
            "unverified":          by_status["unverified"],
            "live":                by_status["live"],
            "live_correct":        by_status["live_correct"],
            "live_mismatch":       by_status["live_mismatch"],
            "partial":             by_status["partial"],
            "missing":             by_status["missing"],
            "coverage_pct":        round(100 * live_total / max(1, verified_count), 1),
            "submit_queue_count":  by_status["missing"],
            "fix_queue_count":     by_status["live_mismatch"] + by_status["live"],   # "live" needs NAP review
            "_note":               f"Coverage % counts live + live_correct + live_mismatch (all confirmed-existing listings). Calculated against {verified_count} verified entries.",
            "_primary_source":     primary_source,
        },
        "pulled_at": raw.get("pulled_at", now()),
    }


def _nap_diff(canonical: dict, listing: dict) -> list[str]:
    """Detect NAP field-by-field mismatches in plain English with both values shown."""

    # Standard USPS street/unit abbreviations — treat short and long forms as equivalent
    ADDRESS_ABBREVS = {
        "drive": "dr", "street": "st", "avenue": "ave", "boulevard": "blvd",
        "road": "rd", "lane": "ln", "court": "ct", "place": "pl",
        "highway": "hwy", "parkway": "pkwy", "circle": "cir", "terrace": "ter",
        "suite": "ste", "apartment": "apt", "building": "bldg", "floor": "fl",
        "north": "n", "south": "s", "east": "e", "west": "w",
        "northeast": "ne", "northwest": "nw", "southeast": "se", "southwest": "sw",
    }

    def normalize_address(s: str) -> str:
        """Lowercase, strip punctuation, expand abbreviations to a canonical short form."""
        s = s.lower()
        # Strip punctuation, keep spaces
        s = "".join(ch if ch.isalnum() or ch.isspace() else " " for ch in s)
        # Tokenize and normalize each word
        tokens = []
        for tok in s.split():
            tokens.append(ADDRESS_ABBREVS.get(tok, tok))
        return " ".join(tokens)

    def normalize_phone(s: str) -> str:
        """Strip everything except digits — (919) 234-5797 == 919-234-5797 == 9192345797."""
        return "".join(ch for ch in s if ch.isdigit())

    diffs = []
    FIELD_LABELS = {"name": "Name", "address": "Address", "phone": "Phone", "website": "Website"}
    for field in ("name", "address", "phone", "website"):
        label = FIELD_LABELS[field]
        c_val_raw = canonical.get(field) or ""
        l_val_raw = listing.get(field) or ""
        c_val = c_val_raw.strip().lower()
        l_val = l_val_raw.strip().lower()

        if c_val and l_val and c_val != l_val:
            # Apply field-specific normalization to decide formatting-only vs real diff
            if field == "address":
                c_norm = normalize_address(c_val)
                l_norm = normalize_address(l_val)
            elif field == "phone":
                c_norm = normalize_phone(c_val)
                l_norm = normalize_phone(l_val)
            else:
                c_norm = "".join(ch for ch in c_val if ch.isalnum())
                l_norm = "".join(ch for ch in l_val if ch.isalnum())

            if c_norm == l_norm:
                diffs.append(
                    f"{label} – formatting only:\n"
                    f"    Listed:    {l_val_raw}\n"
                    f"    Correct:   {c_val_raw}"
                )
            else:
                diffs.append(
                    f"{label} differs:\n"
                    f"    Listed:    {l_val_raw}\n"
                    f"    Correct:   {c_val_raw}"
                )
        elif c_val and not l_val:
            diffs.append(f"{label} missing on listing — correct value: {c_val_raw}")
    return diffs


def _citation_action(status: str, priority: str) -> str:
    if status == "live_correct":
        return ""
    if status == "live_mismatch":
        return f"Fix NAP mismatch ({priority})"
    return f"Submit new citation ({priority})"


# ===========================================================================
# 5. LOCAL LINKS — client vs competitor referring-domain matrix
# ===========================================================================

def normalize_local_links() -> dict:
    client_raw = load_raw_any("ahrefs-refdomains-client.json", "ahrefs-local-links.json", "ahrefs-backlinks-raw.json")
    if not client_raw:
        return {"_skipped": True, "reason": "no raw ahrefs-refdomains-client.json / ahrefs-local-links.json"}

    # Spec shape (`ahrefs-local-links.json`) is `{backlinks: [{source_url, ...}]}`.
    # Legacy shape (`ahrefs-refdomains-client.json`) is `{domains: [{domain, ...}]}`.
    client_domains: set[str] = set()
    if isinstance(client_raw.get("domains"), list):
        client_domains = {d["domain"] for d in client_raw["domains"] if isinstance(d, dict) and d.get("domain")}
    elif isinstance(client_raw.get("backlinks"), list):
        from urllib.parse import urlparse
        for bl in client_raw["backlinks"]:
            url = bl.get("source_url") or bl.get("url_from") or ""
            try:
                host = (urlparse(url).hostname or "").lower().lstrip(".")
            except Exception:
                host = ""
            if host:
                client_domains.add(host)

    competitors: dict[str, set[str]] = {}
    for i in range(1, 4):
        comp_raw = load_raw(f"ahrefs-refdomains-comp{i}.json")
        if comp_raw:
            comp_name = comp_raw.get("source_domain", f"competitor_{i}")
            competitors[comp_name] = {d["domain"] for d in comp_raw.get("domains", [])}

    # Compute union of all referring domains
    all_domains = set(client_domains)
    for comp_set in competitors.values():
        all_domains |= comp_set

    rows = []
    for d in all_domains:
        client_has = d in client_domains
        comp_count = sum(1 for s in competitors.values() if d in s)
        # Opportunity score: high if competitors have it but client doesn't
        if not client_has and comp_count >= 2:
            opp_score = "P1"
        elif not client_has and comp_count == 1:
            opp_score = "P2"
        elif client_has:
            opp_score = ""
        else:
            opp_score = "P3"
        rows.append({
            "domain":     d,
            "client_has": client_has,
            "comp_count": comp_count,
            "opportunity": opp_score,
        })

    # Sort: P1 opportunities first, then P2, then client's existing
    rows.sort(key=lambda r: (
        {"P1": 0, "P2": 1, "P3": 2, "": 3}[r["opportunity"]],
        -r["comp_count"],
        r["domain"],
    ))

    return {
        "competitor_domains": list(competitors.keys()),
        "rows": rows,
        "summary": {
            "client_total":          len(client_domains),
            "p1_opportunities":      sum(1 for r in rows if r["opportunity"] == "P1"),
            "p2_opportunities":      sum(1 for r in rows if r["opportunity"] == "P2"),
            "gap_pct":               round(100 * (len(all_domains) - len(client_domains)) / max(1, len(all_domains)), 1),
        },
        "pulled_at": client_raw.get("pulled_at", now()),
    }


# ===========================================================================
# 6. LOCAL PAGES — filter site crawl to local-relevant pages
# ===========================================================================

LOCATION_PATTERNS = ["location", "service-area", "service-areas", "areas-served", "/locations/"]
SERVICE_AREA_HINTS = ["near", "city", "county", "neighborhood"]


def normalize_local_pages() -> dict:
    """Read the WQA crawl JSON, filter to local-relevant pages.

    Categorizes each page as:
      - location_page    : per-city landing pages
      - service_area_page: pages targeting a service + city combo
      - has_local_schema : pages with LocalBusiness / Service / Review schema
      - other            : non-local
    """
    crawl_path = ROOT / "clients" / args.client_slug / "crawls" / "latest-crawl.json"
    if not crawl_path.exists():
        return {"_skipped": True, "reason": f"no crawl at {crawl_path}"}

    crawl = json.loads(crawl_path.read_text())
    pages = crawl.get("pages") or crawl.get("data") or []

    categorized = {
        "location_pages":     [],
        "service_area_pages": [],
        "local_schema_pages": [],
        "all_count":          len(pages),
    }

    for p in pages:
        url = (p.get("url") or p.get("address") or "").lower()
        schema = (p.get("schema") or p.get("structured_data") or "").lower()
        title = (p.get("title") or p.get("title_1") or "").lower()

        is_location = any(pat in url for pat in LOCATION_PATTERNS)
        is_service_area = any(h in url or h in title for h in SERVICE_AREA_HINTS) and not is_location
        has_schema = any(s in schema for s in ("localbusiness", "service", "review", "place"))

        if is_location:
            categorized["location_pages"].append({"url": p.get("url"), "title": p.get("title")})
        if is_service_area:
            categorized["service_area_pages"].append({"url": p.get("url"), "title": p.get("title")})
        if has_schema:
            categorized["local_schema_pages"].append({"url": p.get("url")})

    return {
        **categorized,
        "summary": {
            "total_pages":            len(pages),
            "location_pages_count":   len(categorized["location_pages"]),
            "service_area_count":     len(categorized["service_area_pages"]),
            "local_schema_count":     len(categorized["local_schema_pages"]),
        },
        "pulled_at": crawl.get("pulled_at") or now(),
    }


# ===========================================================================
# Letter grade helper
# ===========================================================================

def _letter_grade(pct: float) -> str:
    if pct >= 90: return "A"
    if pct >= 80: return "B"
    if pct >= 70: return "C"
    if pct >= 60: return "D"
    return "F"


# ===========================================================================
# Main
# ===========================================================================

def normalize_ai_geo() -> dict:
    """Build the AI / Generative Search visibility report from the DfS keyword
    tracker output. Each result row already includes ai_rank (rank of the client
    inside the AI Overview block; 0 = not cited)."""
    rankings = load_raw("keyword-rankings.json")
    if not isinstance(rankings, dict) or not rankings.get("results"):
        return {"_skipped": True, "reason": "no keyword-rankings.json"}

    results = rankings["results"]
    query_tests = []
    cited = 0
    for r in results:
        kw = r.get("keyword")
        if not kw:
            continue
        ai_rank = r.get("ai_rank") or 0
        client_surfaces = ai_rank > 0
        if client_surfaces:
            cited += 1
        # Competitors_surfaced: top_3 organic competitors are good proxy
        comp_names = [c.get("name") or c.get("domain") for c in (r.get("top_3_competitors") or [])][:3]
        query_tests.append({
            "query": kw,
            "client_surfaces": client_surfaces,
            "ai_rank": ai_rank or None,
            "ai_block_present": True,  # DfS keyword tracker only returns rows where AI block was detected
            "competitors_surfaced": [c for c in comp_names if c],
        })

    total = len(query_tests)
    score_pct = round(100 * cited / total, 1) if total else 0
    if score_pct >= 70:
        grade = "A"
    elif score_pct >= 50:
        grade = "B"
    elif score_pct >= 30:
        grade = "C"
    elif score_pct >= 10:
        grade = "D"
    else:
        grade = "F"

    summary = (
        f"Cited in {cited}/{total} AI Overview blocks ({score_pct}%) — grade {grade}. "
        + ("AI search visibility is a major gap — entity authority signals need work." if score_pct < 30 else
           "AI search visibility is competitive but has room to expand into untracked queries." if score_pct < 70 else
           "Strong AI search visibility across tracked queries.")
    )

    # Entity signals (auto-detected from data we have)
    entity_signals = []
    gbp_raw = load_raw_any("gbp-profile.json", "dataforseo-business-data.json")
    gbp_item = _unwrap_dfs_envelope(gbp_raw) if gbp_raw else {}
    if isinstance(gbp_item, dict):
        entity_signals.append({
            "signal": "GBP listing claimed",
            "status": "live_correct" if gbp_item.get("is_claimed") else "missing",
            "notes": "Primary entity anchor for Google's knowledge graph." if gbp_item.get("is_claimed") else "Claim immediately — required for entity verification.",
        })
        entity_signals.append({
            "signal": "Categories defined (primary + 3+ secondary)",
            "status": "live_correct" if len(gbp_item.get("additional_categories") or []) >= 3 else "partial",
            "notes": "More category coverage = more entity context for AI engines.",
        })
    backlinks_raw = load_raw_any("ahrefs-refdomains-client.json", "ahrefs-local-links.json", "ahrefs-backlinks-raw.json")
    has_wikipedia = False
    if isinstance(backlinks_raw, dict) and backlinks_raw.get("backlinks"):
        has_wikipedia = any(
            "wikipedia.org" in (bl.get("source_url") or bl.get("url_from") or "").lower()
            for bl in backlinks_raw["backlinks"]
        )
    entity_signals.append({
        "signal": "Wikipedia entity (firm or partner)",
        "status": "live_correct" if has_wikipedia else "missing",
        "notes": "AI engines disproportionately weight Wikipedia citations." if not has_wikipedia else "Wikipedia link detected via Ahrefs.",
    })
    entity_signals.append({
        "signal": "LegalService schema on practice area pages",
        "status": "unknown",
        "notes": "Verify via on-site crawl. Schema is a primary AI search signal.",
    })

    # Recommended actions to lift AI visibility
    actions = []
    if score_pct < 50:
        actions.append({
            "priority": "P1",
            "action": "Implement LocalBusiness + LegalService schema with sameAs links to all directory profiles",
            "rationale": "Structured data is one of the strongest signals AI engines use to identify entities and their authoritativeness.",
        })
    if not has_wikipedia:
        actions.append({
            "priority": "P2",
            "action": "Pursue inclusion in Wikipedia (firm partners, notable cases, legal contributions)",
            "rationale": "Wikipedia citations are disproportionately weighted by every major AI engine.",
        })
    actions.append({
        "priority": "P2",
        "action": "Submit firm bios + attorney profiles to 5+ tier-1 legal directories (Avvo, Justia, FindLaw, Super Lawyers, Martindale)",
        "rationale": "AI engines triangulate entity identity from cross-directory references. Each new mention strengthens the signal.",
    })
    if cited < total:
        missing_queries = [q["query"] for q in query_tests if not q["client_surfaces"]][:5]
        if missing_queries:
            actions.append({
                "priority": "P1",
                "action": f"Build long-form authority content addressing the queries the client doesn't surface for: {', '.join(missing_queries[:3])}",
                "rationale": "AI engines cite content that directly answers the user's question with depth + first-hand expertise.",
            })

    return {
        "summary":        summary,
        "score_pct":      score_pct,
        "grade":          grade,
        "cited_count":    cited,
        "total_queries":  total,
        "query_tests":    query_tests,
        "entity_signals": entity_signals,
        "actions":        actions,
        "pulled_at":      rankings.get("pulled_at", now()),
    }


def normalize_locations(falcon: dict, gbp: dict) -> dict:
    """Build a client-agnostic list of every GBP location (1..N) from the client
    record: primary office + any secondary office(s) from NAP, plus a duplicate
    listing if flagged in _known_findings. gmb_connected is derived from whether a
    Windsor GMB account is wired. Single-location clients yield a 1-entry list."""
    import pathlib, re as _re
    cpath = pathlib.Path(args.workspace_root) / "data" / "clients.json"
    if not cpath.exists():
        return {"count": 0, "locations": [], "has_duplicate": False}
    try:
        clients = json.loads(cpath.read_text())
    except Exception:
        return {"count": 0, "locations": [], "has_duplicate": False}
    if isinstance(clients, dict):
        clients = clients.get("clients", clients)
    cf = {}
    for c in (clients or []):
        if (c.get("custom_fields") or {}).get("slug") == args.client_slug:
            cf = c.get("custom_fields") or {}
            break
    if not cf:
        return {"count": 0, "locations": [], "has_duplicate": False}

    nap = cf.get("nap") or {}
    grid_kws = list((falcon.get("summary") or {}).keys())
    # primary review count/avg from the normalized GBP profile fields
    def _gbp_field(name):
        for f in gbp.get("fields", []):
            if f.get("field") == name:
                return f.get("current")
        return None
    prim_reviews = {"count": _gbp_field("review_count") or (nap.get("reviews") or {}).get("count"),
                    "avg":   _gbp_field("review_avg")   or (nap.get("reviews") or {}).get("avg")}
    wired_gmb = bool((cf.get("windsor_accounts") or {}).get("gmb"))

    locs = [{
        "name": nap.get("name") or "Primary office", "role": "primary",
        "address": nap.get("address"), "phone": nap.get("phone"),
        "place_id": nap.get("place_id_louisville") or nap.get("place_id"),
        "cid": nap.get("cid_louisville") or nap.get("cid"),
        "gmb_location_id": cf.get("gmb_location_id"),
        "gmb_connected": wired_gmb,
        "reviews": prim_reviews, "grid_keywords": grid_kws,
        "notes": "Primary Google Business Profile.",
    }]
    # secondary office(s): support both a single secondary_office object and a list
    sec = nap.get("secondary_office")
    sec_list = sec if isinstance(sec, list) else ([sec] if isinstance(sec, dict) else [])
    sec_gmb = cf.get("gmb_location_id_secondary") or cf.get("gmb_location_id_secondary_pending")
    sec_connected = bool(cf.get("gmb_location_id_secondary") or (cf.get("windsor_accounts") or {}).get("gmb_secondary"))
    for s in sec_list:
        locs.append({
            "name": s.get("name") or "Second office", "role": "office",
            "address": s.get("address"), "phone": s.get("phone"),
            "place_id": s.get("place_id"), "cid": s.get("cid"),
            "gmb_location_id": s.get("gmb_location_id") or sec_gmb,
            "gmb_connected": sec_connected,
            "reviews": {"count": None, "avg": None}, "grid_keywords": [],
            "notes": ("GMB connected in Windsor; run Local Falcon scans for full grid coverage."
                      if sec_connected else
                      "Verify GMB connection in Windsor and run Local Falcon scans for full coverage."),
        })
    # duplicate listing flagged in known findings
    findings = " ".join(cf.get("_known_findings_pre_audit") or [])
    has_dup = ("duplicate" in findings.lower()) and ("gbp" in findings.lower() or "listing" in findings.lower())
    if has_dup:
        cids = _re.findall(r'CID\s*(\d{6,})', findings)
        rats = _re.findall(r'(\d\.\d)\s*[★\*]?\s*(\d+)\s*review', findings)
        dup_rev = {"avg": float(rats[1][0]), "count": int(rats[1][1])} if len(rats) > 1 else {"avg": None, "count": None}
        locs.append({
            "name": (nap.get("name") or "") + " — DUPLICATE listing", "role": "duplicate",
            "cid": cids[1] if len(cids) > 1 else None, "gmb_location_id": None, "gmb_connected": False,
            "reviews": dup_rev, "grid_keywords": [], "priority": "P1",
            "notes": "Duplicate Google Business Profile competing with the primary — splits reviews + ranking signal. P1: consolidate/remove via Google duplicate-listing resolution.",
        })
    return {"count": len([l for l in locs if l["role"] != "duplicate"]), "locations": locs, "has_duplicate": has_dup}


def main():
    print(f"Normalizing Local SEO Audit for {args.client_slug} (audit {args.audit_id})")
    print(f"  raw input: {RAW}")
    print(f"  clean output: {AUDIT_DIR}")
    AUDIT_DIR.mkdir(parents=True, exist_ok=True)

    print("\n[1/7] Local Falcon grid...")
    falcon = normalize_local_falcon()
    write_clean("local-falcon-grid.json", falcon)

    print("\n[2/7] GBP profile...")
    gbp = normalize_gbp()
    write_clean("gbp-profile.json", gbp)

    print("\n[3/7] GSC local queries...")
    gsc = normalize_gsc_local()
    write_clean("gsc-local-queries.json", gsc)

    print("\n[4/7] Citations (50 directories)...")
    cits = normalize_citations()
    write_clean("citations.json", cits)

    print("\n[5/7] Local links (client vs competitors)...")
    links = normalize_local_links()
    write_clean("local-links.json", links)

    print("\n[6/7] Local pages (from site crawl)...")
    pages = normalize_local_pages()
    write_clean("local-pages.json", pages)

    print("\n[7/7] AI / Generative search visibility...")
    ai_geo = normalize_ai_geo()
    write_clean("ai-geo-findings.json", ai_geo)

    print("\n[+] GBP locations (multi-location)...")
    locs = normalize_locations(falcon, gbp)
    write_clean("locations.json", locs)
    print(f"  {locs.get('count', 0)} location(s)" + (" + duplicate listing" if locs.get("has_duplicate") else ""))

    # Data-coverage summary. IMPORTANT: this is NOT audit-manifest.json — that
    # file is owned by the localseo_create_audit / localseo_update_config MCP
    # tools (id, client_id, locations, keywords, competitors, match,
    # providers_used, last_checkpoint, ...). This script must never write to
    # audit-manifest.json; doing so previously clobbered the MCP tools' state
    # with this bare schema, silently destroying checkpoint/location/keyword
    # history. build_local_audit_xlsx.py and build_local_audit_report.py read
    # this file (data-coverage.json) for grades/topline, and read
    # audit-manifest.json separately (via the MCP tools) for everything else.
    manifest = {
        "client_slug": args.client_slug,
        "audit_id": args.audit_id,
        "generated_at": now(),
        "sources": {
            "local_falcon":  not falcon.get("_skipped"),
            "gbp":           not gbp.get("_skipped"),
            "gsc":           not gsc.get("_skipped"),
            "citations":     not cits.get("_skipped"),
            "local_links":   not links.get("_skipped"),
            "local_pages":   not pages.get("_skipped"),
        },
        "warnings": WARNINGS,
        "grades": {
            "gbp_pct":          gbp.get("grade_pct"),
            "gbp_letter":       gbp.get("letter_grade"),
            "citation_cov_pct": cits.get("summary", {}).get("coverage_pct"),
        },
    }
    write_clean("data-coverage.json", manifest)

    # Summary
    print("\n📊 AUDIT NORMALIZATION COMPLETE")
    print(f"  GBP grade:           {gbp.get('letter_grade', '—')} ({gbp.get('grade_pct', '—')}%)")
    print(f"  Citation coverage:   {cits.get('summary', {}).get('coverage_pct', '—')}%")
    print(f"  Citations missing:   {cits.get('summary', {}).get('submit_queue_count', '—')}")
    print(f"  Citations mismatch:  {cits.get('summary', {}).get('fix_queue_count', '—')}")
    print(f"  Local link gaps:     P1 = {links.get('summary', {}).get('p1_opportunities', '—')}, P2 = {links.get('summary', {}).get('p2_opportunities', '—')}")
    print(f"  Local pages:         loc={pages.get('summary', {}).get('location_pages_count', '—')}, SA={pages.get('summary', {}).get('service_area_count', '—')}, schema={pages.get('summary', {}).get('local_schema_count', '—')}")
    if WARNINGS:
        print(f"\n⚠ {len(WARNINGS)} warnings:")
        for w in WARNINGS:
            print(f"    · {w}")
    print(f"\nReady for: build_local_audit_xlsx.py --client-slug {args.client_slug} --audit-id {args.audit_id}")


if __name__ == "__main__":
    main()
