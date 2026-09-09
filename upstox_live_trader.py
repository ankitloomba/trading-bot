import os
import time
import yfinance as yf
import pandas as pd
from datetime import datetime
import pytz

from strategy import BreakoutStrategy
from config import *
from upstox_broker import UpstoxBroker

try:
    from db import setup_db, log_trade
    DB_AVAILABLE = True
except Exception:
    DB_AVAILABLE = False

IST = pytz.timezone('Asia/Kolkata')

class UpstoxLiveTrader:
    def __init__(self):
        self.strategy = BreakoutStrategy()
        self.broker = UpstoxBroker()
        self.position = None
        self.entry_price = None
        self.entry_time = None
        self.daily_pnl = 0
        self.daily_trades = []
        self.capital = STARTING_CAPITAL
        self.profit_target = float(os.environ.get('PROFIT_TARGET', PROFIT_TARGET))
        self.stop_loss = float(os.environ.get('STOP_LOSS', STOP_LOSS))

        print("\n" + "="*60)
        print("  UPSTOX LIVE TRADER")
        print("="*60)
        print("Symbol:        {}".format(SYMBOL))
        print("Capital:       Rs.{:,.0f}".format(self.capital))
        print("Profit target: {:.1f}%".format(self.profit_target * 100))
        print("Stop loss:     {:.1f}%".format(self.stop_loss * 100))
        print("Mode:          {}".format('PAPER' if PAPER_TRADE else 'LIVE'))
        print("="*60)

        if DB_AVAILABLE:
            try:
                setup_db()
                print("Database: Connected")
            except Exception as e:
                print("Database: {}".format(e))

    def is_market_open(self):
        now = datetime.now(IST)
        if now.weekday() >= 5:
            return False
        open_t = now.replace(hour=9, minute=15, second=0)
        close_t = now.replace(hour=15, minute=30, second=0)
        return open_t <= now <= close_t

    def is_trading_time(self):
        now = datetime.now(IST)
        cutoff = now.replace(hour=14, minute=30, second=0)
        return self.is_market_open() and now <= cutoff

    def get_live_data(self):
        try:
            raw = yf.download(SYMBOL, period='1d', interval='5m', progress=False)
            if raw.empty:
                return None
            df = pd.DataFrame({
                'Open': raw['Open'].values.flatten(),
                'High': raw['High'].values.flatten(),
                'Low': raw['Low'].values.flatten(),
                'Close': raw['Close'].values.flatten(),
                'Volume': raw['Volume'].values.flatten()
            }, index=raw.index)
            return df
        except Exception as e:
            print("Data error: {}".format(e))
            return None

    def check_signals(self, df):
        closes = pd.Series(df['Close'].values.flatten(), index=df.index)
        highs = pd.Series(df['High'].values.flatten(), index=df.index)
        current_price = float(closes.iloc[-1])
        now = datetime.now(IST).strftime('%H:%M:%S')

        if self.position is None and self.is_trading_time():
            i = len(closes) - 1
            if i < BREAKOUT_PERIODS + 1:
                return
            prev_high = float(highs.iloc[i-BREAKOUT_PERIODS:i].max())
            rsi = self.strategy.calculate_rsi(closes)
            rsi_val = float(rsi.iloc[-1]) if not pd.isna(rsi.iloc[-1]) else 50.0
            if current_price > prev_high and RSI_OVERSOLD < rsi_val < RSI_OVERBOUGHT:
                self.position = 'LONG'
                self.entry_price = current_price
                self.entry_time = now
                print("\n[{}] BUY SIGNAL".format(now))
                print("  Entry:  Rs.{:.2f}".format(self.entry_price))
                print("  Target: Rs.{:.2f} (+{:.1f}%)".format(
                    self.entry_price * (1 + self.profit_target),
                    self.profit_target * 100))
                print("  Stop:   Rs.{:.2f} (-{:.1f}%)".format(
                    self.entry_price * (1 - self.stop_loss),
                    self.stop_loss * 100))

        elif self.position == 'LONG':
            profit_pct = (current_price - self.entry_price) / self.entry_price
            if profit_pct >= self.profit_target:
                self.exit_trade(current_price, 'PROFIT +{:.2f}%'.format(profit_pct * 100), now)
            elif profit_pct <= -self.stop_loss:
                self.exit_trade(current_price, 'STOPLOSS {:.2f}%'.format(profit_pct * 100), now)
            else:
                print("[{}] HOLDING | Rs.{:.2f} | {:.2f}%".format(
                    now, current_price, profit_pct * 100))

    def exit_trade(self, exit_price, reason, now):
        pnl = exit_price - self.entry_price
        pnl_pct = (pnl / self.entry_price) * 100
        self.daily_pnl += pnl
        self.capital += pnl
        trade = {
            'symbol': SYMBOL,
            'entry_time': self.entry_time,
            'exit_time': now,
            'entry_price': round(self.entry_price, 2),
            'exit_price': round(exit_price, 2),
            'pnl': round(pnl, 2),
            'pnl_pct': round(pnl_pct, 4),
            'reason': reason
        }
        self.daily_trades.append(trade)
        icon = "WIN" if pnl > 0 else "LOSS"
        print("\n[{}] EXIT - {}".format(now, icon))
        print("  Entry:     Rs.{:.2f}".format(self.entry_price))
        print("  Exit:      Rs.{:.2f}".format(exit_price))
        print("  P&L:       Rs.{:.2f} ({:.2f}%)".format(pnl, pnl_pct))
        print("  Capital:   Rs.{:,.2f}".format(self.capital))
        print("  Daily P&L: Rs.{:.2f}".format(self.daily_pnl))
        if DB_AVAILABLE:
            try:
                log_trade(trade)
            except Exception as e:
                print("DB error: {}".format(e))
        self.position = None
        self.entry_price = None
        if self.daily_pnl <= -MAX_LOSS_PER_DAY:
            print("\nDAILY LOSS LIMIT Rs.{} HIT - Stopping".format(MAX_LOSS_PER_DAY))
            self.print_summary()
            exit(0)

    def print_summary(self):
        wins = len([t for t in self.daily_trades if t['pnl'] > 0])
        losses = len([t for t in self.daily_trades if t['pnl'] <= 0])
        print("\n" + "="*60)
        print("  DAILY SUMMARY")
        print("="*60)
        print("Trades:    {} (W:{} L:{})".format(len(self.daily_trades), wins, losses))
        print("Total P&L: Rs.{:.2f}".format(self.daily_pnl))
        print("Capital:   Rs.{:,.2f}".format(self.capital))
        print("="*60)

    def run(self):
        print("\nWaiting for market open (9:15am IST)...")
        while True:
            try:
                if not self.is_market_open():
                    now = datetime.now(IST)
                    if now.hour >= 15 and now.minute >= 30:
                        print("\nMarket closed.")
                        self.print_summary()
                        break
                    time.sleep(60)
                    continue
                df = self.get_live_data()
                if df is not None and len(df) > BREAKOUT_PERIODS:
                    self.check_signals(df)
                else:
                    print("Waiting for data...")
                time.sleep(300)
            except KeyboardInterrupt:
                print("\nStopped manually.")
                self.print_summary()
                break
            except Exception as e:
                print("Error: {} - retrying in 60s".format(e))
                time.sleep(60)

if __name__ == '__main__':
    trader = UpstoxLiveTrader()
    trader.run()
