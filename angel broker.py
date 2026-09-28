"""
Angel One Broker - Auto login + real orders
No static IP restrictions!
Uses SmartAPI (Angel One's official API)
"""
import os
import time
import pyotp
import requests
import yfinance as yf
from datetime import datetime
import pytz

BASE_URL = "https://apiconnect.angelbroking.com"
IST = pytz.timezone("Asia/Kolkata")

# Maps yfinance index symbols → tradeable stock symbols on NSE
INDEX_TO_STOCK = {
    "^NSEBANK": "HDFCBANK.NS",
    "^NSEI":    "RELIANCE.NS",
    "^CNXIT":   "INFY.NS",
}

# Angel One symbol info: symbol name, scripcode (token), exchange
SYMBOL_MAP = {
    "^NSEBANK":    {"symbol": "BANKNIFTY", "token": "26009", "exchange": "NSE"},
    "^NSEI":       {"symbol": "NIFTY",     "token": "26000", "exchange": "NSE"},
    "^CNXIT":      {"symbol": "NIFTY IT",  "token": "26003", "exchange": "NSE"},
    "HDFCBANK.NS": {"symbol": "HDFCBANK",  "token": "1333",  "exchange": "NSE"},
    "RELIANCE.NS": {"symbol": "RELIANCE",  "token": "2885",  "exchange": "NSE"},
    "INFY.NS":     {"symbol": "INFY",      "token": "1594",  "exchange": "NSE"},
}


