"""
Upstox OAuth + Angel One auto-login
Both brokers on one Railway URL page.
"""
import os
import time
import json
import pyotp
import requests
import threading
import schedule
import pytz
from datetime import datetime
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs

IST = pytz.timezone("Asia/Kolkata")

# ──────────────────── Upstox config ────────────────────
UPSTOX_CLIENT_ID     = os.environ.get("UPSTOX_CLIENT_ID", "")
UPSTOX_CLIENT_SECRET = os.environ.get("UPSTOX_CLIENT_SECRET", "")
UPSTOX_REDIRECT_URI  = os.environ.get("UPSTOX_REDIRECT_URI",
                        "https://trading-bot-production-65cd.up.railway.app/callback")
UPSTOX_MOBILE        = os.environ.get("UPSTOX_MOBILE", "")
UPSTOX_PIN           = os.environ.get("UPSTOX_PIN", "")
UPSTOX_TOTP_SECRET   = os.environ.get("UPSTOX_TOTP_SECRET", "")

# ──────────────────── Shared state ─────────────────────
upstox_token   = None   # set when OAuth completes
angel_status   = {"logged_in": False, "login_time": None, "error": None}
_angel_broker  = None   # set by main.py via set_angel_broker()

token_callbacks = []  # functions to call when Upstox token arrives

def set_angel_broker(broker):
    global _angel_broker
    _angel_broker = broker

def get_upstox_token():
    return upstox_token

def on_token(callback):
    token_callbacks.append(callback)

# ──────────────────── Upstox auto-login ─────────────────
def attempt_upstox_auto_login():
    """Try automated Upstox login (often fails with 400 — user must login manually)."""
    global upstox_token
    print("[AUTH] Attempting automated Upstox login...")
    try:
        totp = pyotp.TOTP(UPSTOX_TOTP_SECRET).now()
        print("[AUTH] TOTP generated: {}".format(totp))

        # Step 1: Get auth code
        session = requests.Session()
        login_resp = session.post(
            "https://api.upstox.com/v2/login/authorization/dialog",
            data={
                "mobile_num":  UPSTOX_MOBILE,
                "mpin":        UPSTOX_PIN,
                "totp":        totp,
                "source":      "WEB",
                "client_id":   UPSTOX_CLIENT_ID,
                "redirect_uri": UPSTOX_REDIRECT_URI,
                "response_type": "code",
                "state":       "intra-gini",
            },
            allow_redirects=False,
            timeout=15
        )
        print("[AUTH] Auto-login response: {}".format(login_resp.status_code))
        if login_resp.status_code in (200, 302):
            location = login_resp.headers.get("Location", "")
            if "code=" in location:
                code = parse_qs(urlparse(location).query).get("code", [None])[0]
                if code:
                    return exchange_upstox_code(code)
        print("[AUTH] Auto-login failed — please login manually at the web URL")
        return False
    except Exception as e:
        print("[AUTH] Auto-login error: {}".format(e))
        return False


def exchange_upstox_code(code):
    global upstox_token
    try:
        resp = requests.post(
            "https://api.upstox.com/v2/login/authorization/token",
            data={
                "code":          code,
                "client_id":     UPSTOX_CLIENT_ID,
                "client_secret": UPSTOX_CLIENT_SECRET,
                "redirect_uri":  UPSTOX_REDIRECT_URI,
                "grant_type":    "authorization_code",
            },
            timeout=15
        )
        data = resp.json()
        token = data.get("access_token")
        if token:
            upstox_token = token
            print("[AUTH] ✅ Upstox token received!")
            for cb in token_callbacks:
                try:
                    cb(token)
                except Exception as e:
                    print("[AUTH] Callback error: {}".format(e))
            return True
        print("[AUTH] Token exchange failed: {}".format(data))
        return False
    except Exception as e:
        print("[AUTH] Token exchange error: {}".format(e))
        return False

