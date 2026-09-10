"""
Bank Nifty Options Trader
- Buys CE when bullish signal fires
- Buys PE when bearish signal fires  
- Exits when premium drops 30% from peak (trailing)
- Hard stop: 40% loss of premium
- Capital: ~₹2,500 per options trade
"""
import os
import requests
from datetime import datetime, timedelta
import pytz

IST = pytz.timezone('Asia/Kolkata')

class BankNiftyOptionsTrader:
    def __init__(self, broker_token):
        self.token = broker_token
        self.base_url = "https://api.upstox.com/v2"
        self.lot_size = 15  # Bank Nifty lot size
        self.options_capital = 2500  # Capital for options
        self.headers = {
            'Authorization': 'Bearer {}'.format(self.token),
            'Accept': 'application/json',
            'Content-Type': 'application/json'
        }

    def get_expiry(self):
        """Get nearest weekly expiry (every Wednesday for Bank Nifty)"""
        today = datetime.now(IST)
        days_ahead = 2 - today.weekday()  # Wednesday = 2
        if days_ahead <= 0:
            days_ahead += 7
        expiry = today + timedelta(days=days_ahead)
        return expiry.strftime('%y%b%d').upper()  # e.g. 26SEP10

    def get_atm_strike(self, spot_price):
        """Round to nearest 100 for Bank Nifty"""
        return round(spot_price / 100) * 100

    def get_instrument_key(self, strike, option_type, expiry):
        """
        Format: NSE_FO|BANKNIFTY26SEP56000CE
        """
        return "NSE_FO|BANKNIFTY{}{}{}".format(
            expiry, strike, option_type
        )

    def get_option_ltp(self, instrument_key):
        """Get Last Traded Price of option"""
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

    def buy_option(self, spot_price, signal_type='BUY'):
        """
        Buy CE for bullish signal, PE for bearish
        """
        try:
            option_type = 'CE' if signal_type == 'BUY' else 'PE'
            strike = self.get_atm_strike(spot_price)
            # Slightly OTM for better risk/reward
            if option_type == 'CE':
                strike += 100  # 1 strike OTM
            else:
                strike -= 100

            expiry = self.get_expiry()
            instrument_key = self.get_instrument_key(strike, option_type, expiry)

            print("[OPTIONS] Buying {} {} Strike:{} Expiry:{}".format(
                option_type, instrument_key, strike, expiry))

            # Get current premium
            premium = self.get_option_ltp(instrument_key)
            if not premium:
                print("[OPTIONS] Could not get premium — skipping")
                return None

            # Calculate quantity (1 lot = 15)
            cost = premium * self.lot_size
            print("[OPTIONS] Premium: Rs.{:.2f} | 1 lot cost: Rs.{:.2f}".format(
                premium, cost))

            if cost > self.options_capital:
                print("[OPTIONS] Too expensive (Rs.{:.0f} > Rs.{:.0f}) — skipping".format(
                    cost, self.options_capital))
                return None

            # Place order
            res = requests.post(
                "{}/order/place".format(self.base_url),
                headers=self.headers,
                json={
                    'quantity': self.lot_size,
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
                order_id = data['data']['order_id']
                print("[OPTIONS] Order placed! ID: {} | Premium: Rs.{}".format(
                    order_id, premium))
                return {
                    'order_id': order_id,
                    'instrument_key': instrument_key,
                    'option_type': option_type,
                    'strike': strike,
                    'entry_premium': premium,
                    'highest_premium': premium,
                    'lot_size': self.lot_size,
                    'capital_used': cost
                }
            else:
                print("[OPTIONS] Order failed: {}".format(data))
                return None

        except Exception as e:
            print("[OPTIONS] Buy error: {}".format(e))
            return None

    def should_exit_option(self, position):
        """Check if option should be exited"""
        current_premium = self.get_option_ltp(position['instrument_key'])
        if not current_premium:
            return False, None, 0

        # Update peak
        if current_premium > position['highest_premium']:
            position['highest_premium'] = current_premium

        entry = position['entry_premium']
        peak = position['highest_premium']
        pnl_pct = (current_premium - entry) / entry * 100

        # Trailing stop: exit if premium drops 30% from peak
        trail_stop = peak * 0.70
        if current_premium < trail_stop and peak > entry * 1.10:
            pnl = (current_premium - entry) * position['lot_size']
            return True, 'TRAIL_STOP', pnl

        # Hard stop: exit if premium drops 40% from entry
        if current_premium < entry * 0.60:
            pnl = (current_premium - entry) * position['lot_size']
            return True, 'HARD_STOP', pnl

        print("[OPTIONS] Holding {} | Premium: Rs.{:.2f} | P&L: {:.1f}%".format(
            position['instrument_key'], current_premium, pnl_pct))
        return False, None, 0

    def sell_option(self, position):
        """Sell/square off the option position"""
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
                print("[OPTIONS] Sold! Order: {}".format(data['data']['order_id']))
                return True
            return False
        except Exception as e:
            print("[OPTIONS] Sell error: {}".format(e))
            return False
