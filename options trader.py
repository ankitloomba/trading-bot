"""
Multi-Index Options Trader
Trades CE/PE on: Bank Nifty, Nifty 50, Nifty IT
"""
import os
import requests
from datetime import datetime, timedelta
import pytz

IST = pytz.timezone('Asia/Kolkata')

INDEX_CONFIG = {
    "^NSEBANK": {
        "name": "BANKNIFTY",
        "lot_size": 15,
        "strike_gap": 100,
        "expiry_day": 2,  # Wednesday
    },
    "^NSEI": {
        "name": "NIFTY",
        "lot_size": 50,
        "strike_gap": 50,
        "expiry_day": 3,  # Thursday
    },
    "^CNXIT": {
        "name": "NIFTYIT",
        "lot_size": 35,
        "strike_gap": 100,
        "expiry_day": 3,  # Thursday
    }
}

class MultiOptionsTrader:
    def __init__(self, broker_token):
        self.token = broker_token
        self.base_url = "https://api.upstox.com/v2"
        self.options_capital = int(os.environ.get('OPTIONS_CAPITAL', '2000'))
        self.headers = {
            'Authorization': 'Bearer {}'.format(self.token),
            'Accept': 'application/json',
            'Content-Type': 'application/json'
        }

    def get_expiry(self, expiry_day):
        today = datetime.now(IST)
        days_ahead = expiry_day - today.weekday()
        if days_ahead <= 0:
            days_ahead += 7
        expiry = today + timedelta(days=days_ahead)
        return expiry.strftime('%y%b%d').upper()

    def get_atm_strike(self, spot, gap):
        return round(spot / gap) * gap

    def get_instrument_key(self, index_name, strike, option_type, expiry):
        return "NSE_FO|{}{}{}{}".format(index_name, expiry, strike, option_type)

    def get_option_ltp(self, instrument_key):
        try:
            res = requests.get(
                "{}/market-quote/ltp".format(self.base_url),
                headers=self.headers,
                params={'symbol': instrument_key}
            )
            data = res.json()
            if data.get('status') == 'success':
                return float(list(data['data'].values())[0]['last_price'])
            return None
        except Exception as e:
            print("[OPTIONS] LTP error: {}".format(e))
            return None

    def buy_option(self, symbol, spot_price, signal_type='BUY'):
        cfg = INDEX_CONFIG.get(symbol)
        if not cfg:
            print("[OPTIONS] No config for {}".format(symbol))
            return None

        option_type = 'CE' if signal_type == 'BUY' else 'PE'
        strike = self.get_atm_strike(spot_price, cfg['strike_gap'])
        if option_type == 'CE':
            strike += cfg['strike_gap']
        else:
            strike -= cfg['strike_gap']

        expiry = self.get_expiry(cfg['expiry_day'])
        instrument_key = self.get_instrument_key(
            cfg['name'], strike, option_type, expiry)

        print("[OPTIONS] {} {} Strike:{} Expiry:{}".format(
            cfg['name'], option_type, strike, expiry))

        premium = self.get_option_ltp(instrument_key)
        if not premium:
            print("[OPTIONS] No premium data — skipping")
            return None

        cost = premium * cfg['lot_size']
        print("[OPTIONS] Premium:Rs.{:.2f} | 1 lot cost:Rs.{:.2f}".format(
            premium, cost))

        if cost > self.options_capital:
            print("[OPTIONS] Too expensive Rs.{:.0f} > Rs.{:.0f}".format(
                cost, self.options_capital))
            return None

        res = requests.post(
            "{}/order/place".format(self.base_url),
            headers=self.headers,
            json={
                'quantity': cfg['lot_size'],
                'product': 'I',
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
            print("[OPTIONS] ✅ Order placed! ID:{}".format(
                data['data']['order_id']))
            return {
                'order_id': data['data']['order_id'],
                'symbol': symbol,
                'index_name': cfg['name'],
                'instrument_key': instrument_key,
                'option_type': option_type,
                'strike': strike,
                'entry_premium': premium,
                'highest_premium': premium,
                'lot_size': cfg['lot_size'],
                'capital_used': cost
            }
        else:
            print("[OPTIONS] Order failed: {}".format(data))
            return None

    def should_exit_option(self, position):
        current = self.get_option_ltp(position['instrument_key'])
        if not current:
            return False, None, 0
        if current > position['highest_premium']:
            position['highest_premium'] = current
        entry = position['entry_premium']
        peak = position['highest_premium']
        pnl_pct = (current - entry) / entry * 100
        trail_stop = peak * 0.70
        if current < trail_stop and peak > entry * 1.10:
            pnl = (current - entry) * position['lot_size']
            return True, 'TRAIL_STOP', pnl
        if current < entry * 0.60:
            pnl = (current - entry) * position['lot_size']
            return True, 'HARD_STOP', pnl
        print("[OPTIONS] Holding {} | Premium:Rs.{:.2f} | P&L:{:.1f}%".format(
            position['index_name'] + position['option_type'],
            current, pnl_pct))
        return False, None, 0

    def sell_option(self, position):
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
                print("[OPTIONS] ✅ Sold!")
                return True
            return False
        except Exception as e:
            print("[OPTIONS] Sell error: {}".format(e))
            return False
