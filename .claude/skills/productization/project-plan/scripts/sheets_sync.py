#!/usr/bin/env python3
"""sheets_sync — parse + cache content workbook and central link DB.

ARCHITECTURE
============
Sheets are the SOURCE OF TRUTH for content and link tracking.
This module is a READ-ONLY mirror layer:

  1. An out-of-band orchestrator (Claude via the Google Drive MCP, or a
     headless cron job hitting the Sheets API) calls
     `read_file_content` on the sheet and gets a Markdown-formatted table.
  2. That raw markdown is handed to `parse_content_workbook()` or
     `parse_link_db()` here, which returns a list of normalized row dicts.
  3. The result is written to a cache file at
     `clients/{slug}/sheets-cache/{content_workbook,link_db}.json`
     via `save_cache()`.
  4. `build_agency_dashboard.py` calls `load_cache()` at build time to
     pull the data and render it in the Content + Links tabs.

The build script NEVER calls the MCP itself — it only reads caches.
This keeps builds fast, deterministic, and runnable offline.

CACHE SHAPE
===========
content_workbook.json:
  {
    "last_synced_at": "2026-06-07T14:35:00Z",
    "sheet_id": "14nfw6...",
    "sheet_url": "https://docs.google.com/spreadsheets/d/14nfw6.../edit",
    "row_count": 12,
    "rows": [
      {"status": "Ready For Upload", "client_feedback": "Pending Approval",
       "start_date": "", "published_date": "",
       "draft_url": "https://docs.google.com/document/...",
       "main_kw": "tampa personal injury lawyer", "search_volume": "3,300",
       "page_type": "Service Detail", "new_or_rewrite": "Rewrite",
       "notes": "", "published_url": "https://www.ligorilaw.com/..."},
      ...
    ]
  }

link_db.json (one per client, filtered by client name):
  {
    "last_synced_at": "2026-06-07T14:35:00Z",
    "sheet_id": "1noOD...",
    "sheet_url": "https://docs.google.com/spreadsheets/d/1noOD.../edit",
    "client_filter": "Blueprint",
    "row_count": 234,
    "rows": [
      {"status": "8. Live", "client": "Blueprint", "date": "1/28/2019",
       "link_type": "Vendor", "niche": "Marketing",
       "domain": "blogs.uwa.edu.au", "cost": "$80",
       "live_url": "https://...", "target_page": "https://theblueprint.training/",
       "anchor": "SEO blueprint"},
      ...
    ]
  }
"""

from __future__ import annotations

import json
import os
import re
from datetime import datetime, timezone
from typing import Optional


# ---------------------------------------------------------------------------
# Markdown-table parsing
# ---------------------------------------------------------------------------

def _unescape_cell(cell: str) -> str:
    """Unescape a cell value from the MCP read_file_content output.

    Handles:
      - Backslash-escaped underscores: `\\_` -> `_`
      - HTML entity newlines in headers: `&#10;` -> ` `
      - Leading/trailing whitespace
    """
    if cell is None:
        return ""
    s = str(cell)
    # The MCP escapes underscores with backslashes (especially in URLs/IDs)
    s = s.replace(r"\_", "_").replace(r"\*", "*")
    # Headers occasionally contain embedded HTML-entity newlines (e.g.
    # "Search &#10;Volume" when the original sheet header wraps)
    s = s.replace("&#10;", " ").replace("&amp;", "&")
    # Collapse runs of whitespace
    s = re.sub(r"\s+", " ", s).strip()
    return s


