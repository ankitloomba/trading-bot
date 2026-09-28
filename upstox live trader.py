"""
Intra Gini 🔥 — Adaptive Multi-Symbol Trader
Primary broker: Upstox (manual login) | Backup: Angel One (auto-login)
Scans 6 symbols every 60s. Real orders when logged in, paper otherwise.
"""
import os
import time
import json
import threading
import pytz
import yfinance as yf
from datetime import datetime, timedelta

IST = pytz.timezone("Asia/Kolkata")

# ── Config from env ───────────────────────────────────────
SYMBOLS          = os.environ.get("SYMBOLS", "^NSEBANK,^NSEI,^CNXIT,RELIANCE.NS,HDFCBANK.NS,INFY.NS").split(",")
OPTIONS_SYMBOLS  = ["^NSEBANK", "^NSEI", "^CNXIT"]
STARTING_CAP     = float(os.environ.get("STARTING_CAPITAL", "5000"))
MAX_POSITIONS    = int(os.environ.get("MAX_POSITIONS", "3"))
BUFFER_CASH      = float(os.environ.get("BUFFER_CASH", "500"))
OPTIONS_CAP      = float(os.environ.get("OPTIONS_CAPITAL", "2000"))
OPTIONS_ENABLED  = os.environ.get("OPTIONS_ENABLED", "true").lower() == "true"
MIN_SCORE        = int(os.environ.get("MIN_SIGNAL_SCORE", "5"))
STOP_LOSS        = float(os.environ.get("STOP_LOSS", "0.005"))
TRAIL_PCT        = float(os.environ.get("TRAIL_PCT", "0.003"))
MAX_LOSS_DAY     = float(os.environ.get("MAX_LOSS_PER_DAY", "500"))
AB_TEST          = os.environ.get("AB_TEST_ENABLED", "true").lower() == "true"
SCAN_INTERVAL    = int(os.environ.get("SCAN_INTERVAL", "60"))

STOCKS_CAP       = STARTING_CAP - OPTIONS_CAP - BUFFER_CASH  # ~2500


def ist_now():
    return datetime.now(IST)


def is_market_open():
    now = ist_now()
    if now.weekday() >= 5:   # Saturday/Sunday
        return False
    market_open  = now.replace(hour=9,  minute=15, second=0, microsecond=0)
    market_close = now.replace(hour=15, minute=25, second=0, microsecond=0)
    return market_open <= now <= market_close


def is_trading_time():
    """9:15 AM – 3:00 PM IST (stop new entries at 3 PM)."""
    now = ist_now()
    if now.weekday() >= 5:
        return False
    open_t  = now.replace(hour=9,  minute=15, second=0, microsecond=0)
    close_t = now.replace(hour=15, minute=0,  second=0, microsecond=0)
    return open_t <= now <= close_t


def log(msg):
    print("[{}] {}".format(ist_now().strftime("%H:%M:%S"), msg))


