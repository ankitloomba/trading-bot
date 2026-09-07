import os
import pyotp
import requests
import json
from datetime import datetime

class AngelOneBroker:
    def __init__(self):
        self.api_key = os.environ.get('ANGEL_API_KEY')
        self.client_id = os.environ.get('ANGEL_CLIENT_ID')
        self.mpin = os.environ.get('ANGEL_MPIN')
        self.totp_secret = os.environ.get('ANGEL_TOTP_SECRET')
        self.auth_token = None
        self.base_url = "https://apiconnect.angelone.in"

    def generate_totp(self):
        totp = pyotp.TOTP(self.totp_secret)
        return totp.now()

    def login(self):
        print("Logging into Angel One...")
        totp = self.generate_totp()
        headers = {
            'Content-Type': 'application/json',
            'Accept': 'application/json',
            'X-UserType': 'USER',
            'X-SourceID': 'WEB',
            'X-ClientLocalIP': '127.0.0.1',
            'X-ClientPublicIP': '106.193.147.98',
            'X-MACAddress': 'fe80::216e:6507:4b90:3719',
            'X-PrivateKey': self.api_key
        }
        payload = {
            "clientcode": self.client_id,
            "password": self.mpin,
            "totp": totp
        }
        try:
            response = requests.post(
                f"{self.base_url}/rest/auth/angelbroking/user/v1/loginByPassword",
                headers=headers,
                json=payload
            )
            data = response.json()
            if data.get('status') and data.get('data'):
                self.auth_token = data['data']['jwtToken']
                print("Login successful!")
                return True
            else:
                print("Login failed: {}".format(data.get('message', 'Unknown error')))
                return False
        except Exception as e:
            print("Login error: {}".format(e))
            return False

    def get_ltp(self, symbol="NIFTY BANK", token="10666", exchange="NSE"):
        if not self.auth_token:
            self.login()
        headers = {
            'Authorization': f'Bearer {self.auth_token}',
            'Content-Type': 'application/json',
            'Accept': 'application/json',
            'X-UserType': 'USER',
            'X-SourceID': 'WEB',
            'X-ClientLocalIP': '127.0.0.1',
            'X-ClientPublicIP': '106.193.147.98',
            'X-MACAddress': 'fe80::216e:6507:4b90:3719',
            'X-PrivateKey': self.api_key
        }
        payload = {
            "mode": "LTP",
            "exchangeTokens": {exchange: [token]}
        }
        try:
            response = requests.post(
                f"{self.base_url}/rest/secure/angelbroking/market/v1/quote/",
                headers=headers,
                json=payload
            )
            data = response.json()
            if data.get('status') and data.get('data'):
                ltp = data['data']['fetched'][0]['ltp']
                print("Bank Nifty LTP: Rs.{}".format(ltp))
                return float(ltp)
            else:
                print("LTP fetch failed: {}".format(data))
                return None
        except Exception as e:
            print("LTP error: {}".format(e))
            return None

if __name__ == '__main__':
    broker = AngelOneBroker()
    if broker.login():
        broker.get_ltp()
