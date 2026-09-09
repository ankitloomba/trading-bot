import os
import time
import yfinance as yf
import pandas as pd
from datetime import datetime
import pytz
import random

from strategy import BreakoutStrategy
from config import *
from notifications import Notifier
from ab_test import ABTest

try:
    from db import setup_db, log_trade
    DB_AVAILABLE = True
except:
    DB_AVAILABLE = False

IST = pytz.timezone('Asia/Kolkata')

class Position:
    def __init__(self, symbol, entry_price, capital, score, variant, params):
        self.symbol = symbol
        self.entry_price = entry_price
        self.capital = capital
        self.score = score
        self.variant = variant
        self.params = params
        self.highest_price = entry_price
        self.entry_time = datetime.now(IST).strftime('%H:%M:%S')
        self.hard_stop = entry_price * (1 - params['stop_loss'])

    def update_trailing(self, current_price):
        self.highest_price = max(self.highest_price, current_price)

    def should_exit(self, current_price):
        profit_pct = (current_price - self.entry_price) / self.entry_price

        if self.params['use_trailing']:
            trail_stop = self.highest_price * (1 - self.params['trail_pct'])
            if current_price < trail_stop and self.highest_price > self.entry_price * 1.005:
                return True, 'TRAIL_STOP'
        else:
            if profit_pct >= self.params['profit_target']:
                return True, 'PROFIT_TARGET'

        if current_price <= self.hard_stop:
            return True, 'HARD_STOP'
        return False, None

    def unrealised_pnl(self, current_price):
        return (current_price - self.entry_price) / self.entry_price * self.capital


