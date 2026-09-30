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
    # Full Nifty 50 universe
    "RELIANCE":   "NSE_EQ|INE002A01018",
    "HDFCBANK":   "NSE_EQ|INE040A01034",
    "ICICIBANK":  "NSE_EQ|INE090A01021",
    "INFY":       "NSE_EQ|INE009A01021",
    "TCS":        "NSE_EQ|INE467B01029",
    "BHARTIARTL": "NSE_EQ|INE397D01024",
    "SBIN":       "NSE_EQ|INE062A01020",
    "KOTAKBANK":  "NSE_EQ|INE237A01028",
    "WIPRO":      "NSE_EQ|INE075A01022",
    "AXISBANK":   "NSE_EQ|INE238A01034",
    "LT":         "NSE_EQ|INE018A01030",
    "HCLTECH":    "NSE_EQ|INE860A01027",
    "BAJFINANCE": "NSE_EQ|INE296A01024",
    "ASIANPAINT": "NSE_EQ|INE021A01026",
    "MARUTI":     "NSE_EQ|INE585B01010",
    "NTPC":       "NSE_EQ|INE733E01010",
    "POWERGRID":  "NSE_EQ|INE752E01010",
    "ONGC":       "NSE_EQ|INE213A01029",
    "TITAN":      "NSE_EQ|INE280A01028",
    "SUNPHARMA":  "NSE_EQ|INE044A01036",
    "TECHM":      "NSE_EQ|INE669C01036",
    "TATAMOTORS": "NSE_EQ|INE155A01022",
    "TATASTEEL":  "NSE_EQ|INE081A01020",
    "HINDALCO":   "NSE_EQ|INE038A01020",
    "JSWSTEEL":   "NSE_EQ|INE019A01038",
    "ADANIENT":   "NSE_EQ|INE423A01024",
    "ADANIPORTS": "NSE_EQ|INE742F01042",
    "COALINDIA":  "NSE_EQ|INE522F01014",
    "BAJAJFINSV": "NSE_EQ|INE918I01026",
    "DRREDDY":    "NSE_EQ|INE089A01023",
    "CIPLA":      "NSE_EQ|INE059A01026",
    "DIVISLAB":   "NSE_EQ|INE361B01024",
    "EICHERMOT":  "NSE_EQ|INE066A01021",
    "HEROMOTOCO": "NSE_EQ|INE158A01026",
    "BPCL":       "NSE_EQ|INE029A01011",
    "GRASIM":     "NSE_EQ|INE047A01021",
    "INDUSINDBK": "NSE_EQ|INE095A01012",
    "BRITANNIA":  "NSE_EQ|INE216A01030",
    "APOLLOHOSP": "NSE_EQ|INE437A01024",
    "TATACONSUM": "NSE_EQ|INE192A01025",
    "BAJAJ-AUTO": "NSE_EQ|INE917I01010",
    "ULTRACEMCO": "NSE_EQ|INE481G01011",
    "NESTLEIND":  "NSE_EQ|INE239A01016",
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
                params={'instrument_key': instrument_key}  # Upstox v2 uses instrument_key, not symbol
            )
            data = res.json()
            if data.get('status') == 'success':
                return float(list(data['data'].values())[0]['last_price'])
            print(f"[BROKER] LTP API error: {data.get('errors', data)}")
            return None
        except Exception as e:
            print(f"[BROKER] LTP error: {e}")
            return None

    def place_order(self, instrument_key, quantity, transaction_type='BUY', order_type='MARKET', price=0):
        try:
            payload = {
                'quantity': quantity,
                'product': 'I',  # MIS — intraday (5x leverage, auto square-off 15:20)
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