# ── Strategy: signal scoring 1-10 ────────────────────────
def get_signal(df, symbol="", debug=False):
    """Score 0-10. Minimum MIN_SCORE to trade."""
    try:
        if df is None or len(df) < 20:
            return 0, {}
        close  = df["Close"].squeeze()
        volume = df["Volume"].squeeze()
        high   = df["High"].squeeze()

        score  = 0
        detail = {}

        # 1. Breakout: price > 20-candle high (0-3 pts)
        prev_high = high.iloc[-21:-1].max()
        curr      = float(close.iloc[-1])
        if curr > prev_high * 1.001:
            score += 3
            detail["breakout"] = "YES ({:.2f} > {:.2f})".format(curr, prev_high)
        elif curr > prev_high * 0.998:
            score += 1
            detail["breakout"] = "NEAR"
        else:
            detail["breakout"] = "NO"

        # 2. RSI 40-65 (0-2 pts)
        delta     = close.diff()
        gain      = delta.clip(lower=0).rolling(14).mean()
        loss      = (-delta.clip(upper=0)).rolling(14).mean()
        rs        = gain / (loss + 1e-9)
        rsi       = float(100 - (100 / (1 + rs.iloc[-1])))
        if 40 <= rsi <= 65:
            score += 2
            detail["rsi"] = "{:.1f} ✓".format(rsi)
        elif 30 <= rsi <= 75:
            score += 1
            detail["rsi"] = "{:.1f} ~".format(rsi)
        else:
            detail["rsi"] = "{:.1f} ✗".format(rsi)

        # 3. Green candles: last 3 (0-2 pts)
        opens  = df["Open"].squeeze()
        greens = sum(1 for i in range(-3, 0) if float(close.iloc[i]) > float(opens.iloc[i]))
        score += greens * (2 // 3 + (1 if greens == 3 else 0))
        score  = min(score, score)   # cap handled below
        detail["green_candles"] = "{}/3".format(greens)

        # 4. Trading time (0-2 pts) — best 9:30-11:30, 13:30-14:30
        now = ist_now()
        hr  = now.hour + now.minute / 60
        if (9.5 <= hr <= 11.5) or (13.5 <= hr <= 14.5):
            score += 2
            detail["time"] = "PRIME"
        elif 9.25 <= hr <= 15.0:
            score += 1
            detail["time"] = "OK"
        else:
            detail["time"] = "BAD"

        # 5. Volume spike (0-1 pt)
        avg_vol = float(volume.iloc[-20:-1].mean())
        cur_vol = float(volume.iloc[-1])
        if avg_vol > 0 and cur_vol > avg_vol * 1.5:
            score += 1
            detail["volume"] = "SPIKE {:.1f}x".format(cur_vol / avg_vol)
        else:
            detail["volume"] = "NORMAL"

        score = min(score, 10)
        if debug:
            log("[SCAN] {} | Score:{}/10 | Price:{:.2f} | {}".format(
                symbol.replace("^", ""), score, curr, detail))
        return score, detail

    except Exception as e:
        log("[SIGNAL] Error for {}: {}".format(symbol, e))
        return 0, {}


# ── Upstox Broker ─────────────────────────────────────────
class UpstoxBroker:
    INDEX_TO_STOCK = {
        "^NSEBANK": "HDFCBANK.NS",
        "^NSEI":    "RELIANCE.NS",
        "^CNXIT":   "INFY.NS",
    }
    UPSTOX_SYMBOLS = {
        "HDFCBANK.NS": {"symbol": "HDFCBANK", "exchange": "NSE"},
        "RELIANCE.NS": {"symbol": "RELIANCE", "exchange": "NSE"},
        "INFY.NS":     {"symbol": "INFY",     "exchange": "NSE"},
    }

    def __init__(self, access_token=None):
        self.access_token = access_token
        self.client_id    = os.environ.get("UPSTOX_CLIENT_ID", "")
        self.client_secret= os.environ.get("UPSTOX_CLIENT_SECRET", "")

    def set_access_token(self, token):
        self.access_token = token
        log("[UPSTOX] Access token set ✅")

    def get_ltp_yfinance(self, yf_symbol):
        try:
            ticker = yf.Ticker(yf_symbol)
            hist   = ticker.history(period="1d", interval="1m")
            if not hist.empty:
                return float(hist["Close"].iloc[-1])
        except Exception as e:
            log("[UPSTOX] yfinance error {}: {}".format(yf_symbol, e))
        return None

    def buy_stock(self, symbol, capital):
        if not self.access_token:
            log("[UPSTOX] No token — cannot buy {}".format(symbol))
            return None

        trade_sym = self.INDEX_TO_STOCK.get(symbol, symbol)
        info      = self.UPSTOX_SYMBOLS.get(trade_sym)
        if not info:
            log("[UPSTOX] No symbol map for {}".format(trade_sym))
            return None

        ltp = self.get_ltp_yfinance(trade_sym)
        if not ltp:
            log("[UPSTOX] No LTP for {}".format(trade_sym))
            return None

        qty = max(1, int(capital / ltp))
        log("[UPSTOX] BUY {} x {} @ Rs.{:.2f}".format(qty, info["symbol"], ltp))

        import requests
        try:
            resp = requests.post(
                "https://api.upstox.com/v2/order/place",
                headers={
                    "Authorization": "Bearer {}".format(self.access_token),
                    "Content-Type":  "application/json",
                    "Accept":        "application/json",
                },
                json={
                    "quantity":        qty,
                    "product":         "I",        # Intraday
                    "validity":        "DAY",
                    "price":           0,
                    "tag":             "intra-gini",
                    "instrument_token":"NSE_EQ|{}".format(info["symbol"]),
                    "order_type":      "MARKET",
                    "transaction_type":"BUY",
                    "disclosed_quantity": 0,
                    "trigger_price":   0,
                    "is_amo":          False,
                },
                timeout=15
            )
            data = resp.json()
            if data.get("status") == "success":
                order_id = data.get("data", {}).get("order_id")
                log("[UPSTOX] ✅ BUY order: {}".format(order_id))
                return {
                    "symbol":    symbol,
                    "trade_sym": trade_sym,
                    "qty":       qty,
                    "entry":     ltp,
                    "order_id":  order_id,
                    "broker":    "upstox",
                    "peak":      ltp,
                    "stop":      ltp * (1 - STOP_LOSS),
                }
            log("[UPSTOX] Order failed: {}".format(data))
            return None
        except Exception as e:
            log("[UPSTOX] BUY error: {}".format(e))
            return None

    def sell_stock(self, position):
        if not self.access_token:
            log("[UPSTOX] No token — cannot sell")
            return False

        trade_sym = position.get("trade_sym", position.get("symbol"))
        info      = self.UPSTOX_SYMBOLS.get(trade_sym)
        if not info:
            log("[UPSTOX] No symbol map for sell: {}".format(trade_sym))
            return False

        import requests
        try:
            resp = requests.post(
                "https://api.upstox.com/v2/order/place",
                headers={
                    "Authorization": "Bearer {}".format(self.access_token),
                    "Content-Type":  "application/json",
                    "Accept":        "application/json",
                },
                json={
                    "quantity":        position["qty"],
                    "product":         "I",
                    "validity":        "DAY",
                    "price":           0,
                    "instrument_token":"NSE_EQ|{}".format(info["symbol"]),
                    "order_type":      "MARKET",
                    "transaction_type":"SELL",
                    "disclosed_quantity": 0,
                    "trigger_price":   0,
                    "is_amo":          False,
                },
                timeout=15
            )
            data = resp.json()
            if data.get("status") == "success":
                log("[UPSTOX] ✅ SELL order placed")
                return True
            log("[UPSTOX] SELL failed: {}".format(data))
            return False
        except Exception as e:
            log("[UPSTOX] SELL error: {}".format(e))
            return False


# ── Main Trader ───────────────────────────────────────────
class AdaptiveTrader:
    def __init__(self, paper_mode=False):
        self.paper_mode    = paper_mode
        self.upstox        = UpstoxBroker()
        self.angel         = None          # set via set_angel_broker()
        self.positions     = []
        self.daily_pnl     = 0.0
        self.scan_count    = 0
        self.trade_count   = 0
        self._lock         = threading.Lock()

        log("[TRADER] AdaptiveTrader init | Paper: {} | Symbols: {}".format(
            paper_mode, len(SYMBOLS)))

    def set_access_token(self, token):
        """Called when Upstox OAuth completes."""
        self.upstox.set_access_token(token)
        log("[TRADER] Upstox activated — real orders enabled!")

    def set_angel_broker(self, broker):
        """Called by main.py when Angel One is ready."""
        self.angel = broker
        log("[TRADER] Angel One broker connected!")

    def _active_broker(self):
        """Return best available broker. Upstox first, Angel One backup."""
        if self.upstox.access_token:
            return self.upstox, "upstox"
        if self.angel and self.angel.logged_in:
            return self.angel, "angel"
        return None, "paper"

    def _get_data(self, symbol):
        """Fetch 5-min candle data from yfinance."""
        try:
            ticker = yf.Ticker(symbol)
            df     = ticker.history(period="2d", interval="5m")
            if df.empty or len(df) < 20:
                return None
            return df
        except Exception as e:
            log("[DATA] Error for {}: {}".format(symbol, e))
            return None

    def check_entries(self):
        """Scan all symbols for entry signals."""
        if not is_trading_time():
            return

        broker, bname = self._active_broker()
        capital_per   = STOCKS_CAP / max(MAX_POSITIONS, 1)

        for symbol in SYMBOLS:
            with self._lock:
                already_in = any(p["symbol"] == symbol for p in self.positions)
                if already_in:
                    continue
                if len(self.positions) >= MAX_POSITIONS:
                    break

            if self.daily_pnl <= -MAX_LOSS_DAY:
                log("[RISK] Daily loss limit hit — no new trades")
                return

            df    = self._get_data(symbol)
            score, detail = get_signal(df, symbol=symbol, debug=True)

            if score >= MIN_SCORE:
                log("[SIGNAL] 🎯 {} Score:{}/10 — ENTERING!".format(symbol, score))

                if self.paper_mode or broker is None:
                    # Paper trade
                    ltp = float(df["Close"].iloc[-1]) if df is not None else 0
                    pos = {
                        "symbol":  symbol,
                        "qty":     max(1, int(capital_per / ltp)) if ltp else 1,
                        "entry":   ltp,
                        "peak":    ltp,
                        "stop":    ltp * (1 - STOP_LOSS),
                        "broker":  "paper",
                        "score":   score,
                        "trade_id": self.trade_count,
                    }
                    with self._lock:
                        self.positions.append(pos)
                    self.trade_count += 1
                    log("[PAPER] 📝 BUY {} x {} @ Rs.{:.2f}".format(
                        pos["qty"], symbol, ltp))
                else:
                    pos = broker.buy_stock(symbol, capital_per)
                    if pos:
                        pos["score"]    = score
                        pos["trade_id"] = self.trade_count
                        with self._lock:
                            self.positions.append(pos)
                        self.trade_count += 1
                        log("[LIVE] ✅ {} BUY via {} | Score:{}/10".format(
                            symbol, bname, score))

    def check_exits(self):
        """Monitor positions for exit conditions."""
        broker, bname = self._active_broker()

        with self._lock:
            to_exit = []
            for pos in self.positions:
                symbol = pos.get("symbol", "")
                df     = self._get_data(symbol)
                if df is None:
                    continue

                ltp = float(df["Close"].iloc[-1])

                # Update peak (for trailing stop)
                if ltp > pos.get("peak", ltp):
                    pos["peak"] = ltp

                # Trailing stop
                trail_stop = pos["peak"] * (1 - TRAIL_PCT)
                stop       = max(pos.get("stop", 0), trail_stop)

                pnl     = (ltp - pos["entry"]) * pos["qty"]
                pnl_pct = (ltp - pos["entry"]) / pos["entry"] * 100

                # Exit conditions
                exit_reason = None
                if ltp <= stop:
                    exit_reason = "STOP ({:.1f}%)".format(pnl_pct)
                elif not is_trading_time():
                    exit_reason = "EOD SQUAREOFF"
                elif pnl_pct >= 1.0:
                    exit_reason = "TARGET (+{:.1f}%)".format(pnl_pct)

                if exit_reason:
                    to_exit.append((pos, ltp, pnl, exit_reason))

        for pos, ltp, pnl, reason in to_exit:
            log("[EXIT] {} {} @ Rs.{:.2f} | PnL: Rs.{:.2f} | {}".format(
                pos["symbol"], pos.get("broker", "?").upper(), ltp, pnl, reason))

            exited = False
            if self.paper_mode or pos.get("broker") == "paper":
                exited = True
                log("[PAPER] 📝 SELL {} @ Rs.{:.2f}".format(pos["symbol"], ltp))
            elif broker:
                exited = broker.sell_stock(pos)

            if exited:
                self.daily_pnl += pnl
                with self._lock:
                    if pos in self.positions:
                        self.positions.remove(pos)
                log("[PNL] Daily PnL: Rs.{:.2f}".format(self.daily_pnl))

    def run(self):
        """Main scan loop — runs forever until process stops."""
        log("[TRADER] 🚀 Starting scan loop (interval: {}s)".format(SCAN_INTERVAL))
        log("[TRADER] Symbols: {}".format(SYMBOLS))
        log("[TRADER] Options: {}".format("Enabled" if OPTIONS_ENABLED else "Disabled"))

        while True:
            try:
                self.scan_count += 1
                now = ist_now()

                if is_market_open():
                    log("[SCAN #{:04d}] {} | Positions: {} | PnL: Rs.{:.2f}".format(
                        self.scan_count, now.strftime("%H:%M:%S"),
                        len(self.positions), self.daily_pnl))

                    self.check_entries()
                    self.check_exits()

                    # Options trading
                    if OPTIONS_ENABLED:
                        try:
                            from options_trader import MultiOptionsTrader
                            broker, bname = self._active_broker()
                            opt_trader = getattr(self, "_opt_trader", None)
                            if opt_trader is None:
                                self._opt_trader = MultiOptionsTrader(broker=broker)
                                opt_trader = self._opt_trader
                            opt_trader.scan()
                        except ImportError:
                            pass
                        except Exception as e:
                            log("[OPTIONS] Error: {}".format(e))

                elif now.hour >= 15 and now.minute >= 30:
                    # After 3:30 PM — end of day
                    if self.positions:
                        log("[EOD] Squaring off {} positions...".format(len(self.positions)))
                        self.check_exits()
                    if self.scan_count % 60 == 0:
                        log("[EOD] Market closed. Daily PnL: Rs.{:.2f}".format(self.daily_pnl))
                else:
                    if self.scan_count % 30 == 1:
                        log("[WAIT] Market opens at 9:15 AM IST")

                time.sleep(SCAN_INTERVAL)

            except KeyboardInterrupt:
                log("[TRADER] Stopping...")
                break
            except Exception as e:
                log("[TRADER] Scan error: {}".format(e))
                import traceback
                traceback.print_exc()
                time.sleep(10)  # Wait before retry
