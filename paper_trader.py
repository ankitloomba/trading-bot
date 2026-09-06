import csv
import os
from datetime import datetime
from config import *


class PaperTrader:
    def __init__(self, starting_capital=STARTING_CAPITAL):
        self.capital = starting_capital
        self.trades = []
        self.log_file = 'paper_trading_log.csv'
        if not os.path.exists(self.log_file):
            with open(self.log_file, 'w', newline='') as f:
                csv.writer(f).writerow(
                    ['Date', 'Time', 'Symbol', 'Entry', 'Exit', 'Qty', 'PnL', 'Capital', 'Notes'])

    def log_trade(self, entry_price, exit_price, quantity=1, notes=''):
        pnl = (exit_price - entry_price) * quantity
        pnl_pct = ((exit_price - entry_price) / entry_price) * 100
        self.capital += pnl
        with open(self.log_file, 'a', newline='') as f:
            csv.writer(f).writerow([
                datetime.now().strftime('%Y-%m-%d'),
                datetime.now().strftime('%H:%M:%S'),
                SYMBOL, entry_price, exit_price, quantity,
                '{:.2f}'.format(pnl), '{:.2f}'.format(self.capital), notes
            ])
        self.trades.append({'pnl': pnl})
        icon = '+' if pnl > 0 else '-'
        print('\n{} Trade: Entry Rs.{:.1f} | Exit Rs.{:.1f} | P&L Rs.{:.2f} | Capital Rs.{:,.2f}'.format(
            icon, entry_price, exit_price, pnl, self.capital))

    def summary(self):
        if not self.trades:
            print('\nNo trades logged yet')
            return
        total_pnl = sum(t['pnl'] for t in self.trades)
        wins = len([t for t in self.trades if t['pnl'] > 0])
        print('\n' + '=' * 50)
        print('  DAILY SUMMARY')
        print('=' * 50)
        print('Starting: Rs.{:,.2f}'.format(STARTING_CAPITAL))
        print('Current:  Rs.{:,.2f}'.format(self.capital))
        print('P&L:      Rs.{:,.2f}'.format(total_pnl))
        print('Trades:   {} (Wins: {})'.format(len(self.trades), wins))
        print('=' * 50)


def main():
    trader = PaperTrader()
    print('\n  PAPER TRADING - 3 DAY TRIAL')
    print('=' * 50)
    print('Commands: log / summary / exit')
    print('=' * 50)
    while True:
        cmd = input('\n> ').strip().lower()
        if cmd == 'exit':
            trader.summary()
            break
        elif cmd == 'log':
            try:
                entry = float(input('  Entry Price: '))
                exit_p = float(input('  Exit Price: '))
                trader.log_trade(entry, exit_p)
            except ValueError:
                print('Invalid input')
        elif cmd == 'summary':
            trader.summary()


if __name__ == '__main__':
    main()
