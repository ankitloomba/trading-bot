from backtest_3day import main as run_backtest
from db import setup_db, log_trade, log_daily_summary
from datetime import date

print("Setting up database...")
try:
    setup_db()
    print("DB ready!")
except Exception as e:
    print("DB setup failed (running without DB): {}".format(e))

print("\nRunning backtest...")
run_backtest()
