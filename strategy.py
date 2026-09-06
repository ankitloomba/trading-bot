import pandas as pd
import numpy as np
import ta
from config import *

class BreakoutStrategy:
    def __init__(self):
        self.trades = []

    def calculate_rsi(self, df, period=14):
        return ta.momentum.rsi(df['Close'], length=period)

    def calculate_volume_ratio(self, df, period=20):
        return df['Volume'] / df['Volume'].rolling(window=period).mean()

    def get_buy_signal(self, df):
        if len(df) < BREAKOUT_PERIODS:
            return False, None
        current_row = df.iloc[-1]
        prev_high = df['High'].iloc[:-1].tail(BREAKOUT_PERIODS).max()
        price_breakout = current_row['Close'] > prev_high
        rsi = self.calculate_rsi(df)
        rsi_valid = rsi.iloc[-1] < RSI_OVERBOUGHT
        vol_ratio = self.calculate_volume_ratio(df)
        volume_valid = vol_ratio.iloc[-1] > MIN_VOLUME_RATIO
        if price_breakout and rsi_valid and volume_valid:
            return True, {
                'type': 'BUY',
                'price': current_row['Close'],
                'rsi': rsi.iloc[-1],
                'volume_ratio': vol_ratio.iloc[-1],
                'time': current_row.name
            }
        return False, None

    def get_sell_signal(self, entry_price, current_price, entry_high):
        profit_pct = (current_price - entry_price) / entry_price
        if profit_pct >= PROFIT_TARGET:
            return True, {
                'type': 'SELL',
                'reason': 'PROFIT_TARGET (+{:.2f}%)'.format(profit_pct * 100),
                'exit_price': current_price,
                'pnl': current_price - entry_price
            }
        if profit_pct <= -STOP_LOSS:
            return True, {
                'type': 'SELL',
                'reason': 'STOP_LOSS ({:.2f}%)'.format(profit_pct * 100),
                'exit_price': current_price,
                'pnl': current_price - entry_price
            }
        return False, None

    def backtest(self, df):
        trades = []
        position = None
        entry_price = None
        entry_time = None
        entry_high = None
        for i in range(1, len(df)):
            current_df = df.iloc[:i + 1].copy()
            current_row = df.iloc[i]
            if position is None:
                buy, signal = self.get_buy_signal(current_df)
                if buy:
                    position = 'LONG'
                    entry_price = current_row['Close']
                    entry_time = current_row.name
                    entry_high = current_row['High']
            elif position == 'LONG':
                sell, signal = self.get_sell_signal(entry_price, current_row['Close'], entry_high)
                if sell:
                    pnl = signal['exit_price'] - entry_price
                    pnl_pct = (pnl / entry_price) * 100
                    trades.append({
                        'entry_time': entry_time,
                        'entry_price': entry_price,
                        'exit_time': current_row.name,
                        'exit_price': signal['exit_price'],
                        'pnl': pnl,
                        'pnl_pct': pnl_pct,
                        'reason': signal['reason']
                    })
                    position = None
                    entry_price = None
        return trades
