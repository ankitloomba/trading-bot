import pandas as pd
import numpy as np
from config import *

class BreakoutStrategy:
    def __init__(self):
        self.trades = []

    def calculate_rsi(self, closes, period=14):
        delta = closes.diff()
        gain = delta.where(delta > 0, 0.0)
        loss = (-delta).where(delta < 0, 0.0)
        avg_gain = gain.rolling(window=period).mean()
        avg_loss = loss.rolling(window=period).mean()
        rs = avg_gain / avg_loss
        return 100 - (100 / (1 + rs))

    def backtest(self, df):
        closes = pd.Series(df['Close'].values.flatten(), index=df.index)
        highs = pd.Series(df['High'].values.flatten(), index=df.index)
        trades = []
        position = None
        entry_price = None
        entry_time = None
        for i in range(BREAKOUT_PERIODS + 1, len(closes)):
            current_close = float(closes.iloc[i])
            if position is None:
                prev_high = float(highs.iloc[i-BREAKOUT_PERIODS:i].max())
                price_breakout = current_close > prev_high
                rsi = self.calculate_rsi(closes.iloc[:i+1])
                rsi_val = float(rsi.iloc[-1]) if not pd.isna(rsi.iloc[-1]) else 50.0
                rsi_valid = RSI_OVERSOLD < rsi_val < RSI_OVERBOUGHT
                if price_breakout and rsi_valid:
                    position = 'LONG'
                    entry_price = current_close
                    entry_time = closes.index[i]
            elif position == 'LONG':
                profit_pct = (current_close - entry_price) / entry_price
                if profit_pct >= PROFIT_TARGET:
                    trades.append({'entry_time': str(entry_time), 'entry_price': round(entry_price, 2), 'exit_time': str(closes.index[i]), 'exit_price': round(current_close, 2), 'pnl': round(current_close - entry_price, 2), 'pnl_pct': round(profit_pct * 100, 4), 'reason': 'PROFIT +{:.2f}%'.format(profit_pct * 100)})
                    position = None
                elif profit_pct <= -STOP_LOSS:
                    trades.append({'entry_time': str(entry_time), 'entry_price': round(entry_price, 2), 'exit_time': str(closes.index[i]), 'exit_price': round(current_close, 2), 'pnl': round(current_close - entry_price, 2), 'pnl_pct': round(profit_pct * 100, 4), 'reason': 'STOPLOSS {:.2f}%'.format(profit_pct * 100)})
                    position = None
        return trades
