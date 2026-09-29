"""
Multi-Index Options Trader (Bank Nifty, Nifty 50, Nifty IT)
- Buys CE for bullish signals, PE for bearish
- Profit target: 100% gain on premium → exit
- Trailing stop: 30% drop from peak (after 10% gain)
- Hard stop: 40% loss of premium
- Capital: ~₹3,000 per options trade
- Max 2 concurrent options positions
"""
import os
import requests
from datetime import datetime, timedelta
import pytz

IST = pytz.timezone('Asia/Kolkata')

# Index name → options instrument prefix + lot size
INDEX_CONFIG = {
    "^NSEBANK": {"name": "BANKNIFTY", "lot": 15, "strike_step": 100},
    "^NSEI":    {"name": "NIFTY",     "lot": 25, "strike_step": 50},
    "^CNXIT":   {"name": "NIFTYIT",   "lot": 25, "strike_step": 50},
}


class MultiOptionsTrader:
    def __init__(self, broker_token):
        self.token = broker_token
        self.base_url = "https://api.upstox.com/v2"
        self.options_capital = 3000  # Per trade capital
        self.headers = {
            'Authorization': 'Bearer {}'.format(self.token),
            'Accept': 'application/json',
            'Content-Type': 'application/json'
        }

    def get_expiry(self, index_symbol):
        """Get nearest weekly expiry.
        Bank Nifty expires every Wednesday; Nifty 50 every Thursday.
        """
        today = datetime.now(IST)
        # Bank Nifty → Wednesday (2), Nifty → Thursday (3), IT → Thursday (3)
        target_day = 2 if index_symbol == "^NSEBANK" else 3
        days_ahead = target_day - today.weekday()
        if days_ahead <= 0:
            days_ahead += 7
        expiry = today + timedelta(days=days_ahead)
        return expiry.strftime('%y%b%d').upper()  # e.g. 26OCT02

    def get_atm_strike(self, spot_price, step):
        """Round to nearest strike step."""
        return round(spot_price / step) * step

    def get_instrument_key(self, index_symbol, strike, option_type, expiry):
        """
        Format: NSE_FO|BANKNIFTY26SEP56000CE
        """
        cfg = INDEX_CONFIG.get(index_symbol, INDEX_CONFIG["^NSEBANK"])
        return "NSE_FO|{}{}{}{}".format(cfg['name'], expiry, strike, option_type)

    def get_option_ltp(self, instrument_key):
        """Get Last Traded Price of option."""
        try:
            res = requests.get(
                "{}/market-quote/ltp".format(self.base_url),
                headers=self.headers,
                params={'symbol': instrument_key}
            )
            data = res.json()
            if data.get('status') == 'success':
                ltp = list(data['data'].values())[0]['last_price']
                return float(ltp)
            return None
        except Exception as e:
            print("[OPTIONS] LTP error: {}".format(e))
            return None

    def buy_option(self, index_symbol, spot_price, signal_type='BUY'):
        """
        Buy CE for bullish signal (BUY), PE for bearish (SELL).
        Goes 1-strike OTM for better risk/reward.
        """
        try:
            cfg = INDEX_CONFIG.get(index_symbol, INDEX_CONFIG["^NSEBANK"])
            option_type = 'CE' if signal_type == 'BUY' else 'PE'
            step = cfg['strike_step']
            lot_size = cfg['lot']
            index_name = cfg['name']

            atm = self.get_atm_strike(spot_price, step)
            if option_type == 'CE':
                strike = atm + step  # 1 OTM
            else:
                strike = atm - step  # 1 OTM

            expiry = self.get_expiry(index_symbol)
            instrument_key = self.get_instrument_key(index_symbol, strike, option_type, expiry)

            print("[OPTIONS] Buying {}-{} | Strike:{} | Expiry:{}".format(
                index_name, option_type, strike, expiry))

            premium = self.get_option_ltp(instrument_key)
            if not premium:
                print("[OPTIONS] Could not get premium — skipping")
                return None

            cost = premium * lot_size
            print("[OPTIONS] Premium: Rs.{:.2f} | 1 lot cost: Rs.{:.2f} | Budget: Rs.{:.0f}".format(
                premium, cost, self.options_capital))

            if cost > self.options_capital:
                print("[OPTIONS] Too expensive (Rs.{:.0f} > Rs.{:.0f}) — skipping".format(
                    cost, self.options_capital))
                return None

            # Place order
            res = requests.post(
                "{}/order/place".format(self.base_url),
                headers=self.headers,
                json={
                    'quantity': lot_size,
                    'product': 'I',        # MIS — intraday
                    'validity': 'DAY',
                    'price': 0,
                    'tag': 'intragini-options',
                    'instrument_token': instrument_key,
                    'order_type': 'MARKET',
                    'transaction_type': 'BUY',
                    'disclosed_quantity': 0,
                    'trigger_price': 0,
                    'is_amo': False
                }
            )
            data = res.json()
            if data.get('status') == 'success':
                order_id = data['data']['order_id']
                print("[OPTIONS] ✅ Order placed! ID:{} | {}-{} @ Rs.{}".format(
                    order_id, index_name, option_type, premium))
                return {
                    'order_id': order_id,
                    'instrument_key': instrument_key,
                    'index_symbol': index_symbol,
                    'index_name': index_name,
                    'option_type': option_type,
                    'strike': strike,
                    'entry_premium': premium,
                    'highest_premium': premium,
                    'lot_size': lot_size,
                    'capital_used': cost
                }
            else:
                print("[OPTIONS] ❌ Order failed: {}".format(data))
                return None

        except Exception as e:
            print("[OPTIONS] Buy error: {}".format(e))
            return None

    def should_exit_option(self, position):
        """
        Exit rules (in priority order):
          1. Profit target   — premium doubles (100% gain)           → PROFIT_TARGET
          2. Breakeven stop  — once up 25%, hard stop moves to entry → BREAKEVEN_STOP
          3. Dynamic trail   — tightens as profit grows:
                               >80% gain  → trail 10% from peak
                               >50% gain  → trail 15% from peak
                               >20% gain  → trail 20% from peak
                               >10% gain  → trail 25% from peak
          4. Time stop       — flat/losing after 25 min → exit       → TIME_STOP
          5. Hard stop       — 25% loss from entry                   → HARD_STOP
        """
        from datetime import datetime
        import pytz
        IST = pytz.timezone('Asia/Kolkata')

        current_premium = self.get_option_ltp(position['instrument_key'])
        if not current_premium:
            return False, None, 0

        # Track peak and entry time
        if current_premium > position['highest_premium']:
            position['highest_premium'] = current_premium
        if 'entry_time' not in position:
            position['entry_time'] = datetime.now(IST)

        entry = position['entry_premium']
        peak  = position['highest_premium']
        pnl   = (current_premium - entry) * position['lot_size']
        pnl_pct = (current_premium - entry) / entry * 100
        held_min = (datetime.now(IST) - position['entry_time']).seconds / 60

        # 1. Profit target: premium doubled
        if current_premium >= entry * 2.0:
            print("[OPTIONS] 🎯 PROFIT TARGET! +{:.1f}% | P&L: Rs.{:+.0f}".format(pnl_pct, pnl))
            return True, 'PROFIT_TARGET', pnl

        # 2. Breakeven stop: once up 25%, never let it go below entry
        if peak >= entry * 1.25 and current_premium <= entry:
            print("[OPTIONS] 🔒 BREAKEVEN_STOP | Was up, now back to entry | P&L: Rs.{:+.0f}".format(pnl))
            return True, 'BREAKEVEN_STOP', pnl

        # 3. Dynamic trailing stop — tightens as profit grows
        if peak > entry * 1.10:
            if pnl_pct >= 80:
                trail_floor = peak * 0.90   # keep 90% of peak
            elif pnl_pct >= 50:
                trail_floor = peak * 0.85
            elif pnl_pct >= 20:
                trail_floor = peak * 0.80
            else:
                trail_floor = peak * 0.75   # default 25% trail
            if current_premium < trail_floor:
                print("[OPTIONS] 📉 TRAIL_STOP | Rs.{:.2f} < floor Rs.{:.2f} | P&L: Rs.{:+.0f}".format(
                    current_premium, trail_floor, pnl))
                return True, 'TRAIL_STOP', pnl

        # 4. Time stop: held 25+ min and still a loser or barely moving
        if held_min >= 25 and pnl_pct < 10:
            print("[OPTIONS] ⏱ TIME_STOP | {:.0f}min held, only {:.1f}% gain | P&L: Rs.{:+.0f}".format(
                held_min, pnl_pct, pnl))
            return True, 'TIME_STOP', pnl

        # 5. Hard stop: 25% loss (tighter than before)
        if current_premium < entry * 0.75:
            print("[OPTIONS] 🛑 HARD_STOP | Rs.{:.2f} | Loss: Rs.{:.0f}".format(current_premium, pnl))
            return True, 'HARD_STOP', pnl

        print("[OPTIONS] Holding {}-{} | Rs.{:.2f} | {:+.1f}% (Rs.{:+.0f}) | {:.0f}min".format(
            position['index_name'], position['option_type'],
            current_premium, pnl_pct, pnl, held_min))
        return False, None, 0

    def sell_option(self, position):
        """Square off the option position."""
        try:
            res = requests.post(
                "{}/order/place".format(self.base_url),
                headers=self.headers,
                json={
                    'quantity': position['lot_size'],
                    'product': 'I',
                    'validity': 'DAY',
                    'price': 0,
                    'tag': 'intragini-options-exit',
                    'instrument_token': position['instrument_key'],
                    'order_type': 'MARKET',
                    'transaction_type': 'SELL',
                    'disclosed_quantity': 0,
                    'trigger_price': 0,
                    'is_amo': False
                }
            )
            data = res.json()
            if data.get('status') == 'success':
                print("[OPTIONS] ✅ Sold! Order: {}".format(data['data']['order_id']))
                return True
            print("[OPTIONS] ❌ Sell failed: {}".format(data))
            return False
        except Exception as e:
            print("[OPTIONS] Sell error: {}".format(e))
            return False
