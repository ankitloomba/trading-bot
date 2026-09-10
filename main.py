import os
import time
from datetime import datetime
import pytz

IST = pytz.timezone('Asia/Kolkata')
now = datetime.now(IST)

print("""
🔥🔥🔥🔥🔥🔥🔥🔥🔥🔥🔥🔥🔥🔥🔥🔥🔥🔥🔥🔥
        INTRA GINI 🔥
   Multi-Symbol + Options Trader
🔥🔥🔥🔥🔥🔥🔥🔥🔥🔥🔥🔥🔥🔥🔥🔥🔥🔥🔥🔥
""")
print("Started:  {}".format(now.strftime('%Y-%m-%d %H:%M:%S IST')))
print("Capital:  Rs.{:,.0f}".format(float(os.environ.get('STARTING_CAPITAL', 5000))))

try:
    from db import setup_db
    setup_db()
    print("Database: Ready")
except Exception as e:
    print("Database: Unavailable")

from upstox_live_trader import AdaptiveTrader
trader = AdaptiveTrader()

from upstox_auth import run_in_background, get_token
run_in_background()
print("[AUTH] Login page: {}".format(os.environ.get('UPSTOX_REDIRECT_URI', '')))

time.sleep(2)

# If token already exists pass it to trader
existing_token = os.environ.get('UPSTOX_ACCESS_TOKEN')
if existing_token:
    trader.set_access_token(existing_token)
    print("[AUTH] Existing token loaded — options ready!")
else:
    print("[AUTH] Waiting for login at Railway URL...")
    # Wait for login (max 5 mins)
    for _ in range(60):
        token = get_token()
        if token:
            trader.set_access_token(token)
            print("[AUTH] Token received — options ready!")
            break
        time.sleep(5)

trader.run()
