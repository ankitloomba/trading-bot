"""
Upstox OAuth Web Server
Catches the auth code redirect and stores access token automatically.
Runs on port 8080 alongside the trading bot.
"""
import os
import threading
import requests
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
from datetime import datetime

CLIENT_ID = os.environ.get('UPSTOX_CLIENT_ID')
CLIENT_SECRET = os.environ.get('UPSTOX_CLIENT_SECRET')
REDIRECT_URI = os.environ.get('UPSTOX_REDIRECT_URI')
BASE_URL = "https://api.upstox.com/v2"

ACCESS_TOKEN = None

class AuthHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        pass  # suppress default logs

    def do_GET(self):
        global ACCESS_TOKEN
        parsed = urlparse(self.path)

        # Health check
        if parsed.path == '/health':
            self.send_response(200)
            self.send_header('Content-Type', 'text/html')
            self.end_headers()
            status = "LOGGED IN" if ACCESS_TOKEN else "WAITING FOR LOGIN"
            html = f"""
            <html><body style="font-family:sans-serif;padding:20px;background:#111;color:white">
            <h2>🔥 Intra Gini Bot</h2>
            <p>Status: <b style="color:{'#22c55e' if ACCESS_TOKEN else '#f97316'}">{status}</b></p>
            <p>Time: {datetime.now().strftime('%H:%M:%S IST')}</p>
            {'<p style="color:#22c55e">Bot is trading! Check Railway logs for signals.</p>' if ACCESS_TOKEN else f'<p><a href="{get_auth_url()}" style="color:#818cf8">Click here to login with Upstox</a></p>'}
            </body></html>
            """
            self.wfile.write(html.encode())
            return

        # OAuth callback
        if parsed.path == '/' or parsed.path == '/callback':
            params = parse_qs(parsed.query)
            auth_code = params.get('code', [None])[0]

            if auth_code:
                print(f"\n[AUTH] Received auth code: {auth_code[:20]}...")
                token = exchange_code(auth_code)

                if token:
                    ACCESS_TOKEN = token
                    os.environ['UPSTOX_ACCESS_TOKEN'] = token
                    print("[AUTH] Login successful! Bot will now place real orders.")
                    self.send_response(200)
                    self.send_header('Content-Type', 'text/html')
                    self.end_headers()
                    self.wfile.write(b"""
                    <html><body style="font-family:sans-serif;padding:40px;background:#111;color:white;text-align:center">
                    <h1 style="color:#22c55e">Login Successful!</h1>
                    <p style="font-size:20px">Intra Gini is now live trading.</p>
                    <p>You can close this page and check Railway logs for signals.</p>
                    </body></html>
                    """)
                else:
                    self.send_response(400)
                    self.send_header('Content-Type', 'text/html')
                    self.end_headers()
                    self.wfile.write(b"""
                    <html><body style="font-family:sans-serif;padding:40px;background:#111;color:white">
                    <h1 style="color:#ef4444">Login Failed</h1>
                    <p>Could not exchange auth code. Try again.</p>
                    </body></html>
                    """)
            else:
                # No code — show login page
                self.send_response(200)
                self.send_header('Content-Type', 'text/html')
                self.end_headers()
                auth_url = get_auth_url()
                html = f"""
                <html><body style="font-family:sans-serif;padding:40px;background:#111;color:white;text-align:center">
                <h1>🔥 Intra Gini</h1>
                <p>Login with Upstox to start live trading</p>
                <a href="{auth_url}" style="display:inline-block;background:#7c3aed;color:white;padding:14px 28px;border-radius:12px;text-decoration:none;font-size:16px;font-weight:bold;margin-top:20px">
                Login with Upstox
                </a>
                <p style="color:#6b7280;margin-top:20px;font-size:14px">Capital: Rs.5,000 | Mode: Live Trading</p>
                </body></html>
                """
                self.wfile.write(html.encode())

def get_auth_url():
    return (
        f"https://api.upstox.com/v2/login/authorization/dialog"
        f"?response_type=code"
        f"&client_id={CLIENT_ID}"
        f"&redirect_uri={REDIRECT_URI}"
    )

def exchange_code(auth_code):
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
            print(f"[AUTH] Access token obtained!")
            return data['access_token']
        print(f"[AUTH] Token exchange failed: {data}")
        return None
    except Exception as e:
        print(f"[AUTH] Error: {e}")
        return None

def get_token():
    return ACCESS_TOKEN

def start_auth_server():
    server = HTTPServer(('0.0.0.0', 8080), AuthHandler)
    print("[AUTH] Web server running on port 8080")
    print(f"[AUTH] Visit: {REDIRECT_URI}/health to check status")
    server.serve_forever()

def run_in_background():
    thread = threading.Thread(target=start_auth_server, daemon=True)
    thread.start()
    return thread

if __name__ == '__main__':
    print("Starting Upstox auth server...")
    start_auth_server()
