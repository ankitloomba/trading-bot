import os
from datetime import datetime
import pytz

IST = pytz.timezone('Asia/Kolkata')
now = datetime.now(IST)

print("""
🔥🔥🔥🔥🔥🔥🔥🔥🔥🔥🔥🔥🔥🔥🔥🔥🔥🔥🔥🔥
        INTRA GINI 🔥
   Intelligent Intraday Trading Bot
   by Ankit Loomba
🔥🔥🔥🔥🔥🔥🔥🔥🔥🔥🔥🔥🔥🔥🔥🔥🔥🔥🔥🔥
""")
print("Started: {}".format(now.strftime('%Y-%m-%d %H:%M:%S IST')))
print("Capital: Rs.{:,.0f}".format(float(os.environ.get('STARTING_CAPITAL', 5000))))
print("Broker:  {}".format(os.environ.get('BROKER', 'PAPER')))
print("Mode:    Adaptive (Sequential + Parallel)")
print("A/B:     Trailing stop vs Fixed target")
print("="*42)

try:
    from db import setup_db
    setup_db()
    print("Database: Ready")
except Exception as e:
    print("Database: Unavailable")

from upstox_live_trader import AdaptiveTrader
trader = AdaptiveTrader()
trader.run()
