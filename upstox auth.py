"""
Upstox Full Auto-Login
Runs at 9:00am IST daily using mobile + PIN + TOTP
No manual action needed ever.
"""
import os
import time
import threading
import requests
import pyotp
from datetime import datetime, timedelta
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
import pytz

IST = pytz.timezone('Asia/Kolkata')

CLIENT_ID     = os.environ.get('UPSTOX_CLIENT_ID')
CLIENT_SECRET = os.environ.get('UPSTOX_CLIENT_SECRET')
REDIRECT_URI  = os.environ.get('UPSTOX_REDIRECT_URI')
TOTP_SECRET   = os.environ.get('UPSTOX_TOTP_SECRET')
MOBILE        = os.environ.get('UPSTOX_MOBILE')
PIN           = os.environ.get('UPSTOX_PIN')

ACCESS_TOKEN  = None

def get_totp():
    return pyotp.TOTP(TOTP_SECRET).now()

def auto_login():
    global ACCESS_TOKEN
    print("[AUTH] Auto-login starting...")
    try:
        session = requests.Session()

        # Step 1: Initiate login
        r1 = session.post(
            "https://api.upstox.com/v2/login/authorization/dialog",
            data={
                'client_id': CLIENT_ID,
                'redirect_uri': REDIRECT_URI,
                'response_type': 'code',
            },
            allow_redirects=True
        )

        # Step 2: Submit mobile number
        r2 = session.post(
            "https://api.upstox.com/v2/login/authorization/dialog",
            data={'mobile': MOBILE},
            allow_redirects=True
        )

        # Step 3: Submit PIN
        r3 = session.post(
            "https://api.upstox.com/v2/login/authorization/dialog",
            data={'mpin': PIN},
            allow_redirects=True
        )

        # Step 4: Submit TOTP
        totp = get_totp()
        print(f"[AUTH] Using TOTP: {totp}")
        r4 = session.post(
            "https://api.upstox.com/v2/login/authorization/dialog",
            data={'otp': totp},
            allow_redirects=False
        )

        # Extract auth code from redirect
        location = r4.headers.get('Location', '')
        print(f"[AUTH] Redirect: {location[:80]}...")

        if 'code=' in location:
            code = location.split('code=')[1].split('&')[0]
            token = exchange_code(code)
            if token:
                ACCESS_TOKEN = token
                os.environ['UPSTOX_ACCESS_TOKEN'] = token
                print("[AUTH] ✅ Auto-login SUCCESS!")
                return True

        # Fallback: try Upstox v3 login API
        print("[AUTH] Trying v3 API login...")
        return auto_login_v3()

    except Exception as e:
        print(f"[AUTH] Auto-login error: {e}")
        return auto_login_v3()

def auto_login_v3():
    """Alternative login using Upstox internal API"""
    global ACCESS_TOKEN
    try:
        session = requests.Session()
        session.headers.update({
            'User-Agent': 'Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X)',
            'Accept': 'application/json',
        })

        # Get auth page first
        auth_url = (
            f"https://api.upstox.com/v2/login/authorization/dialog"
            f"?response_type=code&client_id={CLIENT_ID}&redirect_uri={REDIRECT_URI}"
        )
        session.get(auth_url)

        # Login with credentials
        totp = get_totp()
        resp = session.post(
            "https://api-v3.upstox.com/login",
            json={
                'mobile_number': MOBILE,
                'client_id': CLIENT_ID,
                'totp': totp,
                'pin': PIN,
            }
        )
        data = resp.json()
        if data.get('status') == 'success' and data.get('data', {}).get('authorization_code'):
            code = data['data']['authorization_code']
            token = exchange_code(code)
            if token:
                ACCESS_TOKEN = token
                os.environ['UPSTOX_ACCESS_TOKEN'] = token
                print("[AUTH] ✅ v3 login SUCCESS!")
                return True

        print(f"[AUTH] v3 response: {data}")
        return False
    except Exception as e:
        print(f"[AUTH] v3 error: {e}")
        return False

def exchange_code(code):
    try:
        r = requests.post(
            "https://api.upstox.com/v2/login/authorization/token",
            headers={'Content-Type': 'application/x-www-form-urlencoded'},
            data={
                'code': code,
                'client_id': CLIENT_ID,
                'client_secret': CLIENT_SECRET,
                'redirect_uri': REDIRECT_URI,
                'grant_type': 'authorization_code'
            }
        )
        data = r.json()
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
        f"?response_type=code&client_id={CLIENT_ID}&redirect_uri={REDIRECT_URI}"
    )