# ──────────────────── HTML Page ─────────────────────────
def _build_html():
    now_ist = datetime.now(IST).strftime("%H:%M:%S IST")

    # Upstox status
    if upstox_token:
        upstox_badge = '<span class="badge badge-green">✅ LOGGED IN</span>'
        upstox_note  = '<p class="note">Upstox is active. Bot is trading with real orders.</p>'
        upstox_btn   = '<a class="btn btn-secondary" href="{}">Re-login Upstox</a>'.format(_upstox_auth_url())
    else:
        upstox_badge = '<span class="badge badge-red">❌ NOT LOGGED IN</span>'
        upstox_note  = '<p class="note warning">⚠️ Upstox needs manual login below. Bot is in paper mode until logged in.</p>'
        upstox_btn   = '<a class="btn btn-primary" href="{}">🔐 Login to Upstox</a>'.format(_upstox_auth_url())

    # Angel One status
    if _angel_broker and _angel_broker.logged_in:
        angel_badge = '<span class="badge badge-green">✅ AUTO-LOGGED IN</span>'
        angel_note  = '<p class="note">Angel One logged in at {}. Auto-login active — no action needed.</p>'.format(
            _angel_broker.login_time.strftime("%H:%M IST") if _angel_broker.login_time else "?")
        angel_btn   = '<button class="btn btn-secondary" onclick="reloginAngel()">🔄 Re-login Angel One</button>'
    else:
        err = angel_status.get("error", "Auto-login pending...")
        angel_badge = '<span class="badge badge-yellow">⏳ PENDING</span>'
        angel_note  = '<p class="note warning">Angel One: {}. Will auto-login at startup.</p>'.format(err)
        angel_btn   = '<button class="btn btn-primary" onclick="reloginAngel()">🔄 Try Angel One Login</button>'

    return """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Intra Gini 🔥 — Broker Login</title>
  <style>
    * {{ box-sizing: border-box; margin: 0; padding: 0; }}
    body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
            background: #0f172a; color: #e2e8f0; min-height: 100vh; padding: 20px; }}
    .container {{ max-width: 500px; margin: 0 auto; }}
    .header {{ text-align: center; padding: 30px 0 20px; }}
    .header h1 {{ font-size: 2rem; font-weight: 800; }}
    .header .sub {{ color: #94a3b8; margin-top: 4px; font-size: 0.9rem; }}
    .card {{ background: #1e293b; border-radius: 16px; padding: 24px;
             margin-bottom: 16px; border: 1px solid #334155; }}
    .card-header {{ display: flex; align-items: center; justify-content: space-between;
                    margin-bottom: 16px; }}
    .card-title {{ font-size: 1.1rem; font-weight: 700; display: flex; align-items: center; gap: 8px; }}
    .card-logo {{ font-size: 1.4rem; }}
    .badge {{ padding: 4px 10px; border-radius: 20px; font-size: 0.75rem; font-weight: 600; }}
    .badge-green  {{ background: #064e3b; color: #34d399; }}
    .badge-red    {{ background: #450a0a; color: #f87171; }}
    .badge-yellow {{ background: #422006; color: #fbbf24; }}
    .note {{ font-size: 0.85rem; color: #94a3b8; margin-bottom: 16px; }}
    .note.warning {{ color: #fbbf24; }}
    .btn {{ display: block; width: 100%; text-align: center; padding: 14px;
            border-radius: 10px; font-size: 1rem; font-weight: 700;
            cursor: pointer; text-decoration: none; border: none; }}
    .btn-primary   {{ background: #6366f1; color: white; }}
    .btn-primary:hover {{ background: #4f46e5; }}
    .btn-secondary {{ background: #334155; color: #94a3b8; }}
    .btn-secondary:hover {{ background: #475569; color: white; }}
    .divider {{ border: none; border-top: 1px solid #334155; margin: 8px 0 16px; }}
    .time {{ text-align: center; color: #475569; font-size: 0.8rem; margin-top: 8px; }}
    .instructions {{ background: #1e293b; border-radius: 12px; padding: 16px;
                     margin-bottom: 16px; border: 1px solid #334155; }}
    .instructions p {{ font-size: 0.82rem; color: #94a3b8; margin-bottom: 6px; }}
    .instructions strong {{ color: #e2e8f0; }}
    #toast {{ position: fixed; bottom: 20px; left: 50%; transform: translateX(-50%);
              background: #1e293b; color: #e2e8f0; padding: 12px 24px;
              border-radius: 10px; border: 1px solid #334155;
              display: none; font-size: 0.9rem; z-index: 999; }}
  </style>
</head>
<body>
<div class="container">
  <div class="header">
    <h1>Intra Gini 🔥</h1>
    <div class="sub">Intraday Trading Bot — Broker Control</div>
  </div>

  <!-- Upstox Card -->
  <div class="card">
    <div class="card-header">
      <div class="card-title"><span class="card-logo">🏦</span> Upstox</div>
      {upstox_badge}
    </div>
    {upstox_note}
    {upstox_btn}
  </div>

  <!-- Angel One Card -->
  <div class="card">
    <div class="card-header">
      <div class="card-title"><span class="card-logo">😇</span> Angel One</div>
      {angel_badge}
    </div>
    {angel_note}
    {angel_btn}
  </div>

  <!-- Instructions -->
  <div class="instructions">
    <p><strong>Morning Checklist (9:00–9:15 AM IST):</strong></p>
    <p>1. Open this page → Login Upstox if red</p>
    <p>2. Angel One auto-logins itself — no action needed</p>
    <p>3. Bot trades from 9:15 AM. Upstox = primary, Angel One = backup</p>
    <p>4. Check Railway logs for live trade updates</p>
  </div>

  <div class="time">Last checked: {time}</div>
</div>

<div id="toast">Loading...</div>

<script>
function reloginAngel() {{
  document.getElementById('toast').style.display = 'block';
  document.getElementById('toast').innerText = '🔄 Triggering Angel One login...';
  fetch('/angel-login', {{method: 'POST'}})
    .then(r => r.json())
    .then(d => {{
      document.getElementById('toast').innerText = d.ok ? '✅ Angel One logged in!' : '❌ ' + d.error;
      setTimeout(() => location.reload(), 1500);
    }})
    .catch(() => {{
      document.getElementById('toast').innerText = '❌ Request failed';
    }})
    .finally(() => setTimeout(() => {{
      document.getElementById('toast').style.display = 'none';
    }}, 3000));
}}
</script>
</body>
</html>""".format(
        upstox_badge=upstox_badge,
        upstox_note=upstox_note,
        upstox_btn=upstox_btn,
        angel_badge=angel_badge,
        angel_note=angel_note,
        angel_btn=angel_btn,
        time=now_ist,
    )


