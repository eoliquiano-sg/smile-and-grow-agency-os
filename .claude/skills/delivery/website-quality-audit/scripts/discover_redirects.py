"""Discover legacy/redirected URLs by diffing GSC URLs against the live Ahrefs Site Audit crawl,
then HEAD-fetching each legacy URL to determine current status (301/302/404 etc) and redirect target.

This is the multi-agency-friendly approach for finding redirects: works with any tools the agency has
(Ahrefs + GSC) and doesn't require parsing host-specific config (Netlify _redirects, Apache .htaccess, etc).
"""

import json
import urllib.request
import urllib.error
from urllib.parse import urlparse
import concurrent.futures
import time

BASE = '/sessions/focused-relaxed-bell/mnt/test-workspace/clients/the-blueprint-training/wqa/audits/61d51437-577a-4e41-9181-a7aa45614692'
AHREFS_PAGES = f'{BASE}/tbt-ahrefs-pages.json'
GSC_DATA = f'{BASE}/tbt-gsc.json'
SF_CRAWL = '/sessions/focused-relaxed-bell/mnt/test-workspace/clients/the-blueprint-training/crawls/latest-crawl.json'
OUTPUT = f'{BASE}/tbt-legacy-urls.json'

def norm(u):
    if not u: return ""
    u = u.split('?')[0].split('#')[0].rstrip('/')
    return u.lower()

# Live URLs from Ahrefs Site Audit (pages only — not images/resources)
with open(AHREFS_PAGES) as f:
    ahrefs_pages = json.load(f)
live_urls_ahrefs = {norm(p['url']) for p in ahrefs_pages
                    if 'Page' in (p.get('page_type') or []) or 'Other' in (p.get('page_type') or [])}

# Live URLs from SF crawl
with open(SF_CRAWL) as f:
    sf_pages = json.load(f)['pages']
live_urls_sf = {norm(p['url']) for p in sf_pages if p.get('status_code') == 200}

# Combined live universe
live_universe = live_urls_ahrefs | live_urls_sf
print(f"Live URLs (Ahrefs Site Audit Pages+Other): {len(live_urls_ahrefs)}")
print(f"Live URLs (SF crawl 200 OK): {len(live_urls_sf)}")
print(f"Combined live universe: {len(live_universe)}")

# GSC URLs
with open(GSC_DATA) as f:
    gsc_rows = json.load(f)
gsc_urls = {norm(r['page']) for r in gsc_rows
            if 'theblueprint.training' in r['page']
            and not r['page'].endswith(('.png', '.jpg', '.jpeg', '.webp', '.svg', '.pdf', '.gif'))}
print(f"GSC TBT URLs (excluding assets): {len(gsc_urls)}")

# Diff: in GSC but not in live crawl = legacy
legacy_urls = gsc_urls - live_universe
print(f"Legacy URLs (in GSC, not in live crawl): {len(legacy_urls)}")

# We need full URLs (not normalized) to HEAD-fetch
gsc_full_by_norm = {norm(r['page']): r['page'] for r in gsc_rows
                    if 'theblueprint.training' in r['page']}
legacy_full = [gsc_full_by_norm[n] for n in legacy_urls if n in gsc_full_by_norm]
print(f"Legacy URLs to HEAD-fetch: {len(legacy_full)}")

# HEAD fetch each legacy URL
results = []
def fetch_status(url):
    try:
        # Use a custom opener that doesn't follow redirects
        class NoRedirect(urllib.request.HTTPRedirectHandler):
            def redirect_request(self, req, fp, code, msg, headers, newurl):
                return None
        opener = urllib.request.build_opener(NoRedirect)
        req = urllib.request.Request(url, method='HEAD',
                                      headers={'User-Agent': 'Mozilla/5.0 WQA-Audit/1.0'})
        try:
            resp = opener.open(req, timeout=10)
            return {'url': url, 'status': resp.status, 'final_url': url, 'redirect_target': None}
        except urllib.error.HTTPError as e:
            # 3xx returns here because we don't follow redirects
            if 300 <= e.code < 400:
                location = e.headers.get('Location', '')
                return {'url': url, 'status': e.code, 'final_url': None, 'redirect_target': location}
            return {'url': url, 'status': e.code, 'final_url': url, 'redirect_target': None}
    except urllib.error.URLError as e:
        return {'url': url, 'status': 'error', 'error': str(e), 'redirect_target': None}
    except Exception as e:
        return {'url': url, 'status': 'error', 'error': str(e)[:200], 'redirect_target': None}

print(f"\nHEAD-fetching {len(legacy_full)} legacy URLs (parallel, 10 workers)...")
start = time.time()
with concurrent.futures.ThreadPoolExecutor(max_workers=10) as ex:
    results = list(ex.map(fetch_status, legacy_full))
elapsed = time.time() - start
print(f"Done in {elapsed:.1f}s")

# Summarize by status
from collections import Counter
status_counts = Counter(r['status'] for r in results)
print(f"\nStatus distribution:")
for status, count in sorted(status_counts.items(), key=lambda x: -x[1] if isinstance(x[1], int) else 0):
    print(f"  {status}: {count}")

# Save full results
with open(OUTPUT, 'w') as f:
    json.dump(results, f, indent=2)
print(f"\nSaved: {OUTPUT}")

# Print first few redirects
redirects = [r for r in results if isinstance(r['status'], int) and 300 <= r['status'] < 400]
print(f"\nFirst 5 redirects:")
for r in redirects[:5]:
    print(f"  {r['status']}: {r['url']} -> {r['redirect_target']}")

errors = [r for r in results if isinstance(r['status'], int) and r['status'] >= 400]
print(f"\nFirst 5 errors:")
for r in errors[:5]:
    print(f"  {r['status']}: {r['url']}")
