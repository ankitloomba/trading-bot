"""
Upstox Auto-Login — Playwright browser automation
Runs at 9:00 AM IST, gets fresh token, updates Railway env var.

Flow:
  1. Open Upstox OAuth URL in headless Chromium
  2. Fill mobile → PIN → TOTP (pyotp)
  3. Capture redirect URL → extract auth code
  4. Exchange code → access token
  5. Push token to Railway via API → bot picks it up
"""
import os
import sys
import time
import pyotp
import requests
from datetime import datetime
import pytz

IST = pytz.timezone('Asia/Kolkata')

# ── Credentials from env vars ──────────────────────────────────────────────
CLIENT_ID     = os.environ.get('UPSTOX_CLIENT_ID',     'db4e86a1-d32c-4f73-b94a-95a76e5a0ec2')
CLIENT_SECRET = os.environ.get('UPSTOX_CLIENT_SECRET', 'ro93q4zu74')
REDIRECT_URI  = os.environ.get('UPSTOX_REDIRECT_URI',  'https://trading-bot-production.up.railway.app/callback')
TOTP_SECRET   = os.environ.get('UPSTOX_TOTP_SECRET',   'KJSTGN6OQH5CON5S5PB7PU4GM3UBY7PG')
MOBILE        = os.environ.get('UPSTOX_MOBILE',        '9717618787')
PIN           = os.environ.get('UPSTOX_PIN',           '909192')

# Railway API — to push the new token as an env var
RAILWAY_TOKEN      = os.environ.get('RAILWAY_API_TOKEN', '')
RAILWAY_SERVICE_ID = os.environ.get('RAILWAY_SERVICE_ID', '')
RAILWAY_ENV_ID     = os.environ.get('RAILWAY_ENVIRONMENT_ID', '')


def get_totp():
    return pyotp.TOTP(TOTP_SECRET).now()


def exchange_code(auth_code):
    """Exchange OAuth code for access token."""
    try:
        res = requests.post(
            'https://api.upstox.com/v2/login/authorization/token',
            headers={'Content-Type': 'application/x-www-form-urlencoded'},
            data={
                'code':          auth_code,
                'client_id':     CLIENT_ID,
                'client_secret': CLIENT_SECRET,
                'redirect_uri':  REDIRECT_URI,
                'grant_type':    'authorization_code',
            }
        )
        data = res.json()
        token = data.get('access_token')
        if token:
            print("[LOGIN] ✅ Token obtained!")
            return token
        print("[LOGIN] ❌ Token exchange failed:", data)
        return None
    except Exception as e:
        print("[LOGIN] Exchange error:", e)
        return None


def push_token_to_railway(token):
    """Update UPSTOX_ACCESS_TOKEN env var on Railway so the bot picks it up."""
    if not RAILWAY_TOKEN:
        print("[LOGIN] No RAILWAY_API_TOKEN — writing token to file instead")
        with open('/tmp/upstox_token.txt', 'w') as f:
            f.write(token)
        os.environ['UPSTOX_ACCESS_TOKEN'] = token
        return True

    query = """
    mutation UpsertVariables($input: VariableCollectionUpsertInput!) {
      variableCollectionUpsert(input: $input)
    }
    """
    variables = {
        "input": {
            "projectId":     os.environ.get('RAILWAY_PROJECT_ID', ''),
            "environmentId": RAILWAY_ENV_ID,
            "serviceId":     RAILWAY_SERVICE_ID,
            "variables": {
                "UPSTOX_ACCESS_TOKEN": token
            }
        }
    }
    try:
        res = requests.post(
            'https://backboard.railway.app/graphql/v2',
            headers={
                'Authorization': 'Bearer {}'.format(RAILWAY_TOKEN),
                'Content-Type':  'application/json',
            },
            json={'query': query, 'variables': variables}
        )
        data = res.json()
        if data.get('data', {}).get('variableCollectionUpsert'):
            print("[LOGIN] ✅ Token pushed to Railway env vars")
            return True
        print("[LOGIN] ❌ Railway push failed:", data)
        return False
    except Exception as e:
        print("[LOGIN] Railway push error:", e)
        return False


