"""
UPSTOX MAIN - Entry point for Upstox live trading
Run this file to start the Upstox trading bot
"""
import os
from datetime import datetime
import pytz

IST = pytz.timezone('Asia/Kolkata')
now = datetime.now(IST)

print("="*60)
print("  UPSTOX TRADING BOT")
print("  {}".format(now.strftime('%Y-%m-%d %H:%M:%S IST')))
print("  Profit: {}% | Stop: {}%".format(
    float(os.environ.get('PROFIT_TARGET', 0.01)) * 100,
    float(os.environ.get('STOP_LOSS', 0.005)) * 100
))
print("="*60)

try:
    from db import setup_db
    setup_db()
    print("Database: Ready")
except Exception as e:
    print("Database: Unavailable")

from upstox_live_trader import UpstoxLiveTrader
trader = UpstoxLiveTrader()
trader.run()
