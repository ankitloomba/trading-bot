"""
Intra Gini 🔥 — Breakout + Breakdown Strategy
Returns BUY signal on bullish breakout, SELL signal on bearish breakdown.
"""
import pandas as pd
import numpy as np


class BreakoutStrategy:
    def __init__(self):
        self.breakout_periods = 10   # Shorter lookback = more breakout opportunities
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
            low = df['Low']
            volume = df['Volume']

            current_price = float(close.iloc[-1])
            rsi = self.calculate_rsi(close)
            rsi_val = float(rsi.iloc[-1])

            # ──────────────────── BULLISH CHECK ────────────────────────
            recent_high = high.iloc[-self.breakout_periods-1:-1].max()
            breakout_pct = (current_price - recent_high) / recent_high * 100

            bull_score = 0
            bull_details = []

            # 1. Breakout above 10-candle high (0-3 pts)
            if breakout_pct > 0.3:
                bull_score += 3
                bull_details.append("Breakout +{:.2f}% ✅✅✅".format(breakout_pct))
            elif breakout_pct > 0.1:
                bull_score += 2
                bull_details.append("Breakout +{:.2f}% ✅✅".format(breakout_pct))
            elif breakout_pct > 0:
                bull_score += 1
                bull_details.append("Breakout +{:.2f}% ✅".format(breakout_pct))
            else:
                bull_details.append("No breakout {:.2f}% ❌".format(breakout_pct))

            # 2. RSI in bullish range (0-2 pts)
            if 45 <= rsi_val <= 65:
                bull_score += 2
                bull_details.append("RSI {:.1f} ✅✅".format(rsi_val))
            elif 40 <= rsi_val < 45 or 65 < rsi_val <= 70:
                bull_score += 1
                bull_details.append("RSI {:.1f} ✅".format(rsi_val))
            else:
                bull_details.append("RSI {:.1f} ❌".format(rsi_val))

            # 3. Last 3 candles green (0-2 pts)
            last3 = close.iloc[-3:].values
            green = sum(1 for i in range(1, len(last3)) if last3[i] > last3[i-1])
            if green >= 2:
                bull_score += 2
                bull_details.append("{} green candles ✅✅".format(green))
            elif green == 1:
                bull_score += 1
                bull_details.append("1 green candle ✅")
            else:
                bull_details.append("No green candles ❌")

            # 4. Trading time bonus (0-2 pts)
            from datetime import datetime
            import pytz
            IST = pytz.timezone('Asia/Kolkata')
            now = datetime.now(IST)
            if 9 <= now.hour < 13:
                bull_score += 2
                bull_details.append("Prime time ✅✅")
                bear_time_bonus = 2
            elif 13 <= now.hour < 14:
                bull_score += 1
                bull_details.append("Good time ✅")
                bear_time_bonus = 1
            else:
                bull_details.append("Late session ❌")
                bear_time_bonus = 0

            # 5. Volume spike (0-1 pt)
            avg_vol = volume.rolling(20).mean().iloc[-1]
            vol_ratio = float(volume.iloc[-1]) / float(avg_vol) if avg_vol > 0 else 0
            if vol_ratio >= 1.2:
                bull_score += 1
                bull_details.append("Volume {:.1f}x ✅".format(vol_ratio))
            else:
                bull_details.append("Volume {:.1f}x ❌".format(vol_ratio))

            # ──────────────────── BEARISH CHECK ────────────────────────
            recent_low = low.iloc[-self.breakout_periods-1:-1].min()
            breakdown_pct = (recent_low - current_price) / recent_low * 100  # positive = broke down

            bear_score = 0
            bear_details = []

            # 1. Breakdown below 10-candle low (0-3 pts)
            if breakdown_pct > 0.3:
                bear_score += 3
                bear_details.append("Breakdown -{:.2f}% ✅✅✅".format(breakdown_pct))
            elif breakdown_pct > 0.1:
                bear_score += 2
                bear_details.append("Breakdown -{:.2f}% ✅✅".format(breakdown_pct))
            elif breakdown_pct > 0:
                bear_score += 1
                bear_details.append("Breakdown -{:.2f}% ✅".format(breakdown_pct))
            else:
                bear_details.append("No breakdown {:.2f}% ❌".format(-breakdown_pct))

            # 2. RSI in bearish range (0-2 pts)
            if 35 <= rsi_val <= 55:
                bear_score += 2
                bear_details.append("RSI {:.1f} bearish ✅✅".format(rsi_val))
            elif 30 <= rsi_val < 35 or 55 < rsi_val <= 60:
                bear_score += 1
                bear_details.append("RSI {:.1f} bearish ✅".format(rsi_val))
            else:
                bear_details.append("RSI {:.1f} not bearish ❌".format(rsi_val))

            # 3. Last 3 candles red (0-2 pts)
            red = sum(1 for i in range(1, len(last3)) if last3[i] < last3[i-1])
            if red >= 2:
                bear_score += 2
                bear_details.append("{} red candles ✅✅".format(red))
            elif red == 1:
                bear_score += 1
                bear_details.append("1 red candle ✅")
            else:
                bear_details.append("No red candles ❌")

            # 4. Time bonus (same as bull)
            bear_score += bear_time_bonus
            if bear_time_bonus == 2:
                bear_details.append("Prime time ✅✅")
            elif bear_time_bonus == 1:
                bear_details.append("Good time ✅")
            else:
                bear_details.append("Late session ❌")

            # 5. Volume spike (same as bull)
            if vol_ratio >= 1.2:
                bear_score += 1
                bear_details.append("Volume {:.1f}x ✅".format(vol_ratio))
            else:
                bear_details.append("Volume {:.1f}x ❌".format(vol_ratio))

            # ──────────────────── DEBUG + RETURN ───────────────────────
            if debug and symbol:
                tag = symbol.replace('.NS', '').replace('^', '')
                print("[SCAN] {} | Bull:{}/10 Break:{:.2f}% | Bear:{}/10 Down:{:.2f}% | Price:{:.2f}".format(
                    tag, bull_score, breakout_pct, bear_score, breakdown_pct, current_price))

            # Bullish wins if tied
            if bull_score >= 5 and bull_score >= bear_score:
                if debug and symbol:
                    for d in bull_details:
                        print("       [BUY] {}".format(d))
                return {
                    'score': bull_score,
                    'price': current_price,
                    'type': 'BUY',
                    'reasons': bull_details
                }
            elif bear_score >= 5 and bear_score > bull_score:
                if debug and symbol:
                    for d in bear_details:
                        print("       [SELL] {}".format(d))
                return {
                    'score': bear_score,
                    'price': current_price,
                    'type': 'SELL',
                    'reasons': bear_details
                }
            return None

        except Exception as e:
            print("[SCAN] {} error: {}".format(symbol, e))
            return None
