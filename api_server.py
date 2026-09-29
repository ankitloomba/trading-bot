"""
Intra Gini API Server
Runs alongside the trading bot, exposes live data for the PWA.
Endpoints:
  GET /api/status   — live positions, capital, daily P&L, bot state
  GET /api/trades   — today's completed trades from DB
  GET /api/summary  — daily summary history
  GET /health       — uptime check
"""
import os
import threading
from datetime import datetime
from flask import Flask, jsonify
import pytz

IST = pytz.timezone('Asia/Kolkata')
app = Flask(__name__)

# Shared state — written by the trading bot, read by API
_state = {
    'status':          'STARTING',   # STARTING / LIVE / MARKET_CLOSED
    'capital':         0,
    'daily_pnl':       0,
    'positions':       [],           # active stock positions
    'options':         [],           # active options positions
    'last_scan':       None,
    'symbols_scanned': 0,
}

def update_state(**kwargs):
    """Called by the trader every scan cycle."""
    _state.update(kwargs)
    _state['last_scan'] = datetime.now(IST).strftime('%H:%M:%S')


def _db_query(sql, params=()):
    try:
        import psycopg2
        conn = psycopg2.connect(os.environ.get('DATABASE_URL'))
        cur = conn.cursor()
        cur.execute(sql, params)
        cols = [d[0] for d in cur.description]
        rows = [dict(zip(cols, row)) for row in cur.fetchall()]
        cur.close()
        conn.close()
        return rows
    except Exception as e:
        return []


@app.route('/health')
def health():
    return jsonify({'ok': True, 'time': datetime.now(IST).strftime('%H:%M:%S IST')})


@app.route('/api/status')
def status():
    pos = _state.get('positions', [])
    opts = _state.get('options', [])
    return jsonify({
        'status':    _state.get('status', 'STARTING'),
        'capital':   round(_state.get('capital', 0), 2),
        'daily_pnl': round(_state.get('daily_pnl', 0), 2),
        'last_scan': _state.get('last_scan'),
        'positions': [
            {
                'symbol':      p.get('symbol', ''),
                'entry_price': round(p.get('entry_price', 0), 2),
                'current':     round(p.get('current_price', 0), 2),
                'pnl':         round(p.get('pnl', 0), 2),
                'pnl_pct':     round(p.get('pnl_pct', 0), 2),
            } for p in pos
        ],
        'options': [
            {
                'name':          '{}-{}'.format(o.get('index_name',''), o.get('option_type','')),
                'strike':        o.get('strike', 0),
                'entry_premium': round(o.get('entry_premium', 0), 2),
                'peak_premium':  round(o.get('highest_premium', 0), 2),
                'pnl':           round((o.get('highest_premium', 0) - o.get('entry_premium', 0)) * o.get('lot_size', 15), 2),
            } for o in opts
        ],
    })


@app.route('/api/trades')
def trades():
    today = datetime.now(IST).strftime('%Y-%m-%d')
    rows = _db_query(
        "SELECT * FROM trades WHERE DATE(created_at AT TIME ZONE 'Asia/Kolkata') = %s ORDER BY created_at DESC",
        (today,)
    )
    # Convert datetime objects to strings
    for r in rows:
        for k, v in r.items():
            if hasattr(v, 'isoformat'):
                r[k] = str(v)
    return jsonify({'date': today, 'trades': rows, 'count': len(rows)})


@app.route('/api/summary')
def summary():
    rows = _db_query(
        "SELECT * FROM daily_summary ORDER BY date DESC LIMIT 30"
    )
    for r in rows:
        for k, v in r.items():
            if hasattr(v, 'isoformat'):
                r[k] = str(v)
    return jsonify({'history': rows})


def start(port=8080):
    """Start the API server in a background thread."""
    def run():
        app.run(host='0.0.0.0', port=port, debug=False, use_reloader=False)
    t = threading.Thread(target=run, daemon=True)
    t.start()
    print("[API] Server started on port {}".format(port))
    return t