def parse_markdown_table(md: str) -> list[dict]:
    """Parse a Markdown pipe-delimited table into a list of row dicts.

    Expected shape (as emitted by the Google Drive MCP read_file_content):

        | Col A | Col B | Col C |
        | :-: | :-: | :-: |
        | row1a | row1b | row1c |
        | row2a |  | row2c |

    The second row is the alignment marker and is skipped.

    Returns [] if the input doesn't look like a table.
    """
    if not md:
        return []

    # Sometimes the MCP wraps content in fenced code blocks or prefixes a
    # heading. Trim non-table lines from the top.
    lines = [ln.rstrip() for ln in md.split("\n")]
    table_lines = []
    started = False
    for ln in lines:
        stripped = ln.strip()
        if stripped.startswith("|") and stripped.endswith("|"):
            table_lines.append(stripped)
            started = True
        elif started:
            # Once the table starts, stop at the first non-pipe line.
            break

    if len(table_lines) < 2:
        return []

    def split_row(row: str) -> list[str]:
        # Strip leading/trailing pipes, split on '|'
        inner = row.strip().strip("|")
        return [_unescape_cell(c) for c in inner.split("|")]

    headers = split_row(table_lines[0])
    # Row 1 is the alignment marker (`:-:` etc) — skip it.
    data_rows = [split_row(r) for r in table_lines[2:]]

    out = []
    for row in data_rows:
        # Pad/truncate to header length
        if len(row) < len(headers):
            row = row + [""] * (len(headers) - len(row))
        elif len(row) > len(headers):
            row = row[: len(headers)]
        # All-empty rows are noise — skip them
        if not any(cell for cell in row):
            continue
        out.append(dict(zip(headers, row)))
    return out


def parse_tsv(tsv: str) -> list[dict]:
    """Parse a tab-separated-values dump into a list of row dicts.

    The Google Drive `download_file_content` MCP returns a base64-encoded
    full export of a sheet — TSV is preferred over CSV because the data
    contains commas (search volumes like "3,300", anchor text with commas)
    but no tabs.

    Unlike `parse_markdown_table`, TSV is the FULL sheet — the
    `read_file_content` MCP truncates large sheets at ~60 KB and is only
    suitable for small workbooks.
    """
    if not tsv:
        return []
    lines = tsv.split("\n")
    # Drop trailing empty lines but preserve internal blanks (TSV doesn't
    # have an alignment marker row to skip).
    while lines and not lines[-1].strip():
        lines.pop()
    if len(lines) < 2:
        return []
    headers = [_unescape_cell(c) for c in lines[0].split("\t")]
    out = []
    for raw in lines[1:]:
        # Skip wholly-empty lines (some exports have blanks between
        # sections, especially after table breaks)
        if not raw.strip():
            continue
        cells = [_unescape_cell(c) for c in raw.split("\t")]
        if len(cells) < len(headers):
            cells = cells + [""] * (len(headers) - len(cells))
        elif len(cells) > len(headers):
            cells = cells[: len(headers)]
        if not any(c for c in cells):
            continue
        out.append(dict(zip(headers, cells)))
    return out


def parse_sheet_export(raw: str) -> list[dict]:
    """Auto-detect TSV vs Markdown table and parse accordingly.

    Heuristic: if any of the first 5 lines contain a tab character,
    treat as TSV. Otherwise fall back to markdown-table parsing.
    """
    if not raw:
        return []
    head = "\n".join(raw.split("\n", 5)[:5])
    if "\t" in head:
        return parse_tsv(raw)
    return parse_markdown_table(raw)


# ---------------------------------------------------------------------------
# Content workbook
# ---------------------------------------------------------------------------

# Map of {normalized header text from sheet}: {normalized field name in cache}
CONTENT_HEADER_MAP = {
    "status": "status",
    "client feedback": "client_feedback",
    "start date": "start_date",
    "published date": "published_date",
    "draft": "draft_url",
    "main kw/topic": "main_kw",
    "search volume": "search_volume",
    "page type": "page_type",
    "new or rewrite?": "new_or_rewrite",
    "notes": "notes",
    "published url": "published_url",
}


def parse_content_workbook(raw: str) -> list[dict]:
    """Parse a content workbook from either markdown-table or TSV.

    Returns a list of normalized row dicts keyed by snake_case field names.
    Unknown columns are preserved with a `unknown__{header_lower}` prefix.
    """
    raw_rows = parse_sheet_export(raw)
    out = []
    for raw in raw_rows:
        normalized = {}
        for header, value in raw.items():
            key = CONTENT_HEADER_MAP.get(header.lower().strip())
            if key:
                normalized[key] = value
            else:
                normalized[f"unknown__{header.lower().strip()}"] = value
        # Backfill expected keys that were missing from the source
        for expected in CONTENT_HEADER_MAP.values():
            normalized.setdefault(expected, "")
        out.append(normalized)
    return out


