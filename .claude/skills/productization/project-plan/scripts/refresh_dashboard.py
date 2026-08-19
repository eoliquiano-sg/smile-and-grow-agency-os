#!/usr/bin/env python3
"""refresh_dashboard — one-shot orchestrator for the customer's ongoing PM loop.

What this does (in order):

  1. `pull_sheets.py --emit-plan` → manifest of sheets to refresh
     ⚠ Sheet fetching happens via the Google Drive MCP, so the calling
       skill must execute that step. This script emits the plan and
       expects the markdown payloads to already be on disk before it
       runs the cache write.
  2. `pull_sheets.py --from-markdown` → parse + cache writes
  3. (TODO) pull_analytics step — see SHEETS_SYNC_RUNBOOK.md for the
     pattern. For now this script just notes the gap and continues.
  4. `build_agency_dashboard.py` → regenerate the HTML
  5. `publish_dashboard.py` → push to configured target

Usage:
  python3 refresh_dashboard.py --workspace-root .
  python3 refresh_dashboard.py --workspace-root . --skip-sheets
  python3 refresh_dashboard.py --workspace-root . --target netlify
  python3 refresh_dashboard.py --workspace-root . --dry-run

This is meant to be invoked either:
  - On a schedule via the Cowork scheduled-tasks MCP (recurring job)
  - On-demand by the strategist via the `/refresh-dashboard` skill
  - From the partner's CI/cron if the customer self-hosts
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime, timezone

SCRIPTS_DIR = os.path.dirname(os.path.abspath(__file__))


def run(cmd: list[str], *, dry: bool, label: str) -> tuple[int, str, str]:
    """Run a subprocess and return (returncode, stdout, stderr)."""
    print(f"\n▶ {label}")
    print(f"  $ {' '.join(cmd)}")
    if dry:
        print("  (dry-run — skipped)")
        return 0, "", ""
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.stdout:
        # Echo tail (don't blow up the log on huge outputs)
        tail = "\n".join(result.stdout.splitlines()[-15:])
        print(f"  stdout (tail):\n{tail}")
    if result.stderr and result.returncode != 0:
        print(f"  stderr:\n{result.stderr[:500]}")
    return result.returncode, result.stdout, result.stderr


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--workspace-root", default=".")
    p.add_argument("--skip-sheets", action="store_true",
                   help="Skip sheets-sync step (use when sheets caches are already fresh).")
    p.add_argument("--skip-analytics", action="store_true",
                   help="Skip analytics-pull step.")
    p.add_argument("--markdown-dir", default=None,
                   help="Directory where the calling skill has already placed the .tsv/.md "
                        "payloads from the Drive MCP. Required for the sheets-sync write step "
                        "unless --skip-sheets is set.")
    p.add_argument("--target", default=None, choices=["local", "netlify", "vercel", "drive"],
                   help="Override publishing.target in agency.json")
    p.add_argument("--dry-run", action="store_true",
                   help="Print the plan without executing any subprocess")
    args = p.parse_args()

    started = datetime.now(timezone.utc).isoformat(timespec="seconds")
    summary = {"started_at": started, "steps": []}
    overall_ok = True

    # ----- Step 1 + 2: sheets sync -----
    if args.skip_sheets:
        summary["steps"].append({"step": "sheets-sync", "skipped": True})
    else:
        # Step 1: emit plan
        rc, out, err = run(
            ["python3", os.path.join(SCRIPTS_DIR, "pull_sheets.py"),
             "--workspace-root", args.workspace_root, "--emit-plan"],
            dry=args.dry_run, label="sheets-sync: emit plan",
        )
        if rc != 0 and not args.dry_run:
            overall_ok = False
            summary["steps"].append({"step": "sheets-emit-plan", "ok": False, "error": err[:300]})
        else:
            summary["steps"].append({"step": "sheets-emit-plan", "ok": True})

            # Step 2: write caches from markdown payloads.
            # NOTE: this requires the calling skill to have already
            # pulled each sheet via the Drive MCP and dropped the
            # payloads in --markdown-dir. If the dir is missing or
            # empty, we skip with a warning so the rest of the loop
            # can still run.
            md_dir = args.markdown_dir
            if md_dir and (args.dry_run or os.path.isdir(md_dir)):
                rc2, out2, err2 = run(
                    ["python3", os.path.join(SCRIPTS_DIR, "pull_sheets.py"),
                     "--workspace-root", args.workspace_root,
                     "--from-markdown", md_dir],
                    dry=args.dry_run, label="sheets-sync: write caches from markdown",
                )
                if rc2 != 0 and not args.dry_run:
                    overall_ok = False
                    summary["steps"].append({"step": "sheets-from-markdown", "ok": False, "error": err2[:300]})
                else:
                    summary["steps"].append({"step": "sheets-from-markdown", "ok": True})
            else:
                msg = ("No --markdown-dir provided. Calling skill must pull sheets via "
                       "Drive MCP and provide the payloads. Skipping cache write.")
                print(f"  ⚠ {msg}")
                summary["steps"].append({"step": "sheets-from-markdown", "skipped": True, "reason": msg})

    # ----- Step 3: analytics (placeholder for the partner) -----
    if args.skip_analytics:
        summary["steps"].append({"step": "analytics-pull", "skipped": True})
    else:
        # TODO(partner): implement pull_analytics.py following the
        # sheets-sync pattern. For now, just check whether at least one
        # cache exists per client and warn if not.
        clients_path = os.path.join(args.workspace_root, "data", "clients.json")
        if os.path.exists(clients_path):
            clients = json.load(open(clients_path))
            for c in clients:
                from_slug = (c.get("custom_fields") or {}).get("slug") or \
                            "".join(ch if ch.isalnum() or ch == "-" else "-"
                                    for ch in (c.get("company_name") or "").lower()).strip("-")
                cache_dir = os.path.join(args.workspace_root, "clients", from_slug, "analytics")
                exists = os.path.isdir(cache_dir) and any(
                    f.endswith(".json") for f in os.listdir(cache_dir)
                )
                if not exists:
                    print(f"  ⚠ No analytics caches for {c.get('company_name')!r} — "
                          f"Reporting tab will show 'Not Connected'.")
        summary["steps"].append({
            "step": "analytics-pull",
            "skipped": True,
            "reason": "pull_analytics.py not yet implemented — see WALKTHROUGH_GAPS.md GAP #22b. "
                      "Analytics caches must be populated out-of-band until that ships.",
        })

    # ----- Step 4: rebuild dashboard -----
    pub_cfg = {}
    try:
        agency = json.load(open(os.path.join(args.workspace_root, "data", "agency.json")))
        pub_cfg = (agency.get("publishing") or {}).get("local") or {}
    except Exception:
        pass
    output_path = pub_cfg.get("output_path") or "./agency-dashboard.html"

    rc, out, err = run(
        ["python3", os.path.join(SCRIPTS_DIR, "build_agency_dashboard.py"),
         "--workspace-root", args.workspace_root,
         "--output", output_path],
        dry=args.dry_run, label="rebuild: build_agency_dashboard.py",
    )
    if rc != 0 and not args.dry_run:
        overall_ok = False
        summary["steps"].append({"step": "build", "ok": False, "error": err[:300]})
        print(json.dumps(summary, indent=2))
        sys.exit(1)
    summary["steps"].append({"step": "build", "ok": True})

    # ----- Step 5: publish -----
    pub_args = ["python3", os.path.join(SCRIPTS_DIR, "publish_dashboard.py"),
                "--workspace-root", args.workspace_root]
    if args.target:
        pub_args += ["--target", args.target]
    rc, out, err = run(pub_args, dry=args.dry_run, label="publish: publish_dashboard.py")
    if rc != 0 and not args.dry_run:
        overall_ok = False
        summary["steps"].append({"step": "publish", "ok": False, "error": err[:300]})
    else:
        # Pull the publish_dashboard.py output to surface the deploy URL
        publish_result = {}
        try:
            # publish_dashboard prints JSON
            publish_result = json.loads(out.split("\n")[-1] if not args.dry_run else "{}") if out else {}
        except Exception:
            pass
        summary["steps"].append({
            "step": "publish",
            "ok": True,
            "url": publish_result.get("url"),
            "target": publish_result.get("target"),
        })

    # ----- Final summary -----
    summary["finished_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    summary["ok"] = overall_ok
    print("\n" + "=" * 60)
    print(json.dumps(summary, indent=2))
    sys.exit(0 if overall_ok else 1)


if __name__ == "__main__":
    main()
