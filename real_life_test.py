"""
REAL LIFE TEST SCENARIO
Simulates exactly what would have happened if the bot ran
on the last 5 trading days with the new adaptive strategy + A/B test.
"""
import yfinance as yf
import pandas as pd
from datetime import datetime, timedelta
from strategy import BreakoutStrategy
from ab_test import ABTest
from config import *

def run_real_life_test():
    print("\n" + "="*60)
    print("  REAL LIFE TEST - LAST 5 DAYS")
    print("  Adaptive strategy + A/B test simulation")
    print("="*60)

    raw = yf.download(SYMBOL, period='7d', interval='5m', progress=False)
    if raw.empty:
        print("No data!")
        return

    df = pd.DataFrame({
        'Open': raw['Open'].values.flatten(),
        'High': raw['High'].values.flatten(),
        'Low': raw['Low'].values.flatten(),
        'Close': raw['Close'].values.flatten(),
        'Volume': raw['Volume'].values.flatten()
    }, index=raw.index)

    strategy = BreakoutStrategy()
    ab = ABTest()
    capital = 5000.0
    all_trades = []
    trade_count = 0

    closes = pd.Series(df['Close'].values.flatten(), index=df.index)
    highs = pd.Series(df['High'].values.flatten(), index=df.index)

    position = None
    entry_price = None
    entry_time = None
    highest_price = None
    current_variant = None
    current_params = None
    capital_used = None

    for i in range(BREAKOUT_PERIODS + 2, len(closes)):
        current = float(closes.iloc[i])
        ts = closes.index[i]

        if position is None:
            score, details = strategy.signal_strength(closes, highs, highs, i)
            if score >= MIN_SIGNAL_SCORE:
                variant = 'A' if trade_count % 2 == 0 else 'B'
                params = ab.get_params(variant)
                position = 'LONG'
                entry_price = current
                entry_time = ts
                highest_price = current
                current_variant = variant
                current_params = params
                capital_used = min(capital * 0.9, capital - BUFFER_CASH)
                print("\n[{}] BUY | Score:{}/10 | Variant:{} | Rs.{:.0f} | Capital:Rs.{:.0f}".format(
                    str(ts)[11:16], score, variant, current, capital_used))

        elif position == 'LONG':
            highest_price = max(highest_price, current)
            exit_trade = False
            reason = None

            if current_params['use_trailing']:
                trail_stop = highest_price * (1 - current_params['trail_pct'])
                if current < trail_stop and highest_price > entry_price * 1.005:
                    exit_trade = True
                    reason = 'TRAIL_STOP'
            else:
                if (current - entry_price) / entry_price >= current_params['profit_target']:
                    exit_trade = True
                    reason = 'PROFIT_TARGET'

            if (current - entry_price) / entry_price <= -current_params['stop_loss']:
                exit_trade = True
                reason = 'HARD_STOP'

            if exit_trade:
                pnl = (current - entry_price) / entry_price * capital_used
                capital += pnl
                trade = {
                    'entry_time': str(entry_time)[11:16],
                    'exit_time': str(ts)[11:16],
                    'entry': round(entry_price, 0),
                    'exit': round(current, 0),
                    'peak': round(highest_price, 0),
                    'pnl': round(pnl, 2),
                    'pct': round((current-entry_price)/entry_price*100, 2),
                    'reason': reason,
                    'variant': current_variant,
                    'capital': round(capital, 2)
                }
                all_trades.append(trade)
                trade_count += 1
                icon = "WIN" if pnl >= 0 else "LOSS"
                print("[{}] {} | {} | Rs.{:+.2f} | Peak:Rs.{:.0f} | Capital:Rs.{:.0f}".format(
                    str(ts)[11:16], icon, reason, pnl, highest_price, capital))
                position = None
                entry_price = None
                highest_price = None

    print("\n" + "="*60)
    print("  RESULTS")
    print("="*60)
    wins = [t for t in all_trades if t['pnl'] > 0]
    losses = [t for t in all_trades if t['pnl'] <= 0]
    total_pnl = sum(t['pnl'] for t in all_trades)

    print("Total trades: {}".format(len(all_trades)))
    print("Wins: {} | Losses: {}".format(len(wins), len(losses)))
    print("Win rate: {:.1f}%".format(len(wins)/len(all_trades)*100 if all_trades else 0))
    print("Total P&L: Rs.{:.2f}".format(total_pnl))
    print("Final capital: Rs.{:.2f}".format(capital))
    print("ROI: {:.2f}%".format((capital-5000)/5000*100))

    print("\n--- A/B BREAKDOWN ---")
    for v in ['A','B']:
        v_trades = [t for t in all_trades if t['variant']==v]
        if v_trades:
            v_wins = len([t for t in v_trades if t['pnl']>0])
            v_pnl = sum(t['pnl'] for t in v_trades)
            print("Variant {} ({}): {} trades | {:.0f}% WR | Rs.{:.2f} P&L | Avg Rs.{:.2f}".format(
                v, ab.VARIANTS[v]['name'], len(v_trades),
                v_wins/len(v_trades)*100, v_pnl, v_pnl/len(v_trades)))

    if len(wins) > 0:
        best = max(all_trades, key=lambda t: t['pnl'])
        print("\nBest trade: +Rs.{:.2f} at {} ({})".format(best['pnl'], best['entry_time'], best['reason']))
    if len(losses) > 0:
        worst = min(all_trades, key=lambda t: t['pnl'])
        print("Worst trade: Rs.{:.2f} at {} ({})".format(worst['pnl'], worst['entry_time'], worst['reason']))
    print("="*60)

if __name__ == '__main__':
    run_real_life_test()
