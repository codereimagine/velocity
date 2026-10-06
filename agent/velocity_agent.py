#!/usr/bin/env python3
"""velocity-agent — localhost telemetry for the Velocity instrument.

Serves GET-only JSON on http://127.0.0.1:7717 (loopback ONLY, never the LAN):
  /health -> {"app":"velocity-agent","v":1}
  /rssi   -> {"dbm":-47,"unit":0.72,"source":"iw"}   (nulls when no WiFi)
  /flow   -> {"rx":<total bytes>,"tx":<total>,"ts":<epoch>}  (client computes rates)

Exposure note: ACAO:* lets any page the user visits read these (low-sensitivity,
read-only: agent-present, RSSI, cumulative byte counters). Host-header allowlist
blunts DNS-rebinding. Loopback bind keeps it off the LAN.

stdlib only. Security posture: binds loopback, GET-only (405 otherwise), fixed
routes (404 otherwise), no request data ever reaches a shell, subprocess args are
static lists, 3s command timeout, no logging of request bodies.
Run: python3 velocity_agent.py   ·   stop: Ctrl+C
"""
import json, platform, re, subprocess, time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

PORT = 7717

# ── pure parsers (unit-tested) ──────────────────────────────────────────────
def parse_netsh_signal(text):
    """Windows `netsh wlan show interfaces` -> approx dBm from Signal %."""
    m = re.search(r"Signal\s*:\s*(\d+)\s*%", text)
    if not m:
        return None
    return int(int(m.group(1)) / 2) - 100

def parse_iw_link(text):
    """Linux `iw dev <ifc> link` -> dBm."""
    m = re.search(r"signal:\s*(-?\d+)\s*dBm", text)
    return int(m.group(1)) if m else None

def parse_proc_net_dev(text, exclude=("lo",)):
    """Linux /proc/net/dev -> (rx_total, tx_total) across real interfaces."""
    rx = tx = 0
    for line in text.splitlines():
        if ":" not in line:
            continue
        name, rest = line.split(":", 1)
        if name.strip() in exclude:
            continue
        cols = rest.split()
        if len(cols) >= 9:
            rx += int(cols[0]); tx += int(cols[8])
    return rx, tx

def parse_pwsh_netstats(text):
    """`pwsh Get-NetAdapterStatistics` table -> (rx_total, tx_total)."""
    rx = tx = 0
    for line in text.splitlines():
        cols = line.split()
        if len(cols) >= 3 and cols[-1].isdigit() and cols[-2].isdigit():
            rx += int(cols[-2]); tx += int(cols[-1])
    return rx, tx

def rssi_to_unit(dbm):
    """-90 dBm -> 0.0 · -30 dBm -> 1.0, clamped."""
    if dbm is None:
        return None
    return max(0.0, min(1.0, (dbm + 90) / 60.0))

# ── collectors ──────────────────────────────────────────────────────────────
def _run(args):
    try:
        return subprocess.run(args, capture_output=True, text=True, timeout=3).stdout
    except Exception:
        return ""

def read_rssi():
    if platform.system() == "Windows":
        dbm = parse_netsh_signal(_run(["netsh", "wlan", "show", "interfaces"]))
        return dbm, "netsh"
    out = _run(["sh", "-c", "iw dev 2>/dev/null | awk '/Interface/{print $2}'"])
    for ifc in out.split():
        dbm = parse_iw_link(_run(["iw", "dev", ifc, "link"]))
        if dbm is not None:
            return dbm, "iw"
    return None, "none"

def read_flow():
    if platform.system() == "Windows":
        out = _run(["pwsh.exe", "-NoProfile", "-Command",
                    "Get-NetAdapterStatistics | Format-Table Name,ReceivedBytes,SentBytes"])
        return parse_pwsh_netstats(out)
    try:
        with open("/proc/net/dev", encoding="utf-8") as f:
            return parse_proc_net_dev(f.read())
    except OSError:
        return 0, 0

# ── server ──────────────────────────────────────────────────────────────────
class Handler(BaseHTTPRequestHandler):
    def _send(self, code, obj):
        body = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _host_ok(self):
        return self.headers.get("Host", "") in ("127.0.0.1:%d" % PORT, "localhost:%d" % PORT)

    def do_GET(self):
        if not self._host_ok():
            return self._send(403, {"err": "bad host"})   # DNS-rebinding defense
        if self.path == "/health":
            return self._send(200, {"app": "velocity-agent", "v": 1})
        if self.path == "/rssi":
            dbm, source = read_rssi()
            return self._send(200, {"dbm": dbm, "unit": rssi_to_unit(dbm), "source": source})
        if self.path == "/flow":
            rx, tx = read_flow()
            return self._send(200, {"rx": rx, "tx": tx, "ts": time.time()})
        return self._send(404, {"err": "unknown route"})

    def do_POST(self):  # GET-only surface
        return self._send(405, {"err": "GET only"})
    do_PUT = do_DELETE = do_PATCH = do_POST

    def log_message(self, *a):  # quiet; no request logging
        pass

if __name__ == "__main__":
    srv = ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
    print(f"velocity-agent on http://127.0.0.1:{PORT} (loopback only, Ctrl+C stops)")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