class AngelBroker:
    def __init__(self):
        self.api_key      = os.environ.get("ANGEL_API_KEY", "")
        self.client_id    = os.environ.get("ANGEL_CLIENT_ID", "")
        self.password     = os.environ.get("ANGEL_PASSWORD", "") or os.environ.get("ANGEL_MPIN", "")
        self.totp_secret  = os.environ.get("ANGEL_TOTP_SECRET", "")
        self.access_token = None
        self.refresh_token = None
        self.logged_in    = False
        self.login_time   = None
        print("[ANGEL] Broker initialized (API key: {}...)".format(self.api_key[:4] if self.api_key else "MISSING"))

    def _headers(self, auth=True):
        h = {
            "Content-Type":  "application/json",
            "Accept":        "application/json",
            "X-UserType":    "USER",
            "X-SourceID":    "WEB",
            "X-ClientLocalIP": "127.0.0.1",
            "X-ClientPublicIP": "127.0.0.1",
            "X-MACAddress":  "00:00:00:00:00:00",
            "X-PrivateKey":  self.api_key,
        }
        if auth and self.access_token:
            h["Authorization"] = "Bearer {}".format(self.access_token)
        return h

    def login(self):
        """Auto-login to Angel One using API key + password + TOTP. No IP restrictions!"""
        try:
            totp = pyotp.TOTP(self.totp_secret).now()
            print("[ANGEL] Attempting login (client: {}, TOTP: {})...".format(self.client_id, totp))

            payload = {
                "clientcode": self.client_id,
                "password":   self.password,
                "totp":       totp,
            }
            resp = requests.post(
                "{}/rest/auth/angelbroking/user/v1/loginByPassword".format(BASE_URL),
                headers=self._headers(auth=False),
                json=payload,
                timeout=15
            )
            data = resp.json()

            if data.get("status") and data.get("data"):
                self.access_token  = data["data"].get("jwtToken")
                self.refresh_token = data["data"].get("refreshToken")
                self.logged_in     = True
                self.login_time    = datetime.now(IST)
                print("[ANGEL] ✅ Login successful! Token: {}...".format(
                    self.access_token[:20] if self.access_token else "?"))
                return True
            else:
                print("[ANGEL] ❌ Login failed: {}".format(data.get("message", "Unknown error")))
                print("[ANGEL] Response: {}".format(data))
                return False

        except Exception as e:
            print("[ANGEL] ❌ Login error: {}".format(e))
            return False

    def ensure_logged_in(self):
        """Login if not already logged in. Re-login if token older than 6 hours."""
        if not self.logged_in or not self.access_token:
            return self.login()
        if self.login_time:
            age_hours = (datetime.now(IST) - self.login_time).total_seconds() / 3600
            if age_hours > 6:
                print("[ANGEL] Token expired ({}h old), re-logging in...".format(int(age_hours)))
                return self.login()
        return True

    def get_ltp_yfinance(self, yf_symbol):
        """Get LTP using yfinance (reliable, no auth needed)."""
        try:
            ticker = yf.Ticker(yf_symbol)
            hist = ticker.history(period="1d", interval="1m")
            if not hist.empty:
                ltp = float(hist["Close"].iloc[-1])
                return ltp
        except Exception as e:
            print("[ANGEL] yfinance error for {}: {}".format(yf_symbol, e))
        return None

    def get_funds(self):
        """Get available margin/funds from Angel One."""
        if not self.ensure_logged_in():
            return None
        try:
            resp = requests.get(
                "{}/rest/secure/angelbroking/user/v1/getRMS".format(BASE_URL),
                headers=self._headers(),
                timeout=10
            )
            data = resp.json()
            if data.get("status") and data.get("data"):
                net = data["data"].get("net", 0)
                print("[ANGEL] Available funds: Rs.{:.2f}".format(float(net)))
                return float(net)
            print("[ANGEL] Funds error: {}".format(data.get("message")))
        except Exception as e:
            print("[ANGEL] Funds fetch error: {}".format(e))
        return None

    def buy_stock(self, symbol, capital):
        """
        Place a real intraday BUY order on Angel One.
        symbol: yfinance-style symbol (e.g. "^NSEBANK", "RELIANCE.NS")
        capital: rupee amount to deploy
        Returns position dict or None on failure.
        """
        if not self.ensure_logged_in():
            print("[ANGEL] Not logged in — cannot place order")
            return None

        # Map index symbols to tradeable stocks
        trade_symbol = INDEX_TO_STOCK.get(symbol, symbol)
        sym_info = SYMBOL_MAP.get(trade_symbol) or SYMBOL_MAP.get(symbol)
        if not sym_info:
            print("[ANGEL] No symbol mapping for: {}".format(symbol))
            return None

        # Get LTP via yfinance
        ltp = self.get_ltp_yfinance(trade_symbol)
        if not ltp or ltp <= 0:
            print("[ANGEL] No LTP for {} — skipping".format(trade_symbol))
            return None

        qty = max(1, int(capital / ltp))
        print("[ANGEL] BUY {} x {} @ Rs.{:.2f} (total Rs.{:.2f})".format(
            qty, sym_info["symbol"], ltp, qty * ltp))

        try:
            payload = {
                "variety":         "NORMAL",
                "tradingsymbol":   sym_info["symbol"],
                "symboltoken":     sym_info["token"],
                "transactiontype": "BUY",
                "exchange":        sym_info["exchange"],
                "ordertype":       "MARKET",
                "producttype":     "INTRADAY",
                "duration":        "DAY",
                "quantity":        str(qty),
                "price":           "0",
                "triggerprice":    "0",
                "squareoff":       "0",
                "stoploss":        "0",
            }
            resp = requests.post(
                "{}/rest/secure/angelbroking/order/v1/placeOrder".format(BASE_URL),
                headers=self._headers(),
                json=payload,
                timeout=15
            )
            data = resp.json()
            if data.get("status") and data.get("data"):
                order_id = data["data"].get("orderid")
                print("[ANGEL] ✅ BUY order placed! Order ID: {}".format(order_id))
                return {
                    "symbol":    symbol,
                    "trade_sym": sym_info["symbol"],
                    "qty":       qty,
                    "entry":     ltp,
                    "order_id":  order_id,
                    "broker":    "angel",
                    "peak":      ltp,
                    "stop":      ltp * (1 - float(os.environ.get("STOP_LOSS", "0.005"))),
                }
            else:
                print("[ANGEL] ❌ Order failed: {}".format(data.get("message", data)))
                return None

        except Exception as e:
            print("[ANGEL] ❌ BUY error: {}".format(e))
            return None

    def sell_stock(self, position):
        """Square off an intraday position on Angel One."""
        if not self.ensure_logged_in():
            print("[ANGEL] Not logged in — cannot place sell order")
            return False

        sym_info = SYMBOL_MAP.get(position.get("trade_sym")) or SYMBOL_MAP.get(position.get("symbol"))
        if not sym_info:
            # Try to resolve
            trade_sym = INDEX_TO_STOCK.get(position["symbol"], position["symbol"])
            sym_info = SYMBOL_MAP.get(trade_sym)

        if not sym_info:
            print("[ANGEL] No symbol info for sell: {}".format(position))
            return False

        qty = position.get("qty", 1)
        ltp = self.get_ltp_yfinance(position.get("symbol", position.get("trade_sym", "")))

        print("[ANGEL] SELL {} x {} @ Rs.{:.2f}".format(qty, sym_info["symbol"], ltp or 0))

        try:
            payload = {
                "variety":         "NORMAL",
                "tradingsymbol":   sym_info["symbol"],
                "symboltoken":     sym_info["token"],
                "transactiontype": "SELL",
                "exchange":        sym_info["exchange"],
                "ordertype":       "MARKET",
                "producttype":     "INTRADAY",
                "duration":        "DAY",
                "quantity":        str(qty),
                "price":           "0",
                "triggerprice":    "0",
            }
            resp = requests.post(
                "{}/rest/secure/angelbroking/order/v1/placeOrder".format(BASE_URL),
                headers=self._headers(),
                json=payload,
                timeout=15
            )
            data = resp.json()
            if data.get("status"):
                print("[ANGEL] ✅ SELL order placed! Order ID: {}".format(
                    data.get("data", {}).get("orderid")))
                return True
            else:
                print("[ANGEL] ❌ SELL failed: {}".format(data.get("message", data)))
                return False

        except Exception as e:
            print("[ANGEL] ❌ SELL error: {}".format(e))
            return False

    def get_positions(self):
        """Fetch current open positions."""
        if not self.ensure_logged_in():
            return []
        try:
            resp = requests.get(
                "{}/rest/secure/angelbroking/order/v1/getPosition".format(BASE_URL),
                headers=self._headers(),
                timeout=10
            )
            data = resp.json()
            if data.get("status") and data.get("data"):
                return data["data"]
        except Exception as e:
            print("[ANGEL] Positions error: {}".format(e))
        return []

    def status(self):
        return {
            "logged_in":  self.logged_in,
            "login_time": self.login_time.strftime("%H:%M IST") if self.login_time else "Never",
            "client":     self.client_id,
        }
