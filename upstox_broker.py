"""
Upstox Broker - Places real orders for stocks and options
"""
import requests
import os

BASE_URL = "https://api.upstox.com/v2"

# Index to stock mapping (when index signals, buy these stocks)
INDEX_TO_STOCK = {
    "^NSEBANK": "HDFCBANK",
    "^NSEI": "RELIANCE",
    "^CNXIT": "INFY",
}

# Stock instrument keys for NSE
STOCK_INSTRUMENTS = {
    "HDFCBANK": "NSE_EQ|INE040A01034",
    "RELIANCE": "NSE_EQ|INE002A01018",
    "INFY": "NSE_EQ|INE009A01021",
    "TCS": "NSE_EQ|INE467B01029",
    "ICICIBANK": "NSE_EQ|INE090A01021",
}

class UpstoxBroker:
    def __init__(self, access_token):
        self.token = access_token
        self.headers = {
            'Authorization': f'Bearer {access_token}',
            'Accept': 'application/json',
            'Content-Type': 'application/json'
        }

    def get_ltp(self, instrument_key):
        try:
            res = requests.get(
                f"{BASE_URL}/market-quote/ltp",
                headers=self.headers,
                params={'symbol': instrument_key}
            )
            data = res.json()
            if data.get('status') == 'success':
                return float(list(data['data'].values())[0]['last_price'])
            return None
        except Exception as e:
            print(f"[BROKER] LTP error: {e}")
            return None

    def place_order(self, instrument_key, quantity, transaction_type='BUY', order_type='MARKET', price=0):
        try:
            payload = {
                'quantity': quantity,
                'product': 'D',  # Delivery for stocks (CNC)
                'validity': 'DAY',
                'price': price,
                'tag': 'intragini',
                'instrument_token': instrument_key,
                'order_type': order_type,
                'transaction_type': transaction_type,
                'disclosed_quantity': 0,
                'trigger_price': 0,
                'is_amo': False
            }
            res = requests.post(
                f"{BASE_URL}/order/place",
                headers=self.headers,
                json=payload
            )
            data = res.json()
            if data.get('status') == 'success':
                order_id = data['data']['order_id']
                print(f"[BROKER] ✅ {transaction_type} order placed! ID:{order_id}")
                return order_id
            else:
                print(f"[BROKER] ❌ Order failed: {data}")
                return None
        except Exception as e:
            print(f"[BROKER] Order error: {e}")
            return None

    def buy_stock(self, symbol, capital):
        """Buy stock with given capital"""
        # Map index symbol to stock
        stock = INDEX_TO_STOCK.get(symbol, symbol.replace('.NS','').replace('^',''))
        instrument_key = STOCK_INSTRUMENTS.get(stock)
        if not instrument_key:
            print(f"[BROKER] No instrument key for {stock}")
            return None

        ltp = self.get_ltp(instrument_key)
        if not ltp:
            print(f"[BROKER] Could not get LTP for {stock}")
            return None

        quantity = int(capital / ltp)
        if quantity < 1:
            print(f"[BROKER] Not enough capital for {stock} at Rs.{ltp:.2f}")
            return None

        actual_cost = quantity * ltp
        print(f"[BROKER] Buying {stock}: {quantity} shares @ Rs.{ltp:.2f} = Rs.{actual_cost:.2f}")
        order_id = self.place_order(instrument_key, quantity, 'BUY')
        if order_id:
            return {
                'order_id': order_id,
                'stock': stock,
                'instrument_key': instrument_key,
                'quantity': quantity,
                'entry_price': ltp,
                'capital': actual_cost
            }
        return None

    def sell_stock(self, position):
        """Sell stock position"""
        print(f"[BROKER] Selling {position['stock']}: {position['quantity']} shares")
        return self.place_order(
            position['instrument_key'],
            position['quantity'],
            'SELL'
        )

    def get_funds(self):
        """Get available funds"""
        try:
            res = requests.get(f"{BASE_URL}/user/get-funds-and-margin", headers=self.headers)
            data = res.json()
            if data.get('status') == 'success':
                equity = data['data'].get('equity', {})
                return float(equity.get('available_margin', 0))
            return None
        except Exception as e:
            print(f"[BROKER] Funds error: {e}")
            return None
