import os
import requests
from datetime import datetime

BOT_NAME = "Intra Gini 🔥"

class Notifier:
    def __init__(self):
        self.webhook_url = os.environ.get('NOTIFICATION_WEBHOOK', '')
        self.db_notify = True
        print("Notifications: Web Push via PWA enabled")

    def _write_notification(self, notif_type, title, body, data=None):
        """Write notification to DB so PWA can push it to iPhone."""
        try:
            from db import get_connection
            conn = get_connection()
            cur = conn.cursor()
            cur.execute('''
                CREATE TABLE IF NOT EXISTS notifications (
                    id SERIAL PRIMARY KEY,
                    type VARCHAR(50),
                    title VARCHAR(200),
                    body TEXT,
                    data JSONB,
                    read BOOLEAN DEFAULT FALSE,
                    created_at TIMESTAMP DEFAULT NOW()
                )
            ''')
            import json
            cur.execute(
                'INSERT INTO notifications (type, title, body, data) VALUES (%s, %s, %s, %s)',
                (notif_type, title, body, json.dumps(data or {}))
            )
            conn.commit()
            cur.close()
            conn.close()
            print("[NOTIFY] {} - {}".format(title, body))
        except Exception as e:
            print("[NOTIFY] {} - {} (DB error: {})".format(title, body, e))

    def trade_open(self, symbol, price, score, capital, hard_stop):
        self._write_notification(
            'TRADE_OPEN',
            '{} Bought {}'.format(BOT_NAME, symbol),
            'Entry ₹{:,.0f} | Capital ₹{:,.0f} | Score {}/10'.format(price, capital, score),
            {'symbol': symbol, 'price': price, 'capital': capital, 'score': score}
        )

    def trade_close(self, symbol, entry, exit_p, pnl, reason, capital):
        icon = '✅' if pnl >= 0 else '❌'
        self._write_notification(
            'TRADE_CLOSE',
            '{} {} {}'.format(icon, BOT_NAME, 'Win!' if pnl >= 0 else 'Stop hit'),
            '{:+.0f} P&L | {} → {} | {}'.format(pnl, entry, exit_p, reason),
            {'symbol': symbol, 'pnl': pnl, 'reason': reason, 'capital': capital}
        )

    def daily_summary(self, trades, capital, start_capital):
        wins = len([t for t in trades if t['pnl'] > 0])
        losses = len([t for t in trades if t['pnl'] <= 0])
        total_pnl = sum(t['pnl'] for t in trades)
        self._write_notification(
            'DAILY_SUMMARY',
            '{} Day Summary'.format(BOT_NAME),
            '{:+.0f} P&L | {}W {}L | Capital ₹{:,.0f}'.format(
                total_pnl, wins, losses, capital),
            {'pnl': total_pnl, 'wins': wins, 'losses': losses, 'capital': capital}
        )

    def crash_alert(self, error):
        self._write_notification(
            'CRASH',
            '⚠️ {} Stopped'.format(BOT_NAME),
            'Error: {}'.format(str(error)[:100]),
            {'error': str(error)}
        )

    def market_open(self, capital, variant):
        self._write_notification(
            'MARKET_OPEN',
            '{} Market Open 🔔'.format(BOT_NAME),
            'Capital ₹{:,.0f} | Scanning for signals...'.format(capital),
            {'capital': capital, 'variant': variant}
        )