def get_token():
    return ACCESS_TOKEN

def schedule_daily_login():
    """Auto-login every day at 8:55am IST"""
    def loop():
        while True:
            now = datetime.now(IST)
            target = now.replace(hour=8, minute=55, second=0, microsecond=0)
            if now >= target:
                target += timedelta(days=1)
            wait = (target - now).total_seconds()
            print(f"[AUTH] Next auto-login in {wait/3600:.1f}hrs (8:55am IST)")
            time.sleep(wait)
            print("[AUTH] Scheduled auto-login starting...")
            success = auto_login()
            if not success:
                print("[AUTH] Auto-login failed — retry in 5 mins")
                time.sleep(300)
                auto_login()

    threading.Thread(target=loop, daemon=True).start()

class AuthHandler(BaseHTTPRequestHandler):
    def log_message(self, f, *a): pass

    def do_GET(self):
        global ACCESS_TOKEN
        parsed = urlparse(self.path)
        params = parse_qs(parsed.query)
        code = params.get('code', [None])[0]

        if code:
            token = exchange_code(code)
            if token:
                ACCESS_TOKEN = token
                os.environ['UPSTOX_ACCESS_TOKEN'] = token
                self.send_response(200)
                self.send_header('Content-Type', 'text/html')
                self.end_headers()
                self.wfile.write(b"""
                <html><body style="font-family:sans-serif;padding:40px;background:#111;color:white;text-align:center">
                <h1 style="color:#22c55e">Login Successful!</h1>
                <p>Intra Gini is now live trading. Close this page.</p>
                </body></html>""")
                return

        # Show status page
        self.send_response(200)
        self.send_header('Content-Type', 'text/html')
        self.end_headers()
        status = "LOGGED IN ✅" if ACCESS_TOKEN else "WAITING FOR LOGIN"
        color = "#22c55e" if ACCESS_TOKEN else "#f97316"
        totp = get_totp() if TOTP_SECRET else "N/A"
        mode = "LIVE" if os.environ.get('PAPER_TRADE','true').lower() == 'false' else "PAPER"
        html = f"""
        <html><body style="font-family:-apple-system,sans-serif;padding:40px;background:#111;color:white;text-align:center;max-width:420px;margin:0 auto">
        <h1 style="font-size:32px">🔥 Intra Gini</h1>
        <p style="color:#6b7280;margin-bottom:24px">Intelligent Intraday Trading Bot</p>
        <div style="background:#1a1a1a;border-radius:16px;padding:20px;margin-bottom:16px">
          <p style="color:#6b7280;font-size:12px;margin-bottom:4px">STATUS</p>
          <p style="color:{color};font-size:20px;font-weight:700">{status}</p>
          <p style="color:#6b7280;font-size:13px;margin-top:4px">Mode: {mode} | Capital: ₹5,000</p>
        </div>
        <div style="background:#1a1a1a;border-radius:16px;padding:20px;margin-bottom:16px">
          <p style="color:#6b7280;font-size:12px">TOTP (refreshes every 30s)</p>
          <p style="font-size:36px;font-weight:700;letter-spacing:10px;color:#fbbf24">{totp}</p>
        </div>
        {'<div style="background:#1a1a1a;border-radius:16px;padding:16px;margin-bottom:16px"><p style="color:#22c55e;font-size:14px">✅ Auto-login scheduled at 8:55am IST daily</p></div>' if TOTP_SECRET and MOBILE and PIN else ''}
        {f'<a href="{get_auth_url()}" style="display:block;background:#7c3aed;color:white;padding:16px;border-radius:12px;text-decoration:none;font-size:15px;font-weight:700;margin-top:8px">Login Manually with Upstox</a>' if not ACCESS_TOKEN else '<p style="color:#22c55e;font-size:15px;margin-top:16px">Bot is hunting for trades! 🔥</p>'}
        </body></html>"""
        self.wfile.write(html.encode())

def start_auth_server():
    server = HTTPServer(('0.0.0.0', 8080), AuthHandler)
    print(f"[AUTH] Server ready at {REDIRECT_URI}")
    server.serve_forever()

def run_in_background():
    # Try auto-login immediately on startup
    if TOTP_SECRET and MOBILE and PIN:
        threading.Thread(target=auto_login, daemon=True).start()

    # Schedule daily 8:55am login
    schedule_daily_login()

    # Start web server
    threading.Thread(target=start_auth_server, daemon=True).start()

if __name__ == '__main__':
    start_auth_server()
