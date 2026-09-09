import os
import requests

class UpstoxBroker:
    def __init__(self):
        self.client_id = os.environ.get('UPSTOX_CLIENT_ID')
        self.client_secret = os.environ.get('UPSTOX_CLIENT_SECRET')
        self.redirect_uri = os.environ.get('UPSTOX_REDIRECT_URI')
        self.access_token = os.environ.get('UPSTOX_ACCESS_TOKEN')
        self.base_url = "https://api.upstox.com/v2"
        print("Upstox broker initialized")

    def get_auth_url(self):
        return (
            "https://api.upstox.com/v2/login/authorization/dialog"
            "?response_type=code"
            "&client_id={}".format(self.client_id) +
            "&redirect_uri={}".format(self.redirect_uri)
        )

    def login(self, auth_code):
        print("Logging into Upstox...")
        try:
            response = requests.post(
                "{}/login/authorization/token".format(self.base_url),
                headers={'Content-Type': 'application/x-www-form-urlencoded'},
                data={
                    'code': auth_code,
                    'client_id': self.client_id,
                    'client_secret': self.client_secret,
                    'redirect_uri': self.redirect_uri,
                    'grant_type': 'authorization_code'
                }
            )
            data = response.json()
            if data.get('access_token'):
                self.access_token = data['access_token']
                print("Upstox login successful!")
                return True
            print("Login failed: {}".format(data))
            return False
        except Exception as e:
            print("Login error: {}".format(e))
            return False

    def get_ltp(self, symbol="NSE_INDEX|Nifty Bank"):
        if not self.access_token:
            print("Not logged in!")
            return None
        try:
            response = requests.get(
                "{}/market-quote/ltp".format(self.base_url),
                headers={
                    'Authorization': 'Bearer {}'.format(self.access_token),
                    'Accept': 'application/json'
                },
                params={'symbol': symbol}
            )
            data = response.json()
            if data.get('status') == 'success':
                ltp = list(data['data'].values())[0]['last_price']
                print("Bank Nifty LTP: Rs.{}".format(ltp))
                return float(ltp)
            print("LTP failed: {}".format(data))
            return None
        except Exception as e:
            print("LTP error: {}".format(e))
            return None

    def get_funds(self):
        if not self.access_token:
            return 0
        try:
            response = requests.get(
                "{}/user/get-funds-and-margin".format(self.base_url),
                headers={
                    'Authorization': 'Bearer {}'.format(self.access_token),
                    'Accept': 'application/json'
                },
                params={'segment': 'EQ'}
            )
            data = response.json()
            if data.get('status') == 'success':
                funds = data['data']['equity']['available_margin']
                print("Available funds: Rs.{}".format(funds))
                return float(funds)
            return 0
        except Exception as e:
            print("Funds error: {}".format(e))
            return 0

    def place_order(self, symbol, qty, side, price=0):
        if not self.access_token:
            print("Not logged in!")
            return None
        try:
            response = requests.post(
                "{}/order/place".format(self.base_url),
                headers={
                    'Authorization': 'Bearer {}'.format(self.access_token),
                    'Content-Type': 'application/json',
                    'Accept': 'application/json'
                },
                json={
                    'quantity': qty,
                    'product': 'I',
                    'validity': 'DAY',
                    'price': price,
                    'tag': 'trading-bot',
                    'instrument_token': symbol,
                    'order_type': 'MARKET',
                    'transaction_type': side,
                    'disclosed_quantity': 0,
                    'trigger_price': 0,
                    'is_amo': False
                }
            )
            data = response.json()
            if data.get('status') == 'success':
                print("Order placed: {} {} {}".format(side, qty, symbol))
                return data['data']['order_id']
            print("Order failed: {}".format(data))
            return None
        except Exception as e:
            print("Order error: {}".format(e))
            return None

    def get_positions(self):
        if not self.access_token:
            return []
        try:
            response = requests.get(
                "{}/portfolio/short-term-positions".format(self.base_url),
                headers={
                    'Authorization': 'Bearer {}'.format(self.access_token),
                    'Accept': 'application/json'
                }
            )
            data = response.json()
            if data.get('status') == 'success':
                return data.get('data', [])
            return []
        except Exception as e:
            print("Positions error: {}".format(e))
            return []
