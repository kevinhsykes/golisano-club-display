"""Serve the pages on a laptop and refresh prices every minute while the market is open.

For demos and internal club use only (the prices are a Yahoo Finance snapshot, which is
personal-use data). The cafe TV runs on the Cloudflare Worker with a licensed feed instead.

Run from the repo root:   python3 tools/demo_serve.py
Then open:                http://localhost:8765/tv.html        (full-screen TV view)
                          http://localhost:8765/index.html    (web view)
                          http://localhost:8765/board.html    (TradingView board)
Stop with Ctrl-C.
"""
import http.server
import subprocess
import sys
import threading
import time
from functools import partial
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 8765
REFRESH_SECONDS = 60


def refresh_loop():
    while True:
        try:
            subprocess.run([sys.executable, str(ROOT / "tools" / "snapshot_quotes.py")], check=True,
                           capture_output=True, text=True, timeout=120)
            print(time.strftime("%H:%M:%S"), "prices refreshed")
        except subprocess.CalledProcessError as e:
            print(time.strftime("%H:%M:%S"), "refresh failed; last good prices kept:", e.stderr.strip()[-200:])
        except Exception as e:  # network timeouts and the like
            print(time.strftime("%H:%M:%S"), "refresh failed; last good prices kept:", e)
        time.sleep(REFRESH_SECONDS)


class NoCache(http.server.SimpleHTTPRequestHandler):
    def end_headers(self):
        self.send_header("Cache-Control", "no-store")
        super().end_headers()

    def log_message(self, *a):  # keep the console readable
        pass


if __name__ == "__main__":
    threading.Thread(target=refresh_loop, daemon=True).start()
    handler = partial(NoCache, directory=str(ROOT / "web"))
    with http.server.ThreadingHTTPServer(("127.0.0.1", PORT), handler) as srv:
        print(f"serving http://localhost:{PORT}/tv.html  (Ctrl-C to stop)")
        srv.serve_forever()
