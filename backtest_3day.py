import yfinance as yf
import pandas as pd
from datetime import datetime, timedelta
from config import *
from strategy import BreakoutStrategy


def download_data(symbol, days=10, interval='5m'):
    print('Downloading {}-day {} data for {}...'.format(days, interval, symbol))
    end_date = datetime.now()
    start_date = end_date - timedelta(days=days + 4)
    try:
        raw = yf.download(symbol, start=start_date, end=end_date, interval=interval, progress=False)
        if raw.empty:
            print('No data found for {}'.format(symbol))
            return None
        df = pd.DataFrame({
            'Open': raw['Open'].values.flatten(),
            'High': raw['High'].values.flatten(),
            'Low': raw['Low'].values.flatten(),
            'Close': raw['Close'].values.flatten(),
            'Volume': raw['Volume'].values.flatten()
        }, index=raw.index)
        print('Downloaded {} candles ({} to {})'.format(
            len(df), df.index[0].date(), df.index[-1].date()))
        return df
    except Exception as e:
        print('Error: {}'.format(e))
        return None


def print_results(trades, capital):
    if not trades:
        print('\nNo trades generated during backtest')
        return
    df_t = pd.DataFrame(trades)
    total = len(trades)
    wins = len(df_t[df_t['pnl'] > 0])
    losses = len(df_t[df_t['pnl'] <= 0])
    win_rate = (wins / total * 100) if total > 0 else 0
    # Correct P&L using position sizing (risk 2% per trade)
    risk_per_trade = capital * 0.02
    point_pnl = df_t['pnl_pct'].sum()
    total_pnl = (df_t['pnl_pct'] / 100 * capital).sum()
    avg_pnl = total_pnl / total
    ending = capital + total_pnl
    roi = (total_pnl / capital) * 100

    print('\n' + '=' * 60)
    print('  10-DAY BACKTEST RESULTS (Bank Nifty 5-min)')
    print('=' * 60)
    print('\n  TRADE STATISTICS:')
    print('   Total Trades:    {}'.format(total))
    print('   Winning Trades:  {}'.format(wins))
    print('   Losing Trades:   {}'.format(losses))
    print('   Win Rate:        {:.1f}%'.format(win_rate))
    print('\n  PROFITABILITY (on Rs.{:,.0f} capital):'.format(capital))
    print('   Total P&L:        Rs.{:,.2f}'.format(total_pnl))
    print('   Ending Capital:   Rs.{:,.2f}'.format(ending))
    print('   ROI:              {:.2f}%'.format(roi))
    print('\n  TRADE METRICS:')
    print('   Avg Trade P&L:    Rs.{:,.2f}'.format(avg_pnl))
    print('   Total Points:     {:.1f} pts'.format(point_pnl))
    print('=' * 60)

    print('\n  INDIVIDUAL TRADES:')
    for t in trades:
        icon = 'W' if t['pnl'] > 0 else 'L'
        print('   [{}] {} | Entry: Rs.{:.0f} | Exit: Rs.{:.0f} | {:.3f}% | {}'.format(
            icon, t['entry_time'][11:16], t['entry_price'],
            t['exit_price'], t['pnl_pct'], t['reason']))

    if total_pnl > 0:
        print('\n   STRATEGY IS PROFITABLE ({:.1f}% ROI over 10 days)'.format(roi))
        print('   Projected monthly: Rs.{:,.0f}'.format(total_pnl * 2.2))
    else:
        print('\n   STRATEGY SHOWS A LOSS - parameters need tuning')


def main():
    print('\n  TRADING BOT - 10 DAY BACKTEST')
    print('=' * 60)
    print('Symbol: {} | Capital: Rs.{}'.format(SYMBOL, STARTING_CAPITAL))
    print('Strategy: Breakout + RSI | Profit: {}% | Stop: {}%'.format(
        PROFIT_TARGET * 100, STOP_LOSS * 100))
    print('=' * 60)
    df = download_data(SYMBOL, days=10, interval='5m')
    if df is None:
        return
    print('\nRunning backtest...')
    strategy = BreakoutStrategy()
    trades = strategy.backtest(df)
    print_results(trades, STARTING_CAPITAL)


if __name__ == '__main__':
    main()
