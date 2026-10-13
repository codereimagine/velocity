#!/usr/bin/env python3
"""CI guard: the inline <script> sha256 must match the CSP script-src hash."""
import re, hashlib, base64, pathlib, sys
html = pathlib.Path("index.html").read_text(encoding="utf-8")
m = re.search(r"<script>([\s\S]*?)</script>", html)
if not m:
    sys.exit("no inline <script> found in index.html")
digest = base64.b64encode(hashlib.sha256(m.group(1).encode()).digest()).decode()
csp = re.search(r"script-src 'sha256-([A-Za-z0-9+/=]+)'", html)
if not csp:
    sys.exit("no sha256 hash in CSP script-src")
if csp.group(1) != digest:
    sys.exit(f"CSP hash mismatch: index={csp.group(1)} computed={digest}")
print("CSP sha256 OK:", digest)
