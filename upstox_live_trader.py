import os
import time
import yfinance as yf
import pandas as pd
from datetime import datetime
import pytz

from strategy import BreakoutStrategy
from config import *
from notifications import Notifier
from ab_test import ABTest

try:
    from options_trader import BankNiftyOptionsTrader
    OPTIONS_AVAILABLE = True
except:
    OPTIONS_AVAILABLE = False

try:
    from db import setup_db, log_trade
    DB_AVAILABLE = True
except:
    DB_AVAILABLE = False

IST = pytz.timezone('Asia/Kolkata')

# Global access token for options
ACCESS_TOKEN = None

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


class AdaptiveTrader:
    def __init__(self):
        self.strategy = BreakoutStrategy()
        self.notifier = Notifier()
        self.ab_test = ABTest()
        self.positions = []
        self.options_position = None
        self.options_trader = None
        self.daily_trades = []
        self.daily_pnl = 0
        self.capital = float(os.environ.get('STARTING_CAPITAL', STARTING_CAPITAL))
        self.start_capital = self.capital
        self.symbols = SYMBOLS
        self.scan_interval = int(os.environ.get('SCAN_INTERVAL', '60'))
        self.min_score = int(os.environ.get('MIN_SIGNAL_SCORE', str(MIN_SIGNAL_SCORE)))

        if DB_AVAILABLE:
            try:
                setup_db()
                print("Database: Connected")
            except Exception as e:
                print("Database: {}".format(e))

        print("\n" + "="*60)
        print("  {} {} - MULTI-SYMBOL + OPTIONS TRADER".format(BOT_NAME, BOT_EMOJI))
        print("="*60)
        print("Capital:   Rs.{:,.0f}".format(self.capital))
        print("Symbols:   {}".format(len(self.symbols)))
        for s in self.symbols:
            print("  - {}".format(s))
        print("Options:   Bank Nifty CE/PE ({}enabled)".format(
            "" if OPTIONS_ENABLED and OPTIONS_AVAILABLE else "NOT "))
        print("Min score: {}/10".format(self.min_score))
        print("Interval:  {}s".format(self.scan_interval))
        print("Stop:      {:.1f}%".format(STOP_LOSS*100))
        print("="*60)

    def set_access_token(self, token):
        global ACCESS_TOKEN
        ACCESS_TOKEN = token
        if OPTIONS_ENABLED and OPTIONS_AVAILABLE and token:
            self.options_trader = BankNiftyOptionsTrader(token)
            print("[OPTIONS] Bank Nifty options trader ready!")

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
        options_used = OPTIONS_CAPITAL if self.options_position else 0
        return self.capital - used - options_used - BUFFER_CASH

    def get_live_data(self, symbol):
        try:
            raw = yf.download(symbol, period='1d', interval='5m', progress=False)
            if raw.empty:
                return None
            return pd.DataFrame({
                'Open': raw['Open'].values.flatten(),
                'High': raw['High'].values.flatten(),
                'Low': raw['Low'].values.flatten(),
                'Close': raw['Close'].values.flatten(),
                'Volume': raw['Volume'].values.flatten()
            }, index=raw.index)
        except:
            return None

    def check_options(self):
        """Check options exit and entry"""
        if not self.options_trader:
            return

        # Check exit first
        if self.options_position:
            exit_trade, reason, pnl = self.options_trader.should_exit_option(
                self.options_position)
            force_exit = (datetime.now(IST).hour >= 15 and
                         datetime.now(IST).minute >= 10)
            if exit_trade or force_exit:
                reason = reason or 'TIME_EXIT'
                self.options_trader.sell_option(self.options_position)
                entry = self.options_position['entry_premium']
                current = self.options_position.get('highest_premium', entry)
                actual_pnl = pnl if pnl != 0 else (current - entry) * self.options_position['lot_size']
                self.capital += actual_pnl
                self.daily_pnl += actual_pnl
                icon = "WIN" if actual_pnl >= 0 else "LOSS"
                now = datetime.now(IST).strftime('%H:%M:%S')
                print("\n[{}] OPTIONS {} | P&L: Rs.{:+.2f} | {}".format(
                    now, icon, actual_pnl, reason))
                self.notifier.trade_close(
                    'BANKNIFTY-OPTIONS', entry, current,
                    actual_pnl, reason, self.capital)
                self.options_position = None

        # Check entry
        if (not self.options_position and
            self.is_trading_time() and
            self.options_trader and
            self.capital - BUFFER_CASH - OPTIONS_CAPITAL > 0):

            # Use Bank Nifty signal for options direction
            df = self.get_live_data("^NSEBANK")
            if df is not None and len(df) > BREAKOUT_PERIODS + 2:
                signal = self.strategy.get_signal(df, symbol=symbol)
                if signal and signal['score'] >= self.min_score:
                    now = datetime.now(IST).strftime('%H:%M:%S')
                    spot = signal['price']
                    print("\n[{}] OPTIONS SIGNAL | Score:{}/10 | BankNifty:{:.0f}".format(
                        now, signal['score'], spot))
                    pos = self.options_trader.buy_option(spot, 'BUY')
                    if pos:
                        self.options_position = pos
                        self.notifier.trade_open(
                            'BANKNIFTY-CE', pos['entry_premium'],
                            signal['score'], OPTIONS_CAPITAL, 0)

    def check_entries(self):
        if not self.is_trading_time():
            return
        if len(self.positions) >= MAX_POSITIONS:
            return
        if self.available_capital() < 500:
            return

        active_symbols = [p.symbol for p in self.positions]
        signals = []
        for symbol in self.symbols:
            if symbol in active_symbols:
                continue
            df = self.get_live_data(symbol)
            if df is None or len(df) < BREAKOUT_PERIODS + 2:
                continue
            signal = self.strategy.get_signal(df, symbol=symbol)
            if signal and signal['score'] >= self.min_score:
                signals.append((symbol, signal))

        if not signals:
            return

        signals.sort(key=lambda x: x[1]['score'], reverse=True)
        slots = MAX_POSITIONS - len(self.positions)
        signals = signals[:slots]

        avail = self.available_capital()
        if len(signals) == 1:
            allocs = [avail]
        elif len(signals) == 2:
            allocs = [avail * 0.6, avail * 0.4]
        else:
            allocs = [avail * 0.5, avail * 0.3, avail * 0.2]

        for idx, (symbol, signal) in enumerate(signals):
            if idx >= len(allocs):
                break
            variant = self.ab_test.get_variant_for_trade() if AB_TEST_ENABLED else 'A'
            params = self.ab_test.get_params(variant)
            pos = Position(symbol, signal['price'], allocs[idx], signal['score'], variant, params)
            self.positions.append(pos)
            now = datetime.now(IST).strftime('%H:%M:%S')
            print("\n[{}] BUY {} | Score:{}/10 | Var:{} | Rs.{:,.0f}".format(
                now, symbol, signal['score'], variant, allocs[idx]))
            self.notifier.trade_open(symbol, signal['price'],
                                     signal['score'], allocs[idx], pos.hard_stop)

    def check_exits(self):
        to_remove = []
        for pos in self.positions:
            df = self.get_live_data(pos.symbol)
            if df is None:
                continue
            current_price = float(df['Close'].values.flatten()[-1])
            now = datetime.now(IST).strftime('%H:%M:%S')
            pos.update_trailing(current_price)
            exit_trade, reason = pos.should_exit(current_price)
            force_exit = (datetime.now(IST).hour >= 15 and datetime.now(IST).minute >= 15)
            if exit_trade or force_exit:
                reason = reason or 'TIME_EXIT'
                pnl = (current_price - pos.entry_price) / pos.entry_price * pos.capital
                self.capital += pnl
                self.daily_pnl += pnl
                icon = "WIN" if pnl >= 0 else "LOSS"
                print("\n[{}] {} {} | P&L: Rs.{:+.2f} | Capital: Rs.{:,.0f}".format(
                    now, icon, pos.symbol, pnl, self.capital))
                self.notifier.trade_close(pos.symbol, pos.entry_price,
                                         current_price, pnl, reason, self.capital)
                trade = {
                    'symbol': pos.symbol, 'entry_time': pos.entry_time,
                    'exit_time': now, 'entry_price': pos.entry_price,
                    'exit_price': current_price, 'pnl': round(pnl, 2),
                    'pnl_pct': round((current_price-pos.entry_price)/pos.entry_price*100, 4),
                    'reason': reason, 'variant': pos.variant
                }
                self.daily_trades.append(trade)
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
                    self.print_summary()
                    exit(0)
        for pos in to_remove:
            self.positions.remove(pos)

    def print_summary(self):
        wins = len([t for t in self.daily_trades if t['pnl'] > 0])
        losses = len([t for t in self.daily_trades if t['pnl'] <= 0])
        print("\n=== {} {} DAILY SUMMARY ===".format(BOT_NAME, BOT_EMOJI))
        print("Trades: {} (W:{} L:{})".format(len(self.daily_trades), wins, losses))
        print("P&L:    Rs.{:.2f}".format(self.daily_pnl))
        print("Capital: Rs.{:,.2f}".format(self.capital))
        self.notifier.daily_summary(self.daily_trades, self.capital, self.start_capital)

    def run(self):
        self.notifier.market_open(self.capital, 'A+B')
        print("\nScanning {} symbols + Bank Nifty options every {}s...".format(
            len(self.symbols), self.scan_interval))
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
                self.check_options()
                self.check_entries()

                now = datetime.now(IST).strftime('%H:%M:%S')
                stocks = ", ".join([p.symbol.split(".")[0].replace("^","")
                                   for p in self.positions]) or "none"
                opts = "{}CE".format(self.options_position['strike']) \
                    if self.options_position else "none"
                print("[{}] Stocks:{} | Options:{} | Capital:Rs.{:,.0f} | Daily:Rs.{:.0f}".format(
                    now, stocks, opts, self.capital, self.daily_pnl))

                time.sleep(self.scan_interval)

            except KeyboardInterrupt:
                print("\nStopped.")
                self.print_summary()
                break
            except Exception as e:
                print("Error: {} - retrying in 30s".format(e))
                time.sleep(30)

if __name__ == '__main__':
    trader = AdaptiveTrader()
    trader.run()