def auto_login_playwright():
    """Use Playwright headless browser to complete Upstox OAuth."""
    from playwright.sync_api import sync_playwright

    auth_url = (
        'https://api.upstox.com/v2/login/authorization/dialog'
        '?response_type=code'
        '&client_id={}'
        '&redirect_uri={}'
    ).format(CLIENT_ID, REDIRECT_URI)

    print("[LOGIN] Starting headless browser login...")
    print("[LOGIN] Auth URL:", auth_url)

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            executable_path='/opt/pw-browsers/chromium',
            args=['--no-sandbox', '--disable-dev-shm-usage']
        )
        page = browser.new_page()

        # Intercept redirects to catch the auth code
        auth_code = None

        def handle_response(response):
            nonlocal auth_code
            url = response.url
            if REDIRECT_URI in url and 'code=' in url:
                code = url.split('code=')[1].split('&')[0]
                print("[LOGIN] Auth code captured:", code[:10], "...")
                auth_code = code

        page.on('response', handle_response)

        try:
            # 1. Open OAuth URL
            page.goto(auth_url, wait_until='networkidle', timeout=30000)
            print("[LOGIN] Page loaded:", page.title())
            time.sleep(2)

            # 2. Enter mobile number
            mobile_field = page.locator('input[type="text"], input[name="mobile"], input[placeholder*="mobile" i], input[placeholder*="number" i]').first
            mobile_field.fill(MOBILE)
            print("[LOGIN] Mobile filled")
            time.sleep(1)

            # Click Get OTP / Continue button
            page.locator('button:has-text("Get OTP"), button:has-text("Continue"), button:has-text("Next")').first.click()
            print("[LOGIN] Continue clicked")
            time.sleep(3)

            # 3. Enter PIN
            pin_field = page.locator('input[type="password"], input[name="pin"], input[name="mpin"]').first
            pin_field.fill(PIN)
            print("[LOGIN] PIN filled")
            time.sleep(1)

            # 4. Generate and enter TOTP
            totp_val = get_totp()
            print("[LOGIN] TOTP:", totp_val)
            totp_field = page.locator('input[name="otp"], input[placeholder*="OTP" i], input[placeholder*="TOTP" i], input[type="text"]').first
            totp_field.fill(totp_val)
            time.sleep(1)

            # 5. Submit
            page.locator('button[type="submit"], button:has-text("Login"), button:has-text("Verify")').first.click()
            print("[LOGIN] Login submitted")

            # Wait for redirect
            page.wait_for_timeout(8000)

            # Check current URL for code
            current_url = page.url
            print("[LOGIN] Current URL:", current_url[:80])
            if 'code=' in current_url and not auth_code:
                auth_code = current_url.split('code=')[1].split('&')[0]
                print("[LOGIN] Code from URL:", auth_code[:10], "...")

        except Exception as e:
            print("[LOGIN] Browser error:", e)
            # Take screenshot for debugging
            try:
                page.screenshot(path='/tmp/login_debug.png')
                print("[LOGIN] Screenshot saved: /tmp/login_debug.png")
            except:
                pass
        finally:
            browser.close()

        return auth_code


def run():
    print("[LOGIN] Upstox Auto-Login | {}".format(
        datetime.now(IST).strftime('%Y-%m-%d %H:%M:%S IST')))

    # Step 1: Browser login → get auth code
    auth_code = auto_login_playwright()
    if not auth_code:
        print("[LOGIN] ❌ Could not get auth code — manual login required")
        sys.exit(1)

    # Step 2: Exchange code for token
    token = exchange_code(auth_code)
    if not token:
        print("[LOGIN] ❌ Token exchange failed")
        sys.exit(1)

    # Step 3: Push token to Railway
    push_token_to_railway(token)

    print("[LOGIN] ✅ Done! Bot will use new token on next scan.")
    print("[LOGIN] Token (first 20 chars):", token[:20], "...")


if __name__ == '__main__':
    run()
