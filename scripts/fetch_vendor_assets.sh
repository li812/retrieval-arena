#!/usr/bin/env bash
# Downloads the classic UI's vendored assets into backend/app/static/vendor/.
# The Dockerfile runs this at image build time; run it yourself only when serving the
# backend outside Docker. Works from any directory.
# Uses only Python's stdlib — no curl or wget required.
set -euo pipefail

export ARENA_REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

echo "[vendor] Fetching assets with Python urllib..."

python3 - <<'PYEOF'
import urllib.request
import re
import hashlib
import os
import sys

VENDOR = os.path.join(os.environ["ARENA_REPO_ROOT"], "backend", "app", "static", "vendor")
FONTS_DIR = os.path.join(VENDOR, "fonts")
os.makedirs(FONTS_DIR, exist_ok=True)

# Full Chrome UA so Google Fonts returns WOFF2 (not TTF/EOT fallbacks)
UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)


def download(url: str, dest: str) -> None:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req) as resp, open(dest, "wb") as f:
        f.write(resp.read())


def fetch_and_localize_font(family: str, weight_spec: str, out_name: str) -> None:
    url = f"https://fonts.googleapis.com/css2?family={family}:{weight_spec}&display=swap"
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    css = urllib.request.urlopen(req).read().decode()

    font_urls = sorted(set(re.findall(r"https://fonts\.gstatic\.com\S+?\.woff2", css)))
    for font_url in font_urls:
        fname = hashlib.md5(font_url.encode()).hexdigest()[:12] + ".woff2"
        local_path = os.path.join(FONTS_DIR, fname)
        download(font_url, local_path)
        css = css.replace(font_url, f"/static/vendor/fonts/{fname}")

    with open(os.path.join(FONTS_DIR, out_name), "w") as f:
        f.write(css)
    print(f"  wrote {out_name} ({len(font_urls)} font files)")


print("[vendor] Downloading Alpine.js...")
download(
    "https://cdn.jsdelivr.net/npm/alpinejs@3.14.8/dist/cdn.min.js",
    os.path.join(VENDOR, "alpine.min.js"),
)

print("[vendor] Downloading vis-network...")
download(
    "https://cdn.jsdelivr.net/npm/vis-network@9.1.9/standalone/umd/vis-network.min.js",
    os.path.join(VENDOR, "vis-network.min.js"),
)

print("[vendor] Downloading fonts...")
fetch_and_localize_font("JetBrains+Mono", "wght@400;500;700", "jetbrains-mono.css")
fetch_and_localize_font("Inter", "wght@400;500;600", "inter.css")

print(f"[vendor] Done. Assets in {VENDOR}/")
PYEOF
