import os
from datetime import datetime
import pytz

IST = pytz.timezone('Asia/Kolkata')
now = datetime.now(IST)

print("="*60)
print("  TRADING BOT v2 - ADAPTIVE + A/B TEST")
print("  {}".format(now.strftime('%Y-%m-%d %H:%M:%S IST')))
print("="*60)

try:
    from db import setup_db
    setup_db()
    print("Database: Ready")
except Exception as e:
    print("Database: Unavailable")

from upstox_live_trader import AdaptiveTrader
trader = AdaptiveTrader()
trader.run()