def content_status_class(status: str) -> str:
    """Map a content workbook status string to a CSS class hint.

    The workbook uses free-form labels ("Ready For Upload", "Writing In
    Progress", "Live", "Published", etc.) — bucket them into 4 visual
    groups for the dashboard.
    """
    s = (status or "").lower().strip()
    if not s:
        return "status-empty"
    if "live" in s or "published" in s:
        return "status-live"
    if "ready" in s or "approved" in s or "scheduled" in s:
        return "status-ready"
    if "writing" in s or "progress" in s or "draft" in s:
        return "status-working"
    if "reject" in s or "hold" in s or "dead" in s:
        return "status-blocked"
    return "status-other"


def is_content_live(row: dict) -> bool:
    """Decide whether a content row counts as 'Live' for overview counts.

    Live = has a Published Date OR Status contains 'live'/'published'.
    """
    if (row.get("published_date") or "").strip():
        return True
    status = (row.get("status") or "").lower()
    return "live" in status or "published" in status


# ---------------------------------------------------------------------------
# Central link DB
# ---------------------------------------------------------------------------

LINK_HEADER_MAP = {
    "status": "status",
    "client": "client",
    "date": "date",
    "link type": "link_type",
    "niche": "niche",
    "domain (no http or www)": "domain",
    "domain": "domain",
    "cost": "cost",
    "live article url": "live_url",
    "target page": "target_page",
    "anchor text": "anchor",
}


def parse_link_db(raw: str, client_filter: Optional[str] = None) -> list[dict]:
    """Parse the central link DB from either markdown-table or TSV.

    If `client_filter` is provided, returns only rows whose `client` value
    matches (case-insensitive, with surrounding whitespace stripped).
    """
    raw_rows = parse_sheet_export(raw)
    out = []
    cf = (client_filter or "").strip().lower()
    for raw in raw_rows:
        normalized = {}
        for header, value in raw.items():
            key = LINK_HEADER_MAP.get(header.lower().strip())
            if key:
                normalized[key] = value
            else:
                normalized[f"unknown__{header.lower().strip()}"] = value
        for expected in set(LINK_HEADER_MAP.values()):
            normalized.setdefault(expected, "")
        # Filter by client name if requested
        if cf and (normalized.get("client") or "").strip().lower() != cf:
            continue
        out.append(normalized)
    return out


def link_status_bucket(status: str) -> str:
    """Bucket a link status string for dashboard display.

    Pipeline statuses observed in the link DB:
      1. Reply Pending   -> outreach
      3. Offered Price   -> outreach
      6. Sent Draft      -> in-flight
      7. Publish Scheduled -> in-flight
      8. Live            -> live
      9. Article Rejected -> dead
      10. Dead           -> dead
    """
    s = (status or "").strip().lower()
    if not s:
        return "unknown"
    if "live" in s:
        return "live"
    if "reject" in s or "dead" in s:
        return "dead"
    if "draft" in s or "scheduled" in s:
        return "in_flight"
    if "reply" in s or "offered" in s or "pending" in s:
        return "outreach"
    return "other"


def is_link_live(row: dict) -> bool:
    """A link row counts as Live if its status starts with '8. Live' or
    contains the word 'live'."""
    return link_status_bucket(row.get("status", "")) == "live"


# ---------------------------------------------------------------------------
# Cache I/O
# ---------------------------------------------------------------------------

def _cache_dir(workspace_root: str, slug: str) -> str:
    return os.path.join(workspace_root, "clients", slug, "sheets-cache")


def _cache_path(workspace_root: str, slug: str, kind: str) -> str:
    return os.path.join(_cache_dir(workspace_root, slug), f"{kind}.json")


