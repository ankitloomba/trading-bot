import os
import time
from datetime import datetime
import pytz

IST = pytz.timezone('Asia/Kolkata')
now = datetime.now(IST)

print("""
🔥🔥🔥🔥🔥🔥🔥🔥🔥🔥🔥🔥🔥🔥🔥🔥🔥🔥🔥🔥
        INTRA GINI 🔥
   Intelligent Intraday Trading Bot
🔥🔥🔥🔥🔥🔥🔥🔥🔥🔥🔥🔥🔥🔥🔥🔥🔥🔥🔥🔥
""")
print("Started:  {}".format(now.strftime('%Y-%m-%d %H:%M:%S IST')))
print("Capital:  Rs.{:,.0f}".format(float(os.environ.get('STARTING_CAPITAL', 5000))))
print("Broker:   {}".format(os.environ.get('BROKER', 'PAPER')))
print("="*42)

# Start auth web server in background
from upstox_auth import run_in_background, get_token
run_in_background()
print("[AUTH] Login page ready at: {}".format(os.environ.get('UPSTOX_REDIRECT_URI', '')))
print("[AUTH] Health check: {}/health".format(os.environ.get('UPSTOX_REDIRECT_URI', '')))

# Setup DB
try:
    from db import setup_db
    setup_db()
    print("Database: Ready")
except Exception as e:
    print("Database: Unavailable")

# Wait briefly for server to start
time.sleep(2)

# Check if already have token in env
existing_token = os.environ.get('UPSTOX_ACCESS_TOKEN')
if existing_token:
    print("\n[AUTH] Found existing token - going live immediately!")
    import upstox_auth
    upstox_auth.ACCESS_TOKEN = existing_token
else:
    print("\n[AUTH] Open this URL to login with Upstox:")
    from upstox_auth import get_auth_url
    print(get_auth_url())
    print("\n[BOT] Starting in paper trade mode until login...")

# Start the adaptive trader
from upstox_live_trader import AdaptiveTrader
trader = AdaptiveTrader()
trader.run()
