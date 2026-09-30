SYMBOLS = [
    # ── Indices (options trading) ──────────────────────────
    "^NSEBANK",
    "^NSEI",
    "^CNXIT",
    # ── Nifty 50 stocks (equity + best signal wins) ────────
    "RELIANCE.NS",
    "HDFCBANK.NS",
    "ICICIBANK.NS",
    "INFY.NS",
    "TCS.NS",
    "BHARTIARTL.NS",
    "SBIN.NS",
    "KOTAKBANK.NS",
    "WIPRO.NS",
    "AXISBANK.NS",
    "LT.NS",
    "HCLTECH.NS",
    "BAJFINANCE.NS",
    "ASIANPAINT.NS",
    "MARUTI.NS",
    "NTPC.NS",
    "POWERGRID.NS",
    "ONGC.NS",
    "TITAN.NS",
    "SUNPHARMA.NS",
    "TECHM.NS",
    "TATAMOTORS.NS",
    "TATASTEEL.NS",
    "HINDALCO.NS",
    "JSWSTEEL.NS",
    "ADANIENT.NS",
    "ADANIPORTS.NS",
    "COALINDIA.NS",
    "BAJAJFINSV.NS",
    "DRREDDY.NS",
    "CIPLA.NS",
    "DIVISLAB.NS",
    "EICHERMOT.NS",
    "HEROMOTOCO.NS",
    "BPCL.NS",
    "GRASIM.NS",
    "INDUSINDBK.NS",
    "BRITANNIA.NS",
    "APOLLOHOSP.NS",
    "TATACONSUM.NS",
    "BAJAJ-AUTO.NS",
    "ULTRACEMCO.NS",
    "NESTLEIND.NS",
]

# Options - which indices to trade options on
OPTIONS_SYMBOLS = ["^NSEBANK", "^NSEI", "^CNXIT"]

# Upstox instrument keys — maps Yahoo-style tickers to Upstox API keys
INSTRUMENT_KEYS = {
    # Indices
    "^NSEBANK":       "NSE_INDEX|Nifty Bank",
    "^NSEI":          "NSE_INDEX|Nifty 50",
    "^CNXIT":         "NSE_INDEX|Nifty IT",
    # Nifty 50 equities (ISIN-based keys)
    "RELIANCE.NS":    "NSE_EQ|INE002A01018",
    "HDFCBANK.NS":    "NSE_EQ|INE040A01034",
    "ICICIBANK.NS":   "NSE_EQ|INE090A01021",
    "INFY.NS":        "NSE_EQ|INE009A01021",
    "TCS.NS":         "NSE_EQ|INE467B01029",
    "BHARTIARTL.NS":  "NSE_EQ|INE397D01024",
    "SBIN.NS":        "NSE_EQ|INE062A01020",
    "KOTAKBANK.NS":   "NSE_EQ|INE237A01028",
    "WIPRO.NS":       "NSE_EQ|INE075A01022",
    "AXISBANK.NS":    "NSE_EQ|INE238A01034",
    "LT.NS":          "NSE_EQ|INE018A01030",
    "HCLTECH.NS":     "NSE_EQ|INE860A01027",
    "BAJFINANCE.NS":  "NSE_EQ|INE296A01024",
    "ASIANPAINT.NS":  "NSE_EQ|INE021A01026",
    "MARUTI.NS":      "NSE_EQ|INE585B01010",
    "NTPC.NS":        "NSE_EQ|INE733E01010",
    "POWERGRID.NS":   "NSE_EQ|INE752E01010",
    "ONGC.NS":        "NSE_EQ|INE213A01029",
    "TITAN.NS":       "NSE_EQ|INE280A01028",
    "SUNPHARMA.NS":   "NSE_EQ|INE044A01036",
    "TECHM.NS":       "NSE_EQ|INE669C01036",
    "TATAMOTORS.NS":  "NSE_EQ|INE155A01022",
    "TATASTEEL.NS":   "NSE_EQ|INE081A01020",
    "HINDALCO.NS":    "NSE_EQ|INE038A01020",
    "JSWSTEEL.NS":    "NSE_EQ|INE019A01038",
    "ADANIENT.NS":    "NSE_EQ|INE423A01024",
    "ADANIPORTS.NS":  "NSE_EQ|INE742F01042",
    "COALINDIA.NS":   "NSE_EQ|INE522F01014",
    "BAJAJFINSV.NS":  "NSE_EQ|INE918I01026",
    "DRREDDY.NS":     "NSE_EQ|INE089A01023",
    "CIPLA.NS":       "NSE_EQ|INE059A01026",
    "DIVISLAB.NS":    "NSE_EQ|INE361B01024",
    "EICHERMOT.NS":   "NSE_EQ|INE066A01021",
    "HEROMOTOCO.NS":  "NSE_EQ|INE158A01026",
    "BPCL.NS":        "NSE_EQ|INE029A01011",
    "GRASIM.NS":      "NSE_EQ|INE047A01021",
    "INDUSINDBK.NS":  "NSE_EQ|INE095A01012",
    "BRITANNIA.NS":   "NSE_EQ|INE216A01030",
    "APOLLOHOSP.NS":  "NSE_EQ|INE437A01024",
    "TATACONSUM.NS":  "NSE_EQ|INE192A01025",
    "BAJAJ-AUTO.NS":  "NSE_EQ|INE917I01010",
    "ULTRACEMCO.NS":  "NSE_EQ|INE481G01011",
    "NESTLEIND.NS":   "NSE_EQ|INE239A01016",
}

STARTING_CAPITAL = 5000
MAX_POSITIONS = 3
BUFFER_CASH = 200
OPTIONS_CAPITAL = 1500   # Per-trade options budget — sized for ₹5k account
OPTIONS_STOP_PCT = 0.40  # Hard stop: exit if premium down 40%
OPTIONS_TRAIL_PCT = 0.30 # Trail stop: exit if 30% below peak
OPTIONS_PROFIT_PCT = 2.0 # Profit target: exit if premium doubles (100% gain)
OPTIONS_MAX_POSITIONS = 2  # Allow 2 concurrent options positions
OPTIONS_ENABLED = True

BREAKOUT_PERIODS = 10    # Shorter lookback = more breakout opportunities
RSI_OVERBOUGHT = 65
RSI_OVERSOLD = 40
MIN_SIGNAL_SCORE = 4     # Fire on good signals, not just perfect ones

PROFIT_TARGET = 0.01
STOP_LOSS = 0.005
TRAIL_PCT = 0.003
MAX_LOSS_PER_DAY = 500

MARKET_OPEN = "09:15"
MARKET_CLOSE = "15:30"
TRADING_END = "14:30"
SCAN_INTERVAL = 90  # seconds — wider universe needs more time per cycle

PAPER_TRADE = False
BROKER = "UPSTOX"
AB_TEST_ENABLED = True

BOT_NAME = "Intra Gini"
BOT_EMOJI = "🔥"
