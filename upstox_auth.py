import os
import requests

class UpstoxAuth:
    """
    Handles Upstox OAuth2 authentication flow.
    
    Steps:
    1. Get auth URL
    2. User opens URL in browser and logs in
    3. Upstox redirects to redirect_uri with ?code=XXX
    4. Use code to get access token
    5. Store token in Railway env variable UPSTOX_ACCESS_TOKEN
    """

    def __init__(self):
        self.client_id = os.environ.get('UPSTOX_CLIENT_ID')
        self.client_secret = os.environ.get('UPSTOX_CLIENT_SECRET')
        self.redirect_uri = os.environ.get('UPSTOX_REDIRECT_URI')
        self.base_url = "https://api.upstox.com/v2"

    def get_auth_url(self):
        url = (
            "https://api.upstox.com/v2/login/authorization/dialog"
            "?response_type=code"
            "&client_id={}".format(self.client_id) +
            "&redirect_uri={}".format(self.redirect_uri)
        )
        print("\nOpen this URL in your browser to login:")
        print(url)
        return url

    def exchange_code(self, auth_code):
        print("Exchanging auth code for access token...")
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
                token = data['access_token']
                print("\nAccess token obtained!")
                print("Add this to Railway variables as UPSTOX_ACCESS_TOKEN:")
                print(token)
                return token
            print("Failed: {}".format(data))
            return None
        except Exception as e:
            print("Error: {}".format(e))
            return None

    def refresh_token_daily(self):
        """
        Upstox tokens expire daily.
        Run this before market open (9am IST) to get fresh token.
        """
        auth_code = os.environ.get('UPSTOX_AUTH_CODE')
        if not auth_code:
            print("No auth code found in UPSTOX_AUTH_CODE env variable")
            self.get_auth_url()
            return None
        return self.exchange_code(auth_code)

if __name__ == '__main__':
    auth = UpstoxAuth()
    auth.get_auth_url()
    code = input("\nPaste the code from redirect URL: ").strip()
    token = auth.exchange_code(code)
    if token:
        print("\nCopy this token to Railway → Variables → UPSTOX_ACCESS_TOKEN")
