# Trading symbols - stocks scanned simultaneously
SYMBOLS = [
    "^NSEBANK",      # Bank Nifty
    "^NSEI",         # Nifty 50
    "^CNXIT",        # Nifty IT
    "RELIANCE.NS",   # Reliance
    "HDFCBANK.NS",   # HDFC Bank
    "INFY.NS",       # Infosys
]

# Capital allocation
STARTING_CAPITAL = 5000
MAX_POSITIONS = 3
BUFFER_CASH = 500

# Options settings
OPTIONS_ENABLED = True
OPTIONS_CAPITAL = 2000        # Capital for 1 Bank Nifty options lot
OPTIONS_STOP_PCT = 0.40       # Exit if premium drops 40%
OPTIONS_TRAIL_PCT = 0.30      # Trail 30% below peak premium

# Strategy params
BREAKOUT_PERIODS = 15
RSI_OVERBOUGHT = 65
RSI_OVERSOLD = 40
MIN_SIGNAL_SCORE = 6          # Lowered from 7 to 6

# Exit params
PROFIT_TARGET = 0.01
STOP_LOSS = 0.005
TRAIL_PCT = 0.003
MAX_LOSS_PER_DAY = 500

# Market hours
MARKET_OPEN = "09:15"
MARKET_CLOSE = "15:30"
TRADING_END = "14:30"

# Mode
PAPER_TRADE = False
BROKER = "UPSTOX"

# A/B testing
AB_TEST_ENABLED = True

# Bot identity
BOT_NAME = "Intra Gini"
BOT_EMOJI = "🔥"
