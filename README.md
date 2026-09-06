# Trading Bot

Intraday breakout momentum bot for Bank Nifty (NSE) on 5-min charts.

## Quick Start

```bash
pip install -r requirements.txt
python backtest_3day.py
```

## Paper Trade (3 Days)

```bash
python paper_trader.py
```

## Strategy

- BUY: Price breaks 20-candle high + volume spike + RSI < 70
- SELL: +1% profit OR -0.5% stop loss
- Max 2 positions, max Rs.500 daily loss

## Files

- config.py - Settings
- strategy.py - Trading logic
- backtest_3day.py - Run backtest
- paper_trader.py - Manual trade tracker

## Next Steps

1. Backtest (today)
2. Paper trade (3 days)
3. Angel One API (Week 2)
4. Deploy to Railway (Week 3)
5. Dashboard on Vercel (Week 4)
