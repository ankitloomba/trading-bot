import os
import psycopg2
from datetime import datetime

def get_connection():
    return psycopg2.connect(os.environ.get('DATABASE_URL'))

def setup_db():
    conn = get_connection()
    cur = conn.cursor()
    cur.execute('''
        CREATE TABLE IF NOT EXISTS trades (
            id SERIAL PRIMARY KEY,
            symbol VARCHAR(20),
            entry_time VARCHAR(50),
            exit_time VARCHAR(50),
            entry_price FLOAT,
            exit_price FLOAT,
            pnl FLOAT,
            pnl_pct FLOAT,
            reason VARCHAR(50),
            created_at TIMESTAMP DEFAULT NOW()
        );
        CREATE TABLE IF NOT EXISTS signals (
            id SERIAL PRIMARY KEY,
            symbol VARCHAR(20),
            signal_type VARCHAR(10),
            price FLOAT,
            rsi FLOAT,
            created_at TIMESTAMP DEFAULT NOW()
        );
        CREATE TABLE IF NOT EXISTS daily_summary (
            id SERIAL PRIMARY KEY,
            date DATE UNIQUE,
            total_trades INT,
            wins INT,
            losses INT,
            total_pnl FLOAT,
            starting_capital FLOAT,
            ending_capital FLOAT,
            created_at TIMESTAMP DEFAULT NOW()
        );
    ''')
    conn.commit()
    cur.close()
    conn.close()
    print("Database tables ready!")

def log_trade(trade):
    try:
        conn = get_connection()
        cur = conn.cursor()
        cur.execute('''
            INSERT INTO trades (symbol, entry_time, exit_time, entry_price, exit_price, pnl, pnl_pct, reason)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        ''', (
            trade.get('symbol', 'BANKNIFTY'),
            trade.get('entry_time'),
            trade.get('exit_time'),
            trade.get('entry_price'),
            trade.get('exit_price'),
            trade.get('pnl'),
            trade.get('pnl_pct'),
            trade.get('reason')
        ))
        conn.commit()
        cur.close()
        conn.close()
        print("Trade logged to DB: PnL Rs.{:.2f}".format(trade.get('pnl', 0)))
    except Exception as e:
        print("DB log error: {}".format(e))

def log_daily_summary(date, trades, capital):
    try:
        wins = len([t for t in trades if t['pnl'] > 0])
        losses = len([t for t in trades if t['pnl'] <= 0])
        total_pnl = sum(t['pnl'] for t in trades)
        conn = get_connection()
        cur = conn.cursor()
        cur.execute('''
            INSERT INTO daily_summary (date, total_trades, wins, losses, total_pnl, starting_capital, ending_capital)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (date) DO UPDATE SET
                total_trades = EXCLUDED.total_trades,
                wins = EXCLUDED.wins,
                losses = EXCLUDED.losses,
                total_pnl = EXCLUDED.total_pnl,
                ending_capital = EXCLUDED.ending_capital
        ''', (date, len(trades), wins, losses, total_pnl, capital, capital + total_pnl))
        conn.commit()
        cur.close()
        conn.close()
        print("Daily summary logged!")
    except Exception as e:
        print("DB summary error: {}".format(e))

if __name__ == '__main__':
    setup_db()
