#!/usr/bin/env python3
"""publish_dashboard — push the rebuilt dashboard to the customer's chosen target.

Reads `data/agency.json` for the publishing config and routes to the right
adapter:

  - target=local    → already lives at agency-dashboard.html in the workspace
                      (nothing to upload). Returns the local path.
  - target=netlify  → POSTs a zip of the HTML to Netlify's deploy API.
  - target=vercel   → POSTs file payload to Vercel's deployment API.
  - target=drive    → Emits a structured request for the calling skill to
                      execute via the Google Drive MCP (Python can't call
                      MCPs directly). The skill picks up the request JSON
                      and runs the upload, then re-invokes this script with
                      --drive-already-uploaded to finalize.

Usage:
  python3 publish_dashboard.py --workspace-root .
  python3 publish_dashboard.py --workspace-root . --target netlify   # override
  python3 publish_dashboard.py --workspace-root . --dry-run          # plan only
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.request
import urllib.error
import zipfile
import io
import hashlib
from datetime import datetime, timezone
from typing import Optional


# ---------------------------------------------------------------------------
# Config loading
# ---------------------------------------------------------------------------

def load_agency_config(workspace_root: str) -> dict:
    path = os.path.join(workspace_root, "data", "agency.json")
    if not os.path.exists(path):
        sys.exit(f"ERROR: agency.json not found at {path}")
    return json.load(open(path))


def get_publishing_config(agency: dict, override_target: Optional[str] = None) -> tuple[str, dict]:
    pub = agency.get("publishing") or {}
    target = override_target or pub.get("target") or "local"
    if target not in ("local", "netlify", "vercel", "drive"):
        sys.exit(f"ERROR: unknown publishing target {target!r}")
    settings = pub.get(target) or {}
    return target, settings


# ---------------------------------------------------------------------------
# Adapter: local
# ---------------------------------------------------------------------------

def publish_local(workspace_root: str, settings: dict, html_source: str) -> dict:
    """Local mode is a no-op for the customer — the HTML is already at the
    output path from `build_agency_dashboard.py`. We just confirm it exists
    and return the absolute path so the calling skill can hand a `file://`
    URL to the user."""
    output_path = settings.get("output_path") or "./agency-dashboard.html"
    abs_path = os.path.abspath(os.path.join(workspace_root, output_path))
    if not os.path.exists(abs_path):
        return {"ok": False, "error": f"Dashboard file not found at {abs_path}. Run build_agency_dashboard.py first."}
    size = os.path.getsize(abs_path)
    return {
        "ok": True,
        "target": "local",
        "url": f"file://{abs_path}",
        "path": abs_path,
        "bytes": size,
        "note": "Local file ready. Share via Drive link or move to a static host for team access.",
    }


# ---------------------------------------------------------------------------
# Adapter: Netlify
# ---------------------------------------------------------------------------

def publish_netlify(settings: dict, html_source: str) -> dict:
    """Push the HTML to a Netlify site via the Deploys API.

    Netlify accepts a zip with the file at the root. We build the zip in
    memory and POST it to /api/v1/sites/{site_id}/deploys with the auth
    token as a Bearer header.

    Auth: personal access token at
      https://app.netlify.com/user/applications#personal-access-tokens
    Site ID: from the Netlify site's General settings page.
    """
    site_id = settings.get("site_id")
    token   = settings.get("auth_token")
    if not site_id or not token:
        return {"ok": False, "error": "netlify.site_id and netlify.auth_token are required in agency.json"}

    if not os.path.exists(html_source):
        return {"ok": False, "error": f"HTML file not found: {html_source}"}

    # Build zip in memory with index.html at the root.
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        with open(html_source, "rb") as f:
            zf.writestr("index.html", f.read())
    zip_bytes = buf.getvalue()

    url = f"https://api.netlify.com/api/v1/sites/{site_id}/deploys"
    req = urllib.request.Request(
        url, data=zip_bytes, method="POST",
        headers={
            "Content-Type": "application/zip",
            "Authorization": f"Bearer {token}",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            payload = json.loads(resp.read().decode())
        deploy_url = payload.get("deploy_ssl_url") or payload.get("ssl_url") or payload.get("url")
        return {
            "ok": True,
            "target": "netlify",
            "url": deploy_url,
            "deploy_id": payload.get("id"),
            "site_id": site_id,
            "state": payload.get("state"),
            "bytes": len(zip_bytes),
        }
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        return {"ok": False, "error": f"Netlify HTTP {e.code}: {body[:300]}"}
    except Exception as e:
        return {"ok": False, "error": f"Netlify upload failed: {e!r}"}


# ---------------------------------------------------------------------------
# Adapter: Vercel
# ---------------------------------------------------------------------------

def publish_vercel(settings: dict, html_source: str) -> dict:
    """Push the HTML to a Vercel project via the v13 Deployments API.

    Vercel's "create deployment" expects a list of files with SHA-1 content
    addresses. For a single HTML file, the simplest path is:

      1. POST /v2/files with the file bytes → get back the SHA
      2. POST /v13/deployments with name + files: [{file: "index.html", sha, size}]

    Auth: personal access token at https://vercel.com/account/tokens
    Project ID: from project settings.
    Team ID: optional, only for team accounts.
    """
    project_id = settings.get("project_id")
    token      = settings.get("auth_token")
    team_id    = settings.get("team_id")  # optional

    if not project_id or not token:
        return {"ok": False, "error": "vercel.project_id and vercel.auth_token are required in agency.json"}

    if not os.path.exists(html_source):
        return {"ok": False, "error": f"HTML file not found: {html_source}"}

    with open(html_source, "rb") as f:
        file_bytes = f.read()
    sha = hashlib.sha1(file_bytes).hexdigest()

    qs = f"?teamId={team_id}" if team_id else ""

    # Step 1: upload file content
    try:
        req = urllib.request.Request(
            f"https://api.vercel.com/v2/files{qs}",
            data=file_bytes,
            method="POST",
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/octet-stream",
                "x-vercel-digest": sha,
            },
        )
        with urllib.request.urlopen(req, timeout=60) as resp:
            _ = resp.read()
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        return {"ok": False, "error": f"Vercel file upload failed HTTP {e.code}: {body[:300]}"}
    except Exception as e:
        return {"ok": False, "error": f"Vercel file upload failed: {e!r}"}

    # Step 2: create deployment
    body = {
        "name": f"agency-os-{int(time.time())}",
        "project": project_id,
        "target": "production",
        "files": [{"file": "index.html", "sha": sha, "size": len(file_bytes)}],
        "projectSettings": {"framework": None},
    }
    try:
        req = urllib.request.Request(
            f"https://api.vercel.com/v13/deployments{qs}",
            data=json.dumps(body).encode(),
            method="POST",
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            },
        )
        with urllib.request.urlopen(req, timeout=60) as resp:
            payload = json.loads(resp.read().decode())
        return {
            "ok": True,
            "target": "vercel",
            "url": f"https://{payload.get('url')}" if payload.get("url") else None,
            "deploy_id": payload.get("id"),
            "state": payload.get("readyState"),
            "bytes": len(file_bytes),
        }
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        return {"ok": False, "error": f"Vercel deploy failed HTTP {e.code}: {body[:300]}"}
    except Exception as e:
        return {"ok": False, "error": f"Vercel deploy failed: {e!r}"}


# ---------------------------------------------------------------------------
# Adapter: Drive (emit-plan only; calling skill handles MCP upload)
# ---------------------------------------------------------------------------

def publish_drive_plan(settings: dict, html_source: str) -> dict:
    """Drive uploads happen via the Google Drive MCP, which Python can't
    call. This adapter emits a structured request — the calling skill
    reads it and invokes the MCP, then optionally calls this script back
    with --drive-already-uploaded to record the resulting Drive URL.
    """
    folder_id = settings.get("folder_id")
    if not folder_id:
        return {"ok": False, "error": "drive.folder_id is required in agency.json"}
    if not os.path.exists(html_source):
        return {"ok": False, "error": f"HTML file not found: {html_source}"}

    return {
        "ok": True,
        "target": "drive",
        "action_required": "mcp_upload",
        "mcp_call": {
            "tool": "create_file",
            "title": f"agency-dashboard - {datetime.now(timezone.utc).strftime('%Y-%m-%d %H%M')}.html",
            "parentId": folder_id,
            "contentMimeType": "text/html",
            "source_file": os.path.abspath(html_source),
            "_note": (
                "Read the HTML file, base64-encode it, and pass as base64Content. "
                "Large files (>1MB) may exceed MCP arg limits — use a subagent in "
                "that case (see SHEETS_SYNC_RUNBOOK.md for the pattern)."
            ),
        },
        "note": "Plan emitted. Calling skill should now invoke the Drive MCP to perform the upload.",
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--workspace-root", default=".")
    p.add_argument("--html", default=None,
                   help="Path to the dashboard HTML. Defaults to "
                        "publishing.local.output_path from agency.json.")
    p.add_argument("--target", default=None, choices=["local", "netlify", "vercel", "drive"],
                   help="Override the publishing.target in agency.json")
    p.add_argument("--dry-run", action="store_true",
                   help="Print the plan without actually publishing")
    args = p.parse_args()

    agency = load_agency_config(args.workspace_root)
    target, settings = get_publishing_config(agency, override_target=args.target)

    # Resolve HTML source
    if args.html:
        html_source = args.html
    else:
        local_cfg = (agency.get("publishing") or {}).get("local") or {}
        html_rel  = local_cfg.get("output_path") or "./agency-dashboard.html"
        html_source = os.path.join(args.workspace_root, html_rel)

    plan = {
        "target": target,
        "html_source": os.path.abspath(html_source),
        "settings_present": bool(settings),
    }
    if args.dry_run:
        print(json.dumps(plan, indent=2))
        return

    # Dispatch
    if target == "local":
        result = publish_local(args.workspace_root, settings, html_source)
    elif target == "netlify":
        result = publish_netlify(settings, html_source)
    elif target == "vercel":
        result = publish_vercel(settings, html_source)
    elif target == "drive":
        result = publish_drive_plan(settings, html_source)
    else:
        result = {"ok": False, "error": f"unknown target {target!r}"}

    result["published_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    print(json.dumps(result, indent=2))
    sys.exit(0 if result.get("ok") else 1)


if __name__ == "__main__":
    main()
