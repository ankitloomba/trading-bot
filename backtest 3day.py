import yfinance as yf
import pandas as pd
from datetime import datetime, timedelta
from config import *
from strategy import BreakoutStrategy


def download_data(symbol, days=3, interval='5m'):
    print('Downloading {}-day {} data for {}...'.format(days, interval, symbol))
    end_date = datetime.now()
    start_date = end_date - timedelta(days=days + 2)
    try:
        df = yf.download(symbol, start=start_date, end=end_date, interval=interval, progress=False, auto_adjust=True)
        if df.empty:
            print('No data found for {}'.format(symbol))
            return None
        # Fix multi-level columns from newer yfinance
        if isinstance(df.columns, pd.MultiIndex):
            df = df.droplevel(1, axis=1)
        # Ensure all columns are 1D Series
        for col in df.columns:
            if hasattr(df[col], 'columns'):
                df[col] = df[col].iloc[:, 0]
        print('Downloaded {} candles'.format(len(df)))
        print('Columns: {}'.format(list(df.columns)))
        print('Close type: {}'.format(type(df['Close'])))
        print('Close shape: {}'.format(df['Close'].shape))
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
    total_pnl = df_t['pnl'].sum()
    avg_pnl = df_t['pnl'].mean()
    best = df_t['pnl'].max()
    worst = df_t['pnl'].min()
    ending = capital + total_pnl
    roi = (total_pnl / capital) * 100
    pf = (df_t[df_t['pnl'] > 0]['pnl'].sum() / abs(df_t[df_t['pnl'] <= 0]['pnl'].sum())
          if losses > 0 else float('inf'))

    print('\n' + '=' * 60)
    print('  3-DAY BACKTEST RESULTS')
    print('=' * 60)
    print('\n  TRADE STATISTICS:')
    print('   Total Trades:    {}'.format(total))
    print('   Winning Trades:  {}'.format(wins))
    print('   Losing Trades:   {}'.format(losses))
    print('   Win Rate:        {:.1f}%'.format(win_rate))
    print('\n  PROFITABILITY:')
    print('   Starting Capital: Rs.{:,.2f}'.format(capital))
    print('   Total P&L:        Rs.{:,.2f}'.format(total_pnl))
    print('   Ending Capital:   Rs.{:,.2f}'.format(ending))
    print('   ROI:              {:.2f}%'.format(roi))
    print('\n  TRADE METRICS:')
    print('   Avg Trade P&L:    Rs.{:,.2f}'.format(avg_pnl))
    print('   Best Trade:       Rs.{:,.2f}'.format(best))
    print('   Worst Trade:      Rs.{:,.2f}'.format(worst))
    print('   Profit Factor:    {:.2f}'.format(pf))
    print('=' * 60)

    print('\n  INDIVIDUAL TRADES:')
    for t in trades:
        icon = '+' if t['pnl'] > 0 else '-'
        print('   {} Entry: Rs.{:.0f} Exit: Rs.{:.0f} P&L: Rs.{:.2f} ({})'.format(
            icon, t['entry_price'], t['exit_price'], t['pnl'], t['reason']))

    if total_pnl > 0:
        print('\n   STRATEGY IS PROFITABLE ({:.1f}% ROI)'.format(roi))
    else:
        print('\n   STRATEGY SHOWS A LOSS ({:.1f}% ROI)'.format(roi))


def main():
    print('\n  TRADING BOT - 3 DAY BACKTEST')
    print('=' * 60)
    print('Symbol: {}'.format(SYMBOL))
    print('Starting Capital: Rs.{}'.format(STARTING_CAPITAL))
    print('=' * 60)
    df = download_data(SYMBOL, days=3, interval='5m')
    if df is None:
        return
    print('\nRunning backtest...')
    strategy = BreakoutStrategy()
    trades = strategy.backtest(df)
    print_results(trades, STARTING_CAPITAL)


if __name__ == '__main__':
    main()
