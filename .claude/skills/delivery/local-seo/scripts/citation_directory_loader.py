#!/usr/bin/env python3
"""
Citation directory loader — vertical-agnostic.

The directory list is NOT hardcoded. Each agency supplies its own citation
sheet (legal, medical, home-services, etc.) as a CSV dropped in the connected
folder. This module finds that file, parses it, and returns a normalized
directory universe in the same shape the audit consumes.

Accepted CSV format (Blueprint "Legal Citations" layout — extra columns are
preserved, missing columns degrade gracefully). Column 0 is an unnamed
*category* column (General / Legal / Legal Niche / Regional / ...):

    <category>, Tier, Name, Domain, Profile Example, Profile Submission Link,
    TF, Traffic, Link Type, Free/Paid, Price, Month/Year, Notes,
    Multiple/Single Profile

Mapping into audit fields:
    Tier "1"/blank      -> priority  (1 -> P1, blank -> P2)
    Name                -> directory label
    Domain              -> SERP match target (normalized to a bare domain)
    Profile Submission  -> action URL for missing/wrong listings (fix track)
    TF / Traffic        -> secondary ranking signal
    category            -> grouping (General = universal foundation)

Fallback: if no agency file is found, the bundled legal sheet is used and the
caller is told it is legally focused — the General category is the universal
foundation every local business needs; Legal/Regional should be swapped for
the agency's vertical and market.
"""
from __future__ import annotations
import csv
import re
from pathlib import Path
from urllib.parse import urlparse

# Directories that expose per-lawyer profiles rather than a single firm profile.
# Used only to set directory_type so legal audits can run the per-attorney
# coverage check. Non-legal lists simply never match these → everything "firm".
_ATTORNEY_LEVEL_DOMAINS = {
    "avvo.com", "justia.com", "nolo.com", "hg.org", "lawyer.com", "lawyers.com",
    "martindale.com", "bestlawyers.com", "lawcrossing.com", "attorneypages.com",
    "lawyerlegion.com", "superlawyers.com",
}

_FALLBACK = Path(__file__).resolve().parent.parent / "templates" / "citations-fallback-generic.csv"
# Vertical-specific templates (used only if the agency asks for one explicitly):
_FALLBACK_LEGAL = Path(__file__).resolve().parent.parent / "templates" / "citations-fallback-legal.csv"


def _norm_domain(raw: str) -> str:
    """Reduce a Domain/URL cell to a bare registrable domain for matching."""
    s = (raw or "").strip().lower()
    if not s:
        return ""
    if "://" not in s:
        s = "https://" + s
    host = urlparse(s).netloc or urlparse(s).path
    host = host.split("/")[0].strip()
    if host.startswith("www."):
        host = host[4:]
    # Guard against malformed cells like "lawyers.findlaw.comprofile" (missing slash)
    m = re.match(r"^([a-z0-9-]+(?:\.[a-z0-9-]+)+?)(?:com|net|org|gov|edu|us|io)?$", host)
    # Best-effort: if it looks like "<name>.com<junk>", trim at a known TLD boundary
    tld_fix = re.match(r"^(.*?\.(?:com|net|org|gov|edu|us|io|co))(?:[a-z].*)?$", host)
    if tld_fix:
        host = tld_fix.group(1)
    return host


def _num(raw: str):
    s = (raw or "").strip().replace(",", "").replace("$", "")
    if not s:
        return None
    mult = 1
    if s.lower().endswith("k"):
        mult, s = 1000, s[:-1]
    try:
        return int(float(s) * mult)
    except ValueError:
        return None


