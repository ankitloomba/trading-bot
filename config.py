# Trading symbols - scanned simultaneously
SYMBOLS = [
    "^NSEBANK",      # Bank Nifty
    "^NSEI",         # Nifty 50
    "^CNXIT",        # Nifty IT
    "RELIANCE.NS",   # Reliance
    "HDFCBANK.NS",   # HDFC Bank
    "INFY.NS",       # Infosys
     # Tata Motors
]

# Capital allocation per symbol
# Total ₹5,000 split across max 3 simultaneous positions
STARTING_CAPITAL = 5000
MAX_POSITIONS = 3
BUFFER_CASH = 500

# Strategy params
BREAKOUT_PERIODS = 15
RSI_OVERBOUGHT = 65
RSI_OVERSOLD = 40
MIN_SIGNAL_SCORE = 7

# Exit params
PROFIT_TARGET = 0.01   # 1% (used for Variant B)
STOP_LOSS = 0.005      # 0.5% hard stop
TRAIL_PCT = 0.003      # 0.3% trailing stop

# Market hours
MARKET_OPEN = "09:15"
MARKET_CLOSE = "15:30"
TRADING_END = "14:30"

# Mode
PAPER_TRADE = False
BROKER = "UPSTOX"

# A/B testing
AB_TEST_ENABLED = True

# Logging
LOG_FILE = "trading_log.csv"
ENABLE_ALERTS = True

# Bot identity
BOT_NAME = "Intra Gini"
BOT_EMOJI = "🔥"
