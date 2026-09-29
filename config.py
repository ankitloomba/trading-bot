SYMBOLS = [
    "^NSEBANK",
    "^NSEI",
    "^CNXIT",
    "RELIANCE.NS",
    "HDFCBANK.NS",
    "INFY.NS",
    "TCS.NS",
    "ICICIBANK.NS",
    "SBIN.NS",
]

# Options - which indices to trade options on
OPTIONS_SYMBOLS = ["^NSEBANK", "^NSEI", "^CNXIT"]

# Upstox instrument keys — maps Yahoo-style tickers to Upstox API keys
INSTRUMENT_KEYS = {
    "^NSEBANK":    "NSE_INDEX|Nifty Bank",
    "^NSEI":       "NSE_INDEX|Nifty 50",
    "^CNXIT":      "NSE_INDEX|Nifty IT",
    "RELIANCE.NS": "NSE_EQ|INE002A01018",
    "HDFCBANK.NS": "NSE_EQ|INE040A01034",
    "INFY.NS":     "NSE_EQ|INE009A01021",
    "TCS.NS":      "NSE_EQ|INE467B01029",
    "ICICIBANK.NS":"NSE_EQ|INE090A01021",
    "SBIN.NS":     "NSE_EQ|INE062A01020",
}

STARTING_CAPITAL = 5000
MAX_POSITIONS = 3
BUFFER_CASH = 500
OPTIONS_CAPITAL = 3000   # Per-trade options budget (up from 2000)
OPTIONS_STOP_PCT = 0.40  # Hard stop: exit if premium down 40%
OPTIONS_TRAIL_PCT = 0.30 # Trail stop: exit if 30% below peak
OPTIONS_PROFIT_PCT = 2.0 # Profit target: exit if premium doubles (100% gain)
OPTIONS_MAX_POSITIONS = 2  # Allow 2 concurrent options positions
OPTIONS_ENABLED = True

BREAKOUT_PERIODS = 15
RSI_OVERBOUGHT = 65
RSI_OVERSOLD = 40
MIN_SIGNAL_SCORE = 5

PROFIT_TARGET = 0.01
STOP_LOSS = 0.005
TRAIL_PCT = 0.003
MAX_LOSS_PER_DAY = 500

MARKET_OPEN = "09:15"
MARKET_CLOSE = "15:30"
TRADING_END = "14:30"

PAPER_TRADE = False
BROKER = "UPSTOX"
AB_TEST_ENABLED = True

BOT_NAME = "Intra Gini"
BOT_EMOJI = "🔥"