def _slug(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", (name or "").lower()).strip("-")


def find_citation_file(search_paths: list[Path]) -> Path | None:
    """Return the first citation CSV found across the given folders.

    A file qualifies if its name contains 'citation' (case-insensitive) and it
    is a .csv. Search order is the caller's responsibility (client folder first,
    then agency/workspace root, then connected-folder root).
    """
    for base in search_paths:
        if not base or not base.exists():
            continue
        if base.is_file():
            if base.suffix.lower() == ".csv":
                return base
            continue
        hits = sorted(
            [p for p in base.glob("*.csv") if "citation" in p.name.lower()],
            key=lambda p: p.stat().st_mtime, reverse=True,
        )
        if hits:
            return hits[0]
    return None


def load_directories(csv_path: Path) -> tuple[dict, dict]:
    """Parse a citation CSV into the directory universe.

    Returns (directories, meta):
      directories = { name: { tier, priority, directory_type, url, domain,
                              category, submission_link, profile_example,
                              tf, traffic, link_type, cost, recurrence,
                              notes, profile_cardinality, slug } }
      meta        = { source_path, source_name, total, by_category, is_fallback }
    """
    rows = list(csv.reader(open(csv_path, encoding="utf-8-sig")))
    if not rows:
        return {}, {"source_path": str(csv_path), "total": 0, "by_category": {}}

    # Locate header row (the one containing 'Name' and 'Domain')
    header_idx = 0
    for i, r in enumerate(rows[:5]):
        low = [c.strip().lower() for c in r]
        if "name" in low and "domain" in low:
            header_idx = i
            break
    header = [c.strip().lower().replace("\n", " ") for c in rows[header_idx]]

    def col(*names):
        for n in names:
            if n in header:
                return header.index(n)
        return None

    c_cat = 0  # unnamed first column = category
    c_tier = col("tier")
    c_name = col("name")
    c_domain = col("domain")
    c_example = col("profile example")
    c_submit = col("profile submission link", "submission link")
    c_tf = col("tf")
    c_traffic = col("traffic")
    c_linktype = col("link type")
    c_cost = col("free/paid")
    c_price = col("price")
    c_recur = col("month/ year", "month/year")
    c_notes = col("notes")
    c_card = col("multiple/single profile", "multiple/single  profile")
    c_vertical = col("vertical")
    c_deep = col("deep-optimize", "deep optimize")

    def cell(r, idx):
        return r[idx].strip() if (idx is not None and idx < len(r)) else ""

    directories: dict = {}
    by_category: dict = {}
    for r in rows[header_idx + 1:]:
        name = cell(r, c_name)
        if not name or not any(c.strip() for c in r):
            continue
        domain = _norm_domain(cell(r, c_domain))
        category = cell(r, c_cat) or "General"
        tier_raw = cell(r, c_tier)
        priority = "P1" if tier_raw == "1" else "P2"
        tier = 1 if tier_raw == "1" else 2
        example = cell(r, c_example)
        dtype = "firm"
        probe = f"{domain} {example}".lower()
        if domain in _ATTORNEY_LEVEL_DOMAINS or "/lawyer/" in probe or "/attorney" in probe:
            dtype = "attorney"
        directories[name] = {
            "tier": tier,
            "priority": priority,
            "directory_type": dtype,
            "url": ("https://" + domain) if domain else (example or ""),
            "domain": domain,
            "category": category,
            "submission_link": cell(r, c_submit),
            "profile_example": example,
            "tf": _num(cell(r, c_tf)),
            "traffic": _num(cell(r, c_traffic)),
            "link_type": cell(r, c_linktype),
            "cost": cell(r, c_cost),
            "price": cell(r, c_price),
            "recurrence": cell(r, c_recur),
            "notes": cell(r, c_notes),
            "profile_cardinality": cell(r, c_card),
            "vertical": (cell(r, c_vertical) or "").lower() or ("all" if category.lower().startswith("general") else ""),
            "deep_optimize": cell(r, c_deep).strip().lower() in ("y", "yes", "1", "true"),
            "slug": _slug(name),
        }
        by_category[category] = by_category.get(category, 0) + 1

    meta = {
        "source_path": str(csv_path),
        "source_name": csv_path.name,
        "total": len(directories),
        "by_category": by_category,
        "is_fallback": False,
    }
    return directories, meta


def resolve_directories(search_paths: list[Path], allow_fallback: bool = True) -> tuple[dict, dict]:
    """Find + load the agency citation list, or fall back to the bundled legal sheet."""
    found = find_citation_file(search_paths)
    if found:
        dirs, meta = load_directories(found)
        if dirs:
            return dirs, meta
    if not allow_fallback or not _FALLBACK.exists():
        return {}, {"total": 0, "by_category": {}, "is_fallback": False, "missing": True}
    dirs, meta = load_directories(_FALLBACK)
    meta.update({
        "is_fallback": True,
        "fallback_warning": (
            "No citation list found for this agency — using the bundled GENERIC fallback "
            "(~50 high-DA general + niche directories). This is vertical-agnostic; for best "
            "results supply your own list (or use a vertical template, e.g. legal) and add "
            "the client's local/market-specific directories."
        ),
    })
    return dirs, meta


def select_for_vertical(directories: dict, vertical: str | None) -> dict:
    """Assemble a niche-aligned list from a loaded directory universe.

    Returns { deep_optimize: [...], full: [...], skipped_other_verticals: [...] }:
      - deep_optimize  = Step 4 set: the universal deep-optimize profiles (deep_optimize=True)
                         PLUS the niche directories matching `vertical` (the vertical add-ons).
      - full           = Step 5 citation universe: universal ('all'/general) rows + the niche
                         rows matching `vertical`. Niche rows for OTHER verticals are dropped.
    A row matches if its vertical is 'all'/'' (universal) or equals the client's vertical.
    Pass vertical=None to keep everything (no filtering).
    """
    v = (vertical or "").strip().lower()
    def is_universal(d): return d.get("vertical") in ("all", "", None)
    def matches(d): return (not v) or is_universal(d) or d.get("vertical") == v
    full, deep, skipped = [], [], []
    for name, d in directories.items():
        d = {**d, "name": name}
        if matches(d):
            full.append(d)
            if d.get("deep_optimize") or (v and d.get("vertical") == v):
                deep.append(d)
        else:
            skipped.append(d)
    key = lambda d: -(d.get("tf") or 0)
    return {"deep_optimize": sorted(deep, key=key), "full": sorted(full, key=key),
            "skipped_other_verticals": skipped, "vertical": v or "all"}


if __name__ == "__main__":
    import sys, json
    args = [a for a in sys.argv[1:] if not a.startswith("--vertical=")]
    vert = next((a.split("=",1)[1] for a in sys.argv[1:] if a.startswith("--vertical=")), None)
    paths = [Path(p) for p in args] or [Path.cwd()]
    dirs, meta = resolve_directories(paths)
    if vert:
        sel = select_for_vertical(dirs, vert)
        print(f"vertical={sel['vertical']}: deep-optimize={len(sel['deep_optimize'])}, full={len(sel['full'])}")
        print("  Step 4 (deep):", ", ".join(d["name"] for d in sel["deep_optimize"]))
        print("  Step 5 adds niche:", ", ".join(d["name"] for d in sel["full"] if d.get("vertical")==sel["vertical"]))
        sys.exit(0)
    print(json.dumps({"meta": meta, "sample": dict(list(dirs.items())[:3])}, indent=2))
    print(f"\nLoaded {meta['total']} directories · categories: {meta['by_category']}")
