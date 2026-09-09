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

    def signal_strength(self, closes, highs, lows, i):
        """Score signal 1-10. 7+ = take trade."""
        score = 0
        current = float(closes.iloc[i])
        prev_high = float(highs.iloc[i-BREAKOUT_PERIODS:i].max())
        rsi_series = self.calculate_rsi(closes.iloc[:i+1])
        rsi = float(rsi_series.iloc[-1]) if not pd.isna(rsi_series.iloc[-1]) else 50.0

        # 1. Breakout size (0-3 pts)
        breakout_pct = (current - prev_high) / prev_high * 100
        if breakout_pct > 0.3: score += 1
        if breakout_pct > 0.6: score += 1
        if breakout_pct > 1.0: score += 1

        # 2. RSI quality (0-2 pts)
        if 40 <= rsi <= 60: score += 2   # fresh momentum
        elif 35 <= rsi <= 65: score += 1  # acceptable

        # 3. Candle pattern - last 3 candles (0-2 pts)
        if i >= 3:
            last3 = closes.iloc[i-3:i+1]
            green_candles = sum(1 for j in range(len(last3)-1) if last3.iloc[j+1] > last3.iloc[j])
            score += min(2, green_candles)

        # 4. Time of day (0-2 pts)
        try:
            hour = closes.index[i].hour
            minute = closes.index[i].minute
            t = hour * 100 + minute
            if 930 <= t <= 1300: score += 2   # prime time
            elif 915 <= t <= 1430: score += 1  # acceptable
        except:
            score += 1

        # 5. Price above breakout level (0-1 pt)
        if current > prev_high * 1.002: score += 1

        return min(10, score), {
            'score': score,
            'breakout_pct': round(breakout_pct, 3),
            'rsi': round(rsi, 1),
            'prev_high': round(prev_high, 2),
            'current': round(current, 2)
        }

    def get_signal(self, df):
        """Returns signal with strength score."""
        closes = pd.Series(df['Close'].values.flatten(), index=df.index)
        highs = pd.Series(df['High'].values.flatten(), index=df.index)
        lows = pd.Series(df['Low'].values.flatten(), index=df.index)
        i = len(closes) - 1
        if i < BREAKOUT_PERIODS + 1:
            return None
        current = float(closes.iloc[i])
        prev_high = float(highs.iloc[i-BREAKOUT_PERIODS:i].max())
        if current <= prev_high:
            return None
        score, details = self.signal_strength(closes, highs, lows, i)
        if score >= 7:
            return {'score': score, 'price': current, 'details': details}
        return None

    def get_trailing_stop(self, entry_price, highest_price, trail_pct=0.003):
        """Trailing stop 0.3% below highest price reached."""
        return highest_price * (1 - trail_pct)

    def backtest(self, df):
        closes = pd.Series(df['Close'].values.flatten(), index=df.index)
        highs = pd.Series(df['High'].values.flatten(), index=df.index)
        lows = pd.Series(df['Low'].values.flatten(), index=df.index)
        trades = []
        position = None
        entry_price = None
        entry_time = None
        highest_price = None

        for i in range(BREAKOUT_PERIODS + 1, len(closes)):
            current = float(closes.iloc[i])
            if position is None:
                score, details = self.signal_strength(closes, highs, lows, i)
                if score >= 7:
                    position = 'LONG'
                    entry_price = current
                    entry_time = closes.index[i]
                    highest_price = current
            elif position == 'LONG':
                highest_price = max(highest_price, current)
                trail_stop = self.get_trailing_stop(entry_price, highest_price)
                hard_stop = entry_price * (1 - STOP_LOSS)
                exit_price = None
                reason = None
                if current < trail_stop and highest_price > entry_price * 1.005:
                    exit_price = current
                    reason = 'TRAIL_STOP'
                elif current < hard_stop:
                    exit_price = current
                    reason = 'HARD_STOP'
                if exit_price:
                    pnl = exit_price - entry_price
                    trades.append({
                        'entry_time': str(entry_time),
                        'entry_price': round(entry_price, 2),
                        'exit_time': str(closes.index[i]),
                        'exit_price': round(exit_price, 2),
                        'highest_price': round(highest_price, 2),
                        'pnl': round(pnl, 2),
                        'pnl_pct': round((pnl/entry_price)*100, 4),
                        'reason': reason
                    })
                    position = None
                    entry_price = None
                    highest_price = None
        return trades