class AdaptiveTrader:
    def __init__(self):
        self.strategy = BreakoutStrategy()
        self.notifier = Notifier()
        self.ab_test = ABTest()
        self.positions = []
        self.daily_trades = []
        self.daily_pnl = 0
        self.capital = float(os.environ.get('STARTING_CAPITAL', STARTING_CAPITAL))
        self.start_capital = self.capital

        if DB_AVAILABLE:
            try:
                setup_db()
                print("Database: Connected")
            except Exception as e:
                print("Database: {}".format(e))

        print("\n" + "="*60)
        print("  ADAPTIVE TRADING BOT v2")
        print("="*60)
        print("Capital:     Rs.{:,.0f}".format(self.capital))
        print("Max trades:  {}".format(MAX_POSITIONS))
        print("Buffer:      Rs.{:,.0f}".format(BUFFER_CASH))
        print("Stop loss:   {:.1f}%".format(STOP_LOSS*100))
        print("A/B testing: {}".format("Enabled" if AB_TEST_ENABLED else "Disabled"))
        print("="*60)
        print(self.ab_test.get_report())

    def is_market_open(self):
        now = datetime.now(IST)
        if now.weekday() >= 5:
            return False
        o = now.replace(hour=9, minute=15, second=0)
        c = now.replace(hour=15, minute=30, second=0)
        return o <= now <= c

    def is_trading_time(self):
        now = datetime.now(IST)
        cutoff = now.replace(hour=14, minute=30, second=0)
        return self.is_market_open() and now <= cutoff

    def available_capital(self):
        used = sum(p.capital for p in self.positions)
        return self.capital - used - BUFFER_CASH

    def allocate_capital(self, n_signals):
        """Allocate capital across signals based on count."""
        avail = self.available_capital()
        if avail <= 0:
            return []
        if n_signals == 1:
            return [avail]
        elif n_signals == 2:
            return [avail * 0.6, avail * 0.4]
        else:
            return [avail * 0.5, avail * 0.3, avail * 0.2]

    def get_live_data(self, symbol=None):
        sym = symbol or SYMBOL
        try:
            raw = yf.download(sym, period='1d', interval='5m', progress=False)
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

    def check_entries(self):
        if not self.is_trading_time():
            return
        if len(self.positions) >= MAX_POSITIONS:
            return
        if self.available_capital() < 500:
            return

        df = self.get_live_data()
        if df is None or len(df) < BREAKOUT_PERIODS + 2:
            return

        signal = self.strategy.get_signal(df)
        if not signal:
            return

        variant = self.ab_test.get_variant_for_trade() if AB_TEST_ENABLED else 'A'
        params = self.ab_test.get_params(variant)
        allocations = self.allocate_capital(1)
        if not allocations:
            return

        alloc = allocations[0]
        now = datetime.now(IST).strftime('%H:%M:%S')
        pos = Position(SYMBOL, signal['price'], alloc, signal['score'], variant, params)
        self.positions.append(pos)

        print("\n[{}] BUY - Variant {} | Score: {}/10".format(now, variant, signal['score']))
        print("  Entry:   Rs.{:.2f}".format(signal['price']))
        print("  Capital: Rs.{:,.0f}".format(alloc))
        print("  Mode:    {}".format(params['name']))
        print("  Stop:    Rs.{:.2f}".format(pos.hard_stop))

        self.notifier.trade_open(
            SYMBOL, signal['price'], signal['score'],
            alloc, pos.hard_stop
        )

    def check_exits(self):
        df = self.get_live_data()
        if df is None:
            return
        current_price = float(df['Close'].values.flatten()[-1])
        now = datetime.now(IST).strftime('%H:%M:%S')

        to_remove = []
        for pos in self.positions:
            pos.update_trailing(current_price)
            exit_trade, reason = pos.should_exit(current_price)

            if exit_trade or (datetime.now(IST).hour >= 15 and datetime.now(IST).minute >= 15):
                reason = reason or 'TIME_EXIT'
                pnl = (current_price - pos.entry_price) / pos.entry_price * pos.capital
                self.capital += pnl
                self.daily_pnl += pnl
                icon = "WIN" if pnl >= 0 else "LOSS"

                trade = {
                    'symbol': pos.symbol,
                    'entry_time': pos.entry_time,
                    'exit_time': now,
                    'entry_price': pos.entry_price,
                    'exit_price': current_price,
                    'highest_price': pos.highest_price,
                    'pnl': round(pnl, 2),
                    'pnl_pct': round((current_price-pos.entry_price)/pos.entry_price*100, 4),
                    'reason': reason,
                    'capital_used': pos.capital,
                    'signal_score': pos.score,
                    'variant': pos.variant
                }
                self.daily_trades.append(trade)

                print("\n[{}] {} - Variant {}".format(now, icon, pos.variant))
                print("  Entry:   Rs.{:.2f}".format(pos.entry_price))
                print("  Peak:    Rs.{:.2f}".format(pos.highest_price))
                print("  Exit:    Rs.{:.2f}".format(current_price))
                print("  P&L:     Rs.{:.2f} ({:.2f}%)".format(pnl, trade['pnl_pct']))
                print("  Reason:  {}".format(reason))
                print("  Capital: Rs.{:,.2f}".format(self.capital))
                print("  Daily:   Rs.{:.2f}".format(self.daily_pnl))

                self.notifier.trade_close(
                    pos.symbol, pos.entry_price, current_price, pnl, reason, self.capital)

                if AB_TEST_ENABLED:
                    self.ab_test.log_trade(pos.variant, trade)

                if DB_AVAILABLE:
                    try:
                        log_trade(trade)
                    except:
                        pass

                to_remove.append(pos)

                if self.daily_pnl <= -MAX_LOSS_PER_DAY:
                    print("\nDAILY LOSS LIMIT HIT - Stopping")
                    self.notifier.crash_alert("Daily loss limit Rs.{} reached".format(MAX_LOSS_PER_DAY))
                    self.print_summary()
                    exit(0)

        for pos in to_remove:
            self.positions.remove(pos)

    def print_summary(self):
        wins = len([t for t in self.daily_trades if t['pnl'] > 0])
        losses = len([t for t in self.daily_trades if t['pnl'] <= 0])
        print("\n" + "="*60)
        print("  DAILY SUMMARY")
        print("="*60)
        print("Trades:    {} (W:{} L:{})".format(len(self.daily_trades), wins, losses))
        print("P&L:       Rs.{:.2f}".format(self.daily_pnl))
        print("Capital:   Rs.{:,.2f}".format(self.capital))
        print(self.ab_test.get_report())
        self.notifier.daily_summary(self.daily_trades, self.capital, self.start_capital)

    def run(self):
        self.notifier.market_open(self.capital, 'A+B')
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

                self.check_exits()
                self.check_entries()

                now = datetime.now(IST).strftime('%H:%M:%S')
                positions_str = "{} open".format(len(self.positions)) if self.positions else "no positions"
                print("[{}] Scanning... {} | Capital: Rs.{:,.0f} | Daily P&L: Rs.{:.0f}".format(
                    now, positions_str, self.capital, self.daily_pnl))

                time.sleep(300)

            except KeyboardInterrupt:
                print("\nStopped manually.")
                self.print_summary()
                break
            except Exception as e:
                print("Error: {} - retrying in 60s".format(e))
                self.notifier.crash_alert(str(e))
                time.sleep(60)

if __name__ == '__main__':
    trader = AdaptiveTrader()
    trader.run()
