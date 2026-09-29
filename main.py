"""
Intra Gini 🔥 — Main entry point
Dual broker: Upstox (primary, manual login) + Angel One (backup, auto-login)
Container stays alive via blocking main loop.
"""
import os
import sys
import time
import signal
import threading
import pytz
from datetime import datetime

IST = pytz.timezone("Asia/Kolkata")


def ist_now():
    return datetime.now(IST)


def log(msg):
    ts = ist_now().strftime("%H:%M:%S IST")
    print("[{}] {}".format(ts, msg))


# ──────────────────── Graceful shutdown ─────────────────
_shutdown = threading.Event()

def _handle_signal(sig, frame):
    log("Received signal {} — shutting down gracefully...".format(sig))
    _shutdown.set()

signal.signal(signal.SIGTERM, _handle_signal)
signal.signal(signal.SIGINT, _handle_signal)


# ──────────────────── Main ──────────────────────────────
def main():
    log("=" * 60)
    log("  Intra Gini 🔥 - DUAL BROKER TRADER")
    log("=" * 60)

    # ── Config ──────────────────────────────────────────
    paper_mode      = os.environ.get("PAPER_TRADE", "false").lower() == "true"
    starting_cap    = float(os.environ.get("STARTING_CAPITAL", "5000"))
    scan_interval   = int(os.environ.get("SCAN_INTERVAL", "60"))

    log("Capital:   Rs.{:,.0f}".format(starting_cap))
    log("Paper:     {}".format(paper_mode))
    log("Interval:  {}s".format(scan_interval))

    # ── Angel One broker (auto-login, no IP restriction) ─
    angel_broker = None
    try:
        from angel_broker import AngelBroker
        angel_broker = AngelBroker()
        log("[ANGEL] Auto-logging into Angel One...")
        ok = angel_broker.login()
        if ok:
            log("[ANGEL] ✅ Angel One ready!")
        else:
            log("[ANGEL] ⚠️ Angel One login failed — will retry later")
    except ImportError:
        log("[ANGEL] angel_broker.py not found — Angel One disabled")
    except Exception as e:
        log("[ANGEL] Startup error: {}".format(e))

    # ── Auth server (Upstox OAuth + Angel status page) ───
    try:
        import upstox_auth
        if angel_broker:
            upstox_auth.set_angel_broker(angel_broker)
        upstox_auth.run_in_background()   # non-blocking — starts server in thread
    except Exception as e:
        log("[AUTH] Auth server error: {}".format(e))

    # ── Database ─────────────────────────────────────────
    db = None
    try:
        from database import Database
        db = Database()
        db.init_tables()
        log("Database: Connected")
    except Exception as e:
        log("Database: Not available ({})".format(e))

    # ── Trader setup ─────────────────────────────────────
    trader = None
    try:
        from upstox_live_trader import AdaptiveTrader
        trader = AdaptiveTrader(paper_mode=paper_mode)
        # Give Angel One broker to trader so it can use it
        if angel_broker and angel_broker.logged_in:
            trader.set_angel_broker(angel_broker)
            log("Primary broker: Angel One (auto-logged in)")
        else:
            log("Primary broker: Upstox (waiting for manual login)")
    except Exception as e:
        log("[TRADER] Init error: {}".format(e))

    # ── Wait for Upstox token (non-blocking, max 10 min) ─
    upstox_token_received = threading.Event()

    def _on_upstox_token(token):
        log("[UPSTOX] ✅ Token received — activating Upstox!")
        if trader:
            trader.set_access_token(token)
        upstox_token_received.set()

    try:
        import upstox_auth
        upstox_auth.on_token(_on_upstox_token)
    except Exception:
        pass

    # ── Start trader in background ────────────────────────
    trader_thread = None
    if trader:
        def run_trader():
            try:
                log("[TRADER] Starting scan loop...")
                trader.run()
            except Exception as e:
                log("[TRADER] Crash: {}".format(e))
                import traceback
                traceback.print_exc()

        trader_thread = threading.Thread(target=run_trader, daemon=True)
        trader_thread.start()
        log("[TRADER] Scan loop started in background")
    else:
        log("[TRADER] Trader not available — running auth server only")

    # ── Print status every 5 minutes ─────────────────────
    def _status_loop():
        while not _shutdown.is_set():
            time.sleep(300)  # 5 minutes
            if _shutdown.is_set():
                break
            now = ist_now()
            log("--- Status @ {} ---".format(now.strftime("%H:%M IST")))

            if angel_broker:
                st = angel_broker.status()
                log("[ANGEL] Logged in: {} (since {})".format(st["logged_in"], st["login_time"]))

            try:
                import upstox_auth
                tok = upstox_auth.get_upstox_token()
                log("[UPSTOX] Token: {}".format("Active" if tok else "Not logged in"))
            except Exception:
                pass

            if trader:
                log("[TRADER] Positions: {} | PnL: Rs.{:.2f}".format(
                    len(getattr(trader, "positions", [])),
                    getattr(trader, "daily_pnl", 0.0)
                ))

    status_thread = threading.Thread(target=_status_loop, daemon=True)
    status_thread.start()

    # ── Re-login Angel One at 9:00 AM daily ─────────────
    def _angel_daily_relogin():
        while not _shutdown.is_set():
            now = ist_now()
            # Target: 9:00 AM IST
            if now.hour == 9 and now.minute == 0:
                log("[ANGEL] Daily 9:00 AM re-login...")
                if angel_broker:
                    angel_broker.login()
                    if trader and angel_broker.logged_in:
                        trader.set_angel_broker(angel_broker)
                time.sleep(61)  # avoid re-triggering in same minute
            time.sleep(30)

    angel_relogin_thread = threading.Thread(target=_angel_daily_relogin, daemon=True)
    angel_relogin_thread.start()

    # ── BLOCKING MAIN LOOP — keeps container alive ────────
    log("Bot running. Upstox login: https://trading-bot-production-65cd.up.railway.app")
    log("Waiting for shutdown signal...")

    try:
        while not _shutdown.is_set():
            time.sleep(5)

            # If trader thread died, restart it
            if trader_thread and not trader_thread.is_alive():
                log("[TRADER] Thread died — restarting in 10s...")
                time.sleep(10)
                if not _shutdown.is_set():
                    trader_thread = threading.Thread(target=run_trader, daemon=True)
                    trader_thread.start()
                    log("[TRADER] Restarted")

    except KeyboardInterrupt:
        log("Keyboard interrupt — shutting down")

    _shutdown.set()
    log("Intra Gini 🔥 stopped.")
    sys.exit(0)


if __name__ == "__main__":
    main()
