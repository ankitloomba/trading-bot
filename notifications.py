import os
import requests
from datetime import datetime

class Notifier:
    def __init__(self):
        self.token = os.environ.get('TELEGRAM_BOT_TOKEN', '')
        self.chat_id = os.environ.get('TELEGRAM_CHAT_ID', '')
        self.enabled = bool(self.token and self.chat_id)
        if self.enabled:
            print("Notifications: Telegram enabled")
        else:
            print("Notifications: Telegram not configured (set TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID)")

    def send(self, message):
        if not self.enabled:
            print("[NOTIFY] {}".format(message))
            return
        try:
            url = "https://api.telegram.org/bot{}/sendMessage".format(self.token)
            requests.post(url, json={
                'chat_id': self.chat_id,
                'text': message,
                'parse_mode': 'HTML'
            }, timeout=5)
        except Exception as e:
            print("Notification error: {}".format(e))

    def trade_open(self, symbol, price, score, capital, target_stop):
        msg = (
            "🤖 <b>BOT BOUGHT</b>\n"
            "Symbol: {}\n"
            "Entry: ₹{:,.2f}\n"
            "Capital: ₹{:,.0f}\n"
            "Signal score: {}/10\n"
            "Hard stop: ₹{:,.2f}\n"
            "Time: {}"
        ).format(symbol, price, capital, score,
                 target_stop, datetime.now().strftime('%H:%M:%S'))
        self.send(msg)

    def trade_close(self, symbol, entry, exit_p, pnl, reason, capital):
        icon = "✅" if pnl >= 0 else "❌"
        msg = (
            "{} <b>BOT SOLD</b>\n"
            "Symbol: {}\n"
            "Entry: ₹{:,.2f} → Exit: ₹{:,.2f}\n"
            "P&L: <b>{}</b>\n"
            "Reason: {}\n"
            "Capital now: ₹{:,.0f}\n"
            "Time: {}"
        ).format(icon, symbol, entry, exit_p,
                 ('+' if pnl>=0 else '')+str(round(pnl,2)),
                 reason, capital, datetime.now().strftime('%H:%M:%S'))
        self.send(msg)

    def daily_summary(self, trades, capital, start_capital):
        wins = len([t for t in trades if t['pnl'] > 0])
        losses = len([t for t in trades if t['pnl'] <= 0])
        total_pnl = sum(t['pnl'] for t in trades)
        pct = (total_pnl / start_capital) * 100
        msg = (
            "📊 <b>DAILY SUMMARY</b>\n"
            "Trades: {} (W:{} L:{})\n"
            "Total P&L: {} ({:.1f}%)\n"
            "Capital: ₹{:,.0f}\n"
            "Date: {}"
        ).format(len(trades), wins, losses,
                 ('+' if total_pnl>=0 else '')+str(round(total_pnl,2)),
                 pct, capital, datetime.now().strftime('%Y-%m-%d'))
        self.send(msg)

    def crash_alert(self, error):
        msg = "⚠️ <b>BOT STOPPED</b>\nError: {}\nTime: {}".format(
            error, datetime.now().strftime('%H:%M:%S'))
        self.send(msg)

    def market_open(self, capital, variant):
        msg = "🔔 <b>MARKET OPEN</b>\nBot starting...\nCapital: ₹{:,.0f}\nVariant: {}\nTime: {}".format(
            capital, variant, datetime.now().strftime('%H:%M:%S'))
        self.send(msg)
