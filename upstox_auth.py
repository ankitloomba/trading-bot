"""
Upstox Auto-Auth
- Runs web server on port 8080 for OAuth callback
- Auto-refreshes token daily at 9am using TOTP
- Stores token in memory + env for bot to use
"""
import os
import threading
import time
import requests
import pyotp
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
from datetime import datetime
import pytz

IST = pytz.timezone('Asia/Kolkata')
CLIENT_ID = os.environ.get('UPSTOX_CLIENT_ID')
CLIENT_SECRET = os.environ.get('UPSTOX_CLIENT_SECRET')
REDIRECT_URI = os.environ.get('UPSTOX_REDIRECT_URI')
TOTP_SECRET = os.environ.get('UPSTOX_TOTP_SECRET')
UPSTOX_MOBILE = os.environ.get('UPSTOX_MOBILE', '')
UPSTOX_PIN = os.environ.get('UPSTOX_PIN', '')
BASE_URL = "https://api.upstox.com/v2"

ACCESS_TOKEN = None
TOKEN_EXPIRY = None
_token_callbacks = []

# Live state updated by trader every scan cycle
_live_state = {
    'status': 'STARTING',
    'capital': 0,
    'daily_pnl': 0,
    'positions': [],
    'options': [],
    'last_scan': None,
}

def update_live_state(**kwargs):
    _live_state.update(kwargs)

def on_token(callback):
    """Register a callback to be called when token is obtained."""
    _token_callbacks.append(callback)

def get_upstox_token():
    return ACCESS_TOKEN

def set_angel_broker(angel_broker):
    """Stub — Angel One status shown on page if needed."""
    pass

def _fire_token_callbacks(token):
    for cb in _token_callbacks:
        try:
            cb(token)
        except Exception as e:
            print(f"[AUTH] Token callback error: {e}")

def get_totp():
    return pyotp.TOTP(TOTP_SECRET).now()

def auto_login():
    """Fully automated login using Upstox API + TOTP"""
    global ACCESS_TOKEN, TOKEN_EXPIRY
    print("[AUTH] Attempting automated Upstox login...")
    try:
        # Step 1: Get auth code via API (requires mobile + PIN + TOTP)
        session = requests.Session()
        
        # Step 2: Exchange for token using auth code flow
        # First get the login page to get the auth code
        auth_url = (
            f"https://api.upstox.com/v2/login/authorization/dialog"
            f"?response_type=code"
            f"&client_id={CLIENT_ID}"
            f"&redirect_uri={REDIRECT_URI}"
        )
        
        # Use Upstox login API directly
        totp = get_totp()
        print(f"[AUTH] TOTP generated: {totp}")
        
        # Login with credentials
        login_resp = session.post(
            "https://api.upstox.com/v2/login/authorization/dialog",
            data={
                'mobile': UPSTOX_MOBILE,
                'mpin': UPSTOX_PIN,
                'otp': totp,
                'client_id': CLIENT_ID,
                'redirect_uri': REDIRECT_URI,
            },
            allow_redirects=False
        )
        
        # Extract code from redirect
        location = login_resp.headers.get('Location', '')
        if 'code=' in location:
            code = location.split('code=')[1].split('&')[0]
            token = exchange_code(code)
            if token:
                ACCESS_TOKEN = token
                os.environ['UPSTOX_ACCESS_TOKEN'] = token
                _fire_token_callbacks(token)
                print("[AUTH] Auto-login successful!")
                return True
        
        print(f"[AUTH] Auto-login response: {login_resp.status_code}")
        print("[AUTH] Please login manually at the web URL")
        return False
    except Exception as e:
        print(f"[AUTH] Auto-login error: {e}")
        return False

def exchange_code(auth_code):
    global ACCESS_TOKEN
    try:
        response = requests.post(
            f"{BASE_URL}/login/authorization/token",
            headers={'Content-Type': 'application/x-www-form-urlencoded'},
            data={
                'code': auth_code,
                'client_id': CLIENT_ID,
                'client_secret': CLIENT_SECRET,
                'redirect_uri': REDIRECT_URI,
                'grant_type': 'authorization_code'
            }
        )
        data = response.json()
        if data.get('access_token'):
            print("[AUTH] Token obtained!")
            return data['access_token']
        print(f"[AUTH] Token exchange failed: {data}")
        return None
    except Exception as e:
        print(f"[AUTH] Exchange error: {e}")
        return None

