"""
Intra Gini 🔥 — Breakout Strategy
With debug logging to show scores per symbol
"""
import pandas as pd
import numpy as np

class BreakoutStrategy:
    def __init__(self):
        self.breakout_periods = 15
        self.rsi_period = 14

    def calculate_rsi(self, series, period=14):
        delta = series.diff()
        gain = delta.where(delta > 0, 0).rolling(period).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(period).mean()
        rs = gain / loss
        return 100 - (100 / (1 + rs))

    def get_signal(self, df, symbol='', debug=True):
        try:
            close = df['Close']
            high = df['High']
            volume = df['Volume']

            score = 0
            details = []

            # 1. Breakout above 15-candle high (0-3 pts)
            recent_high = high.iloc[-self.breakout_periods-1:-1].max()
            current_price = float(close.iloc[-1])
            breakout_pct = (current_price - recent_high) / recent_high * 100

            if breakout_pct > 0.5:
                score += 3
                details.append("Breakout +{:.2f}% ✅✅✅".format(breakout_pct))
            elif breakout_pct > 0.2:
                score += 2
                details.append("Breakout +{:.2f}% ✅✅".format(breakout_pct))
            elif breakout_pct > 0:
                score += 1
                details.append("Breakout +{:.2f}% ✅".format(breakout_pct))
            else:
                details.append("No breakout {:.2f}% ❌".format(breakout_pct))

            # 2. RSI in range (0-2 pts)
            rsi = self.calculate_rsi(close)
            rsi_val = float(rsi.iloc[-1])
            if 45 <= rsi_val <= 65:
                score += 2
                details.append("RSI {:.1f} ✅✅".format(rsi_val))
            elif 40 <= rsi_val < 45 or 65 < rsi_val <= 70:
                score += 1
                details.append("RSI {:.1f} ✅".format(rsi_val))
            else:
                details.append("RSI {:.1f} ❌".format(rsi_val))

            # 3. Last 3 candles green (0-2 pts)
            last3 = close.iloc[-3:].values
            green = sum(1 for i in range(1, len(last3)) if last3[i] > last3[i-1])
            if green >= 2:
                score += 2
                details.append("{}  green candles ✅✅".format(green))
            elif green == 1:
                score += 1
                details.append("1 green candle ✅")
            else:
                details.append("No green candles ❌")

            # 4. Trading time bonus (0-2 pts)
            from datetime import datetime
            import pytz
            IST = pytz.timezone('Asia/Kolkata')
            now = datetime.now(IST)
            if 9 <= now.hour < 13:
                score += 2
                details.append("Prime time ✅✅")
            elif 13 <= now.hour < 14:
                score += 1
                details.append("Good time ✅")
            else:
                details.append("Late session ❌")

            # 5. Volume spike (0-1 pt)
            avg_vol = volume.rolling(20).mean().iloc[-1]
            vol_ratio = float(volume.iloc[-1]) / float(avg_vol) if avg_vol > 0 else 0
            if vol_ratio >= 1.5:
                score += 1
                details.append("Volume {:.1f}x ✅".format(vol_ratio))
            else:
                details.append("Volume {:.1f}x ❌".format(vol_ratio))

            # Debug log
            if debug and symbol:
                print("[SCAN] {} | Score:{}/10 | Price:{:.2f}".format(
                    symbol.replace('.NS','').replace('^',''),
                    score, current_price))
                for d in details:
                    print("       {}".format(d))

            if score >= 5:
                return {
                    'score': score,
                    'price': current_price,
                    'type': 'BUY',
                    'reasons': details
                }
            return None

        except Exception as e:
            print("[SCAN] {} error: {}".format(symbol, e))
            return None