def _upstox_auth_url():
    return (
        "https://api.upstox.com/v2/login/authorization/dialog"
        "?response_type=code"
        "&client_id={}"
        "&redirect_uri={}"
        "&state=intra-gini"
    ).format(UPSTOX_CLIENT_ID, UPSTOX_REDIRECT_URI)


# ──────────────────── HTTP Handler ──────────────────────
class AuthHandler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        pass  # suppress default access logs

    def do_GET(self):
        parsed = urlparse(self.path)

        if parsed.path == "/callback":
            # Upstox OAuth callback
            params = parse_qs(parsed.query)
            code = params.get("code", [None])[0]
            if code:
                ok = exchange_upstox_code(code)
                msg = "✅ Upstox Login Successful! Bot is now live trading." if ok else "❌ Token exchange failed."
            else:
                msg = "❌ No auth code in callback."

            self._respond(200, """<!DOCTYPE html><html><head>
<meta charset="UTF-8"><title>Intra Gini 🔥</title>
<style>body{{font-family:sans-serif;background:#0f172a;color:#e2e8f0;
display:flex;align-items:center;justify-content:center;min-height:100vh;}}
.box{{text-align:center;padding:40px;background:#1e293b;border-radius:16px;}}
h2{{font-size:1.5rem;margin-bottom:12px;}} a{{color:#6366f1;}}</style></head>
<body><div class="box"><h2>{msg}</h2>
<p><a href="/">← Back to dashboard</a></p></div></body></html>""".format(msg=msg))

        elif parsed.path in ("/", "/status"):
            self._respond(200, _build_html())

        elif parsed.path == "/health":
            self._respond(200, '{"status":"ok"}', "application/json")

        else:
            self._respond(404, "Not found")

    def do_POST(self):
        parsed = urlparse(self.path)

        if parsed.path == "/angel-login":
            # Trigger Angel One re-login
            if _angel_broker:
                ok = _angel_broker.login()
                if ok:
                    self._respond(200, '{"ok":true}', "application/json")
                else:
                    self._respond(200, '{"ok":false,"error":"Login failed — check logs"}', "application/json")
            else:
                self._respond(200, '{"ok":false,"error":"Angel broker not initialized"}', "application/json")
        else:
            self._respond(404, "Not found")

    def _respond(self, code, body, ctype="text/html"):
        b = body.encode("utf-8") if isinstance(body, str) else body
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", len(b))
        self.end_headers()
        self.wfile.write(b)


# ──────────────────── Scheduler ─────────────────────────
def _schedule_daily_logins():
    """Schedule auto-logins at 9:00 AM IST daily."""
    def do_upstox():
        print("[AUTH] Daily Upstox auto-login attempt (9:00 AM IST)...")
        attempt_upstox_auto_login()

    def do_angel():
        print("[AUTH] Daily Angel One re-login (9:00 AM IST)...")
        if _angel_broker:
            _angel_broker.login()

    schedule.every().day.at("03:30").do(do_upstox)   # 9:00 AM IST = 3:30 UTC
    schedule.every().day.at("03:30").do(do_angel)

    def run():
        while True:
            schedule.run_pending()
            time.sleep(30)

    t = threading.Thread(target=run, daemon=True)
    t.start()
    print("[AUTH] Daily 9:00 AM IST login scheduler started")


# ──────────────────── Start server ──────────────────────
def start_auth_server():
    port = int(os.environ.get("PORT", 8080))
    railway_url = os.environ.get("RAILWAY_PUBLIC_DOMAIN", "")
    public_url = "https://{}".format(railway_url) if railway_url else "http://localhost:{}".format(port)

    print("[AUTH] Login page: {}".format(public_url))

    # Try Upstox auto-login at startup (may fail — user can login manually)
    attempt_upstox_auto_login()

    # Schedule daily re-logins
    _schedule_daily_logins()

    def _run():
        server = HTTPServer(("0.0.0.0", port), AuthHandler)
        print("[AUTH] Web server ready at {}".format(public_url))
        server.serve_forever()

    t = threading.Thread(target=_run, daemon=True)
    t.start()
    print("[AUTH] Next auto-login scheduled for 9:00 AM IST")