def save_content_workbook_cache(
    workspace_root: str,
    slug: str,
    sheet_id: str,
    rows: list[dict],
) -> str:
    """Write the parsed content workbook to the cache. Returns path."""
    cache_dir = _cache_dir(workspace_root, slug)
    os.makedirs(cache_dir, exist_ok=True)
    payload = {
        "last_synced_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "sheet_id": sheet_id,
        "sheet_url": f"https://docs.google.com/spreadsheets/d/{sheet_id}/edit",
        "row_count": len(rows),
        "rows": rows,
    }
    path = _cache_path(workspace_root, slug, "content_workbook")
    with open(path, "w") as f:
        json.dump(payload, f, indent=2)
    return path


def save_link_db_cache(
    workspace_root: str,
    slug: str,
    sheet_id: str,
    client_filter: str,
    rows: list[dict],
) -> str:
    """Write the parsed (and client-filtered) link DB rows to the cache."""
    cache_dir = _cache_dir(workspace_root, slug)
    os.makedirs(cache_dir, exist_ok=True)
    payload = {
        "last_synced_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "sheet_id": sheet_id,
        "sheet_url": f"https://docs.google.com/spreadsheets/d/{sheet_id}/edit",
        "client_filter": client_filter,
        "row_count": len(rows),
        "rows": rows,
    }
    path = _cache_path(workspace_root, slug, "link_db")
    with open(path, "w") as f:
        json.dump(payload, f, indent=2)
    return path


def load_content_workbook_cache(workspace_root: str, slug: str) -> Optional[dict]:
    """Read the content workbook cache. Returns None if missing."""
    path = _cache_path(workspace_root, slug, "content_workbook")
    if not os.path.exists(path):
        return None
    try:
        with open(path) as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return None


def load_link_db_cache(workspace_root: str, slug: str) -> Optional[dict]:
    """Read the per-client link DB cache. Returns None if missing."""
    path = _cache_path(workspace_root, slug, "link_db")
    if not os.path.exists(path):
        return None
    try:
        with open(path) as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return None


def cache_freshness_label(cache: Optional[dict]) -> str:
    """Human-friendly 'Last synced X ago' label for the dashboard banner."""
    if not cache or "last_synced_at" not in cache:
        return "Never synced"
    try:
        synced = datetime.fromisoformat(cache["last_synced_at"].replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return cache.get("last_synced_at", "Unknown")
    now = datetime.now(timezone.utc)
    if synced.tzinfo is None:
        synced = synced.replace(tzinfo=timezone.utc)
    delta = now - synced
    secs = int(delta.total_seconds())
    if secs < 60:
        return "Synced just now"
    if secs < 3600:
        return f"Synced {secs // 60} min ago"
    if secs < 86400:
        return f"Synced {secs // 3600} hr ago"
    days = secs // 86400
    return f"Synced {days} day{'s' if days != 1 else ''} ago"


# ---------------------------------------------------------------------------
# CLI for manual cache population (testing only)
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import argparse
    import sys

    parser = argparse.ArgumentParser(
        description="Parse a sheets markdown file and write the cache. "
                    "Useful for testing parsing without invoking the MCP."
    )
    parser.add_argument("--kind", choices=["content", "links"], required=True)
    parser.add_argument("--markdown-file", required=True,
                        help="Path to a file containing the raw markdown table")
    parser.add_argument("--workspace-root", default=".")
    parser.add_argument("--client-slug", required=True)
    parser.add_argument("--sheet-id", required=True)
    parser.add_argument("--client-filter", default=None,
                        help="(links only) client name to filter on")
    args = parser.parse_args()

    with open(args.markdown_file) as f:
        md = f.read()

    if args.kind == "content":
        rows = parse_content_workbook(md)
        out_path = save_content_workbook_cache(
            args.workspace_root, args.client_slug, args.sheet_id, rows
        )
        print(f"Parsed {len(rows)} content rows -> {out_path}", file=sys.stderr)
    else:
        if not args.client_filter:
            print("--client-filter is required for links", file=sys.stderr)
            sys.exit(2)
        rows = parse_link_db(md, client_filter=args.client_filter)
        out_path = save_link_db_cache(
            args.workspace_root, args.client_slug, args.sheet_id,
            args.client_filter, rows
        )
        print(f"Parsed {len(rows)} link rows for '{args.client_filter}' -> {out_path}",
              file=sys.stderr)