def get_auth_url():
    return (
        f"https://api.upstox.com/v2/login/authorization/dialog"
        f"?response_type=code"
        f"&client_id={CLIENT_ID}"
        f"&redirect_uri={REDIRECT_URI}"
    )

def get_token():
    return ACCESS_TOKEN

def schedule_daily_login():
    """Runs at 9:00am IST every day to refresh token"""
    def loop():
        while True:
            now = datetime.now(IST)
            # Target: 9:00am IST
            target = now.replace(hour=9, minute=0, second=0, microsecond=0)
            if now >= target:
                # Already past 9am today — schedule for tomorrow
                from datetime import timedelta
                target = target + timedelta(days=1)
            wait_secs = (target - now).total_seconds()
            print(f"[AUTH] Next auto-login in {wait_secs/3600:.1f} hours (9:00am IST)")
            time.sleep(wait_secs)
            print("[AUTH] Scheduled daily auto-login starting...")
            auto_login()
    thread = threading.Thread(target=loop, daemon=True)
    thread.start()

def _db_query(sql, params=()):
    try:
        import psycopg2, os
        conn = psycopg2.connect(os.environ.get('DATABASE_URL'))
        cur = conn.cursor()
        cur.execute(sql, params)
        cols = [d[0] for d in cur.description]
        rows = [dict(zip(cols, row)) for row in cur.fetchall()]
        cur.close(); conn.close()
        return rows
    except Exception:
        return []

def _json_response(handler, data, status=200):
    import json
    body = json.dumps(data, default=str).encode()
    handler.send_response(status)
    handler.send_header('Content-Type', 'application/json')
    handler.send_header('Access-Control-Allow-Origin', '*')
    handler.send_header('Content-Length', str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)

class AuthHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args): pass

    def do_GET(self):
        global ACCESS_TOKEN
        parsed = urlparse(self.path)
        path = parsed.path
        params = parse_qs(parsed.query)

        # ── API endpoints ──────────────────────────────────
        if path == '/api/status':
            _json_response(self, _live_state)
            return

        if path == '/api/trades':
            today = datetime.now(IST).strftime('%Y-%m-%d')
            rows = _db_query(
                "SELECT * FROM trades WHERE DATE(created_at AT TIME ZONE 'Asia/Kolkata') = %s ORDER BY created_at DESC",
                (today,)
            )
            _json_response(self, {'date': today, 'trades': rows, 'count': len(rows)})
            return

        if path == '/api/summary':
            rows = _db_query("SELECT * FROM daily_summary ORDER BY date DESC LIMIT 30")
            _json_response(self, {'history': rows})
            return

        if path == '/health':
            _json_response(self, {'ok': True, 'time': datetime.now(IST).strftime('%H:%M:%S IST')})
            return

        if path == '/api/clear-dummy':
            # One-time: delete all trades/summaries that are dummy/test data
            # Keeps only rows where pnl is non-null and entry_price > 0
            try:
                import psycopg2, os as _os2
                conn = psycopg2.connect(_os2.environ.get('DATABASE_URL'))
                cur = conn.cursor()
                cur.execute("DELETE FROM trades WHERE entry_price IS NULL OR entry_price = 0 OR pnl IS NULL")
                deleted_trades = cur.rowcount
                cur.execute("DELETE FROM daily_summary WHERE total_trades = 0 OR total_pnl IS NULL")
                deleted_summary = cur.rowcount
                conn.commit()
                cur.close(); conn.close()
                _json_response(self, {'cleared': True, 'trades_deleted': deleted_trades, 'summary_deleted': deleted_summary})
            except Exception as e:
                _json_response(self, {'error': str(e)}, 500)
            return

        if path == '/api/wipe-all':
            # Nuclear: delete everything — use once to start fresh
            try:
                import psycopg2, os as _os3
                conn = psycopg2.connect(_os3.environ.get('DATABASE_URL'))
                cur = conn.cursor()
                cur.execute("DELETE FROM trades")
                t = cur.rowcount
                cur.execute("DELETE FROM daily_summary")
                s = cur.rowcount
                conn.commit()
                cur.close(); conn.close()
                _json_response(self, {'wiped': True, 'trades': t, 'summaries': s})
            except Exception as e:
                _json_response(self, {'error': str(e)}, 500)
            return

        # ── Dashboard static files ─────────────────────────
        import os as _os
        dashboard_dir = _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), 'dashboard')
        if path == '/' or path == '/dashboard' or path == '/dashboard/':
            file_path = _os.path.join(dashboard_dir, 'index.html')
            content_type = 'text/html'
        elif path == '/manifest.json':
            file_path = _os.path.join(dashboard_dir, 'manifest.json')
            content_type = 'application/json'
        else:
            file_path = None
            content_type = None

        if file_path and _os.path.exists(file_path):
            with open(file_path, 'rb') as f:
                body = f.read()
            self.send_response(200)
            self.send_header('Content-Type', content_type)
            self.send_header('Content-Length', str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return

        # ── OAuth callback ─────────────────────────────────
        auth_code = params.get('code', [None])[0]

        if auth_code:
            print(f"[AUTH] Got auth code from browser login")
            token = exchange_code(auth_code)
            if token:
                ACCESS_TOKEN = token
                os.environ['UPSTOX_ACCESS_TOKEN'] = token
                _fire_token_callbacks(token)
                self.send_response(200)
                self.send_header('Content-Type', 'text/html')
                self.end_headers()
                self.wfile.write(b"""
                <html><body style="font-family:sans-serif;padding:40px;background:#111;color:white;text-align:center">
                <h1 style="color:#22c55e">Login Successful!</h1>
                <p style="font-size:18px">Intra Gini is now placing real trades.</p>
                <p style="color:#6b7280">You can close this page.</p>
                </body></html>""")
                return

        # Show login page
        self.send_response(200)
        self.send_header('Content-Type', 'text/html')
        self.end_headers()
        status = "LOGGED IN ✅" if ACCESS_TOKEN else "WAITING FOR LOGIN"
        color = "#22c55e" if ACCESS_TOKEN else "#f97316"
        auth_url = get_auth_url()
        totp = get_totp() if TOTP_SECRET else "N/A"
        html = f"""
        <html><body style="font-family:-apple-system,sans-serif;padding:40px;background:#111;color:white;text-align:center;max-width:400px;margin:0 auto">
        <h1 style="font-size:32px;margin-bottom:8px">🔥 Intra Gini</h1>
        <p style="color:#6b7280;margin-bottom:24px">Intelligent Intraday Trading Bot</p>
        <div style="background:#1a1a1a;border-radius:16px;padding:20px;margin-bottom:24px">
          <p style="color:#6b7280;font-size:12px;margin-bottom:4px">STATUS</p>
          <p style="color:{color};font-size:18px;font-weight:700">{status}</p>
          {'<p style="color:#22c55e;font-size:14px">Bot is live trading with ₹5,000!</p>' if ACCESS_TOKEN else ''}
        </div>
        {'<div style="background:#1a1a1a;border-radius:16px;padding:20px;margin-bottom:24px"><p style="color:#6b7280;font-size:12px">TOTP (valid 30 secs)</p><p style="font-size:32px;font-weight:700;letter-spacing:8px">'+totp+'</p></div>' if TOTP_SECRET else ''}
        {f'<a href="{auth_url}" style="display:block;background:#7c3aed;color:white;padding:16px 28px;border-radius:12px;text-decoration:none;font-size:16px;font-weight:700">Login with Upstox</a>' if not ACCESS_TOKEN else ''}
        <p style="color:#374151;font-size:12px;margin-top:24px">Capital: ₹5,000 | Mode: {"LIVE" if not os.environ.get("PAPER_TRADE","true") == "true" else "PAPER"}</p>
        </body></html>"""
        self.wfile.write(html.encode())

def start_auth_server():
    server = HTTPServer(('0.0.0.0', 8080), AuthHandler)
    print(f"[AUTH] Web server ready at {REDIRECT_URI}")
    server.serve_forever()

def run_in_background():
    # Try auto-login first if TOTP available
    if TOTP_SECRET:
        threading.Thread(target=auto_login, daemon=True).start()
    # Schedule daily 9am login
    schedule_daily_login()
    # Start web server
    thread = threading.Thread(target=start_auth_server, daemon=True)
    thread.start()
    return thread

if __name__ == '__main__':
    start_auth_server()
