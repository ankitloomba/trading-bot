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

class AuthHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args): pass

    def do_GET(self):
        global ACCESS_TOKEN
        parsed = urlparse(self.path)
        params = parse_qs(parsed.query)
        auth_code = params.get('code', [None])[0]

        if auth_code:
            print(f"[AUTH] Got auth code from browser login")
            token = exchange_code(auth_code)
            if token:
                ACCESS_TOKEN = token
                os.environ['UPSTOX_ACCESS_TOKEN'] = token
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
