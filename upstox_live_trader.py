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
    from options_trader import MultiOptionsTrader
    OPTIONS_AVAILABLE = True
except:
    OPTIONS_AVAILABLE = False

try:
    from upstox_broker import UpstoxBroker
    BROKER_AVAILABLE = True
except:
    BROKER_AVAILABLE = False

try:
    from db import setup_db, log_trade
    DB_AVAILABLE = True
except:
    DB_AVAILABLE = False

IST = pytz.timezone('Asia/Kolkata')

class Position:
    def __init__(self, symbol, entry_price, capital, score, variant, params, broker_pos=None):
        self.symbol = symbol
        self.entry_price = entry_price
        self.capital = capital
        self.score = score
        self.variant = variant
        self.params = params
        self.broker_pos = broker_pos  # Real broker position data
        self.highest_price = entry_price
        self.entry_time = datetime.now(IST).strftime('%H:%M:%S')
        self.hard_stop = entry_price * (1 - params['stop_loss'])

    def update_trailing(self, current_price):
        self.highest_price = max(self.highest_price, current_price)

    def should_exit(self, current_price):
        if self.params['use_trailing']:
            trail_stop = self.highest_price * (1 - self.params['trail_pct'])
            if current_price < trail_stop and self.highest_price > self.entry_price * 1.005:
                return True, 'TRAIL_STOP'
        else:
            if (current_price - self.entry_price) / self.entry_price >= self.params['profit_target']:
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
        self.broker = None
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
                print(f"Database: {e}")

        print("\n" + "="*60)
        print(f"  {BOT_NAME} {BOT_EMOJI} - MULTI-SYMBOL + OPTIONS TRADER")
        print("="*60)
        print(f"Capital:   Rs.{self.capital:,.0f}")
        print(f"Symbols:   {len(self.symbols)}")
        for s in self.symbols:
            print(f"  - {s}")
        print(f"Options:   Bank Nifty + Nifty + NiftyIT CE/PE")
        print(f"Min score: {self.min_score}/10")
        print(f"Interval:  {self.scan_interval}s")
        print("="*60)

    def set_access_token(self, token):
        if BROKER_AVAILABLE and token:
            self.broker = UpstoxBroker(token)
            print("[BROKER] ✅ Real stock orders enabled!")
            # Check funds
            funds = self.broker.get_funds()
            if funds:
                print(f"[BROKER] Available funds: Rs.{funds:,.2f}")

        if OPTIONS_AVAILABLE and token:
            self.options_trader = MultiOptionsTrader(token)
            print("[OPTIONS] ✅ Options trader ready!")

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
        opts_used = OPTIONS_CAPITAL if self.options_position else 0
        return self.capital - used - opts_used - BUFFER_CASH

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
        if not self.options_trader:
            return

        # Exit existing options position
        if self.options_position:
            exit_trade, reason, pnl = self.options_trader.should_exit_option(self.options_position)
            force_exit = (datetime.now(IST).hour >= 15 and datetime.now(IST).minute >= 10)
            if exit_trade or force_exit:
                reason = reason or 'TIME_EXIT'
                self.options_trader.sell_option(self.options_position)
                entry = self.options_position['entry_premium']
                actual_pnl = pnl if pnl != 0 else 0
                self.capital += actual_pnl
                self.daily_pnl += actual_pnl
                now = datetime.now(IST).strftime('%H:%M:%S')
                icon = "WIN" if actual_pnl >= 0 else "LOSS"
                print(f"\n[{now}] OPTIONS {icon} | P&L: Rs.{actual_pnl:+.2f} | {reason}")
                self.notifier.trade_close(
                    f"{self.options_position['index_name']}-{self.options_position['option_type']}",
                    entry, entry, actual_pnl, reason, self.capital)
                self.options_position = None

        # Enter new options position
        if (not self.options_position and self.is_trading_time() and
                self.capital - BUFFER_CASH - OPTIONS_CAPITAL > 0):
            for opt_symbol in OPTIONS_SYMBOLS:
                df = self.get_live_data(opt_symbol)
                if df is None or len(df) < BREAKOUT_PERIODS + 2:
                    continue
                signal = self.strategy.get_signal(df, symbol=opt_symbol, debug=False)
                if signal and signal['score'] >= self.min_score:
                    now = datetime.now(IST).strftime('%H:%M:%S')
                    print(f"\n[{now}] OPTIONS SIGNAL {opt_symbol} | Score:{signal['score']}/10")
                    pos = self.options_trader.buy_option(opt_symbol, signal['price'], 'BUY')
                    if pos:
                        self.options_position = pos
                        self.notifier.trade_open(
                            f"{pos['index_name']}-CE",
                            pos['entry_premium'],
                            signal['score'],
                            OPTIONS_CAPITAL, 0)
                    break

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
            signal = self.strategy.get_signal(df, symbol=symbol, debug=True)
            if signal and signal['score'] >= self.min_score:
                signals.append((symbol, signal))

        if not signals:
            return

        signals.sort(key=lambda x: x[1]['score'], reverse=True)
        slots = MAX_POSITIONS - len(self.positions)
        avail = self.available_capital()

        allocs = [avail] if len(signals)==1 else \
                 [avail*0.6, avail*0.4] if len(signals)==2 else \
                 [avail*0.5, avail*0.3, avail*0.2]

        for idx, (symbol, signal) in enumerate(signals[:slots]):
            if idx >= len(allocs):
                break
            alloc = allocs[idx]
            variant = self.ab_test.get_variant_for_trade() if AB_TEST_ENABLED else 'A'
            params = self.ab_test.get_params(variant)

            # Place REAL order via broker
            broker_pos = None
            if self.broker:
                broker_pos = self.broker.buy_stock(symbol, alloc)
                if broker_pos:
                    entry_price = broker_pos['entry_price']
                    alloc = broker_pos['capital']
                    print(f"[BROKER] ✅ Real order filled for {symbol}!")
                else:
                    print(f"[BROKER] ❌ Order failed for {symbol} — skipping")
                    continue
            else:
                entry_price = signal['price']

            pos = Position(symbol, entry_price, alloc, signal['score'], variant, params, broker_pos)
            self.positions.append(pos)
            now = datetime.now(IST).strftime('%H:%M:%S')
            print(f"\n[{now}] BUY {symbol} | Score:{signal['score']}/10 | Var:{variant} | Rs.{alloc:,.0f}")
            self.notifier.trade_open(symbol, entry_price, signal['score'], alloc, pos.hard_stop)

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

                # Place REAL sell order
                if self.broker and pos.broker_pos:
                    self.broker.sell_stock(pos.broker_pos)

                pnl = (current_price - pos.entry_price) / pos.entry_price * pos.capital
                self.capital += pnl
                self.daily_pnl += pnl
                icon = "WIN" if pnl >= 0 else "LOSS"
                print(f"\n[{now}] {icon} {pos.symbol} | P&L: Rs.{pnl:+.2f} | Capital: Rs.{self.capital:,.0f}")
                self.notifier.trade_close(pos.symbol, pos.entry_price, current_price, pnl, reason, self.capital)

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
        wins = [t for t in self.daily_trades if t['pnl'] > 0]
        losses = [t for t in self.daily_trades if t['pnl'] <= 0]
        print(f"\n=== {BOT_NAME} {BOT_EMOJI} DAILY SUMMARY ===")
        print(f"Trades: {len(self.daily_trades)} (W:{len(wins)} L:{len(losses)})")
        print(f"P&L:    Rs.{self.daily_pnl:.2f}")
        print(f"Capital: Rs.{self.capital:,.2f}")
        self.notifier.daily_summary(self.daily_trades, self.capital, self.start_capital)

    def run(self):
        self.notifier.market_open(self.capital, 'A+B')
        print(f"\nScanning {len(self.symbols)} symbols + options every {self.scan_interval}s...")
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
                stocks = ", ".join([p.symbol.split(".")[0].replace("^","") for p in self.positions]) or "none"
                opts = f"{self.options_position['index_name']}{self.options_position['option_type']}" \
                    if self.options_position else "none"
                print(f"[{now}] Stocks:{stocks} | Options:{opts} | Capital:Rs.{self.capital:,.0f} | Daily:Rs.{self.daily_pnl:.0f}")
                time.sleep(self.scan_interval)

            except KeyboardInterrupt:
                print("\nStopped.")
                self.print_summary()
                break
            except Exception as e:
                print(f"Error: {e} - retrying in 30s")
                time.sleep(30)

if __name__ == '__main__':
    trader = AdaptiveTrader()
    trader.run()
