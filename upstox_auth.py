"""
Upstox Auto-Auth
- Runs web server on port 8080 for OAuth callback
- Auto-refreshes token daily at 9am using TOTP
- Stores token in memory + env for bot to use
"""
import os
import threading
import time
import requests
import pyotp
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
from datetime import datetime
import pytz

IST = pytz.timezone('Asia/Kolkata')
CLIENT_ID = os.environ.get('UPSTOX_CLIENT_ID')
CLIENT_SECRET = os.environ.get('UPSTOX_CLIENT_SECRET')
REDIRECT_URI = os.environ.get('UPSTOX_REDIRECT_URI')
TOTP_SECRET = os.environ.get('UPSTOX_TOTP_SECRET')
UPSTOX_MOBILE = os.environ.get('UPSTOX_MOBILE', '')
UPSTOX_PIN = os.environ.get('UPSTOX_PIN', '')
BASE_URL = "https://api.upstox.com/v2"

ACCESS_TOKEN = None
TOKEN_EXPIRY = None
_token_callbacks = []

# Live state updated by trader every scan cycle
_live_state = {
    'status': 'STARTING',
    'capital': 0,
    'daily_pnl': 0,
    'positions': [],
    'options': [],
    'last_scan': None,
}

def update_live_state(**kwargs):
    _live_state.update(kwargs)

DASHBOARD_HTML = """\
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<meta name="theme-color" content="#0a0f0a">
<meta name="apple-mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-status-bar-style" content="black-translucent">
<title>Intra Gini 🔥</title>
<link rel="manifest" href="/manifest.json">
<style>
:root{
  --bg:#0a0f0a;--surface:#111811;--card:#182018;--border:#1e2e1e;
  --green:#00d084;--green-dim:#00d08420;--green-text:#4ade80;
  --purple:#a855f7;--purple-dim:#a855f720;
  --red:#f43f5e;--red-dim:#f43f5e20;
  --amber:#f59e0b;--amber-dim:#f59e0b20;
  --text:#e8f5e8;--muted:#5a7a5a;--subtle:#8fa88f;
  --nav-h:68px;--safe-b:env(safe-area-inset-bottom,0px);
}
*{box-sizing:border-box;margin:0;padding:0;-webkit-tap-highlight-color:transparent}
html,body{height:100%;background:var(--bg);color:var(--text);font-family:-apple-system,BlinkMacSystemFont,'SF Pro Display','Segoe UI',sans-serif;overflow-x:hidden}
body{padding-bottom:calc(var(--nav-h) + var(--safe-b))}

/* ── HERO ── */
.hero{
  background:linear-gradient(160deg,#0d1f0d 0%,#0a1a0a 40%,#091409 100%);
  padding:20px 20px 28px;
  position:relative;overflow:hidden;
}
.hero::before{
  content:'';position:absolute;top:-60px;right:-40px;
  width:220px;height:220px;
  background:radial-gradient(circle,#00d08415 0%,transparent 70%);
  border-radius:50%;pointer-events:none;
}
.hero-top{display:flex;justify-content:space-between;align-items:flex-start;margin-bottom:20px}
.greeting{font-size:13px;color:var(--muted);letter-spacing:.3px;margin-bottom:2px}
.hero-title{font-size:18px;font-weight:700;color:var(--text)}
.live-pill{
  display:flex;align-items:center;gap:6px;
  background:var(--green-dim);border:1px solid #00d08440;
  padding:5px 12px;border-radius:20px;
  font-size:11px;font-weight:700;color:var(--green);letter-spacing:.8px;
}
.live-dot{width:6px;height:6px;border-radius:50%;background:var(--green);animation:blink 1.5s ease-in-out infinite}
@keyframes blink{0%,100%{opacity:1;box-shadow:0 0 0 0 #00d08480}50%{opacity:.5;box-shadow:0 0 0 4px #00d08400}}
.capital-label{font-size:12px;color:var(--muted);letter-spacing:.3px;margin-bottom:6px}
.capital-value{font-size:42px;font-weight:800;letter-spacing:-1px;color:var(--text);line-height:1}
.capital-value span{font-size:26px;font-weight:600;color:var(--subtle);margin-right:2px}
.pnl-badge{
  display:inline-flex;align-items:center;gap:5px;
  margin-top:10px;padding:5px 12px;border-radius:20px;
  font-size:13px;font-weight:700;
}
.pnl-badge.pos{background:var(--green-dim);color:var(--green-text);border:1px solid #4ade8030}
.pnl-badge.neg{background:var(--red-dim);color:var(--red);border:1px solid #f43f5e30}
.pnl-badge.zero{background:#1e2e1e;color:var(--muted);border:1px solid var(--border)}

/* ── STAT CARDS ── */
.stats{display:grid;grid-template-columns:1fr 1fr 1fr;gap:10px;padding:16px 16px 4px}
.stat-card{background:var(--card);border:1px solid var(--border);border-radius:16px;padding:14px 12px}
.stat-label{font-size:10px;color:var(--muted);text-transform:uppercase;letter-spacing:.5px;margin-bottom:6px}
.stat-value{font-size:20px;font-weight:800;color:var(--text)}
.stat-value.green{color:var(--green-text)}
.stat-value.red{color:var(--red)}
.stat-sub{font-size:10px;color:var(--muted);margin-top:3px}

/* ── SECTION ── */
.section{padding:20px 16px 4px}
.section-header{display:flex;align-items:center;gap:8px;margin-bottom:12px}
.section-dot{width:8px;height:8px;border-radius:50%;flex-shrink:0}
.section-dot.green{background:var(--green);box-shadow:0 0 8px #00d08460;animation:blink 2s ease-in-out infinite}
.section-dot.purple{background:var(--purple);box-shadow:0 0 8px #a855f760;animation:blink 2.5s ease-in-out infinite}
.section-title{font-size:13px;font-weight:700;color:var(--subtle);text-transform:uppercase;letter-spacing:.5px}
.section-count{font-size:11px;color:var(--muted);background:var(--surface);border:1px solid var(--border);padding:2px 8px;border-radius:20px;margin-left:auto}

/* ── POSITION CARD ── */
.pos-card{
  background:var(--card);border:1px solid var(--border);
  border-radius:16px;padding:16px;margin-bottom:8px;
  display:flex;justify-content:space-between;align-items:center;
}
.pos-card.green-border{border-color:#00d08430}
.pos-card.purple-border{border-color:#a855f730}
.pos-name{font-size:16px;font-weight:700;color:var(--text)}
.pos-meta{font-size:11px;color:var(--muted);margin-top:3px}
.pos-pnl-amt{font-size:18px;font-weight:800;text-align:right}
.pos-pnl-pct{font-size:11px;color:var(--muted);text-align:right;margin-top:2px}
.pos-pnl-amt.green{color:var(--green-text)}
.pos-pnl-amt.red{color:var(--red)}
.pos-pnl-amt.zero{color:var(--muted)}

/* ── EMPTY STATE ── */
.empty{
  background:var(--card);border:1px solid var(--border);border-radius:16px;
  padding:28px;text-align:center;color:var(--muted);font-size:13px;
}
.empty-icon{font-size:28px;margin-bottom:8px;opacity:.4}

/* ── ACTION BUTTONS ── */
.actions{display:grid;grid-template-columns:1fr 1fr 1fr;gap:10px;padding:20px 16px}
.action-btn{
  background:var(--card);border:1px solid var(--border);border-radius:14px;
  padding:14px 8px;text-align:center;cursor:pointer;
  transition:background .15s,border-color .15s;
  color:var(--subtle);font-size:12px;font-weight:600;
}
.action-btn:active{background:var(--surface)}
.action-btn .icon{font-size:20px;margin-bottom:5px;display:block}

/* ── CTA ── */
.cta{
  margin:4px 16px 16px;padding:15px 20px;
  background:linear-gradient(135deg,#00d08415,#00d08408);
  border:1px solid #00d08430;border-radius:16px;
  display:flex;justify-content:space-between;align-items:center;
  cursor:pointer;
}
.cta-text{font-size:13px;font-weight:600;color:var(--green-text)}
.cta-sub{font-size:11px;color:var(--muted);margin-top:2px}
.cta-arrow{color:var(--green);font-size:16px}

/* ── BOTTOM NAV ── */
.nav{
  position:fixed;bottom:0;left:0;right:0;
  height:calc(var(--nav-h) + var(--safe-b));
  background:#0d180d;border-top:1px solid #1a2e1a;
  display:flex;align-items:flex-start;padding-top:10px;
  z-index:100;
}
.nav-item{
  flex:1;display:flex;flex-direction:column;align-items:center;gap:4px;
  padding:4px 0;cursor:pointer;transition:color .15s;
  color:var(--muted);font-size:10px;font-weight:600;letter-spacing:.3px;
}
.nav-item.active{color:var(--green)}
.nav-item svg{width:22px;height:22px;stroke:currentColor;fill:none;stroke-width:1.8;stroke-linecap:round;stroke-linejoin:round}
.nav-item.active svg{stroke:var(--green)}

/* ── PAGES ── */
.page{display:none}.page.active{display:block}

/* ── TRADES PAGE ── */
.trade-item{
  background:var(--card);border:1px solid var(--border);border-radius:14px;
  padding:14px 16px;margin-bottom:8px;
  display:flex;justify-content:space-between;align-items:center;
}
.trade-sym{font-size:15px;font-weight:700}
.trade-time{font-size:11px;color:var(--muted);margin-top:3px}
.trade-reason{
  font-size:10px;padding:2px 7px;border-radius:10px;
  background:var(--surface);color:var(--muted);
  display:inline-block;margin-top:4px;
}
.trade-pnl{font-size:17px;font-weight:800;text-align:right}
.trade-pnl.green{color:var(--green-text)}.trade-pnl.red{color:var(--red)}

/* ── P&L PAGE ── */
.pnl-hero{
  background:linear-gradient(160deg,#0d1f0d,#0a1a0a);
  padding:28px 20px;text-align:center;
}
.pnl-big{font-size:52px;font-weight:900;letter-spacing:-2px}
.pnl-big.green{color:var(--green-text)}.pnl-big.red{color:var(--red)}
.pnl-date{font-size:12px;color:var(--muted);margin-top:6px}
.pnl-grid{display:grid;grid-template-columns:1fr 1fr;gap:10px;padding:16px}

/* ── SETTINGS PAGE ── */
.settings-item{
  background:var(--card);border:1px solid var(--border);border-radius:14px;
  padding:16px;margin-bottom:8px;display:flex;justify-content:space-between;align-items:center;
}
.settings-label{font-size:13px;font-weight:600;color:var(--text)}
.settings-val{font-size:13px;color:var(--muted)}

/* ── REFRESH BAR ── */
.refresh-bar{text-align:center;padding:8px;font-size:10px;color:var(--muted);letter-spacing:.3px}

/* ── SKELETON ── */
.skel{
  background:linear-gradient(90deg,var(--card) 25%,var(--surface) 50%,var(--card) 75%);
  background-size:200% 100%;animation:shimmer 1.5s infinite;
  border-radius:8px;height:16px;
}
@keyframes shimmer{0%{background-position:200% 0}100%{background-position:-200% 0}}
</style>
</head>
<body>

<!-- ══ HOME PAGE ══════════════════════════════════════════════ -->
<div class="page active" id="page-home">

  <div class="hero">
    <div class="hero-top">
      <div>
        <div class="greeting" id="greeting">Good morning, Ankit</div>
        <div class="hero-title">🔥 Intra Gini</div>
      </div>
      <div class="live-pill" id="status-pill">
        <span class="live-dot"></span>
        <span id="status-text">LIVE</span>
      </div>
    </div>
    <div class="capital-label">PORTFOLIO VALUE</div>
    <div class="capital-value"><span>₹</span><span id="hero-capital">—</span></div>
    <div class="pnl-badge zero" id="hero-pnl-badge">
      <span id="hero-pnl-arrow">—</span>
      <span id="hero-pnl">Today's P&L</span>
    </div>
  </div>

  <div class="stats">
    <div class="stat-card">
      <div class="stat-label">Win Rate</div>
      <div class="stat-value green" id="stat-wr">—</div>
      <div class="stat-sub" id="stat-wr-sub">—</div>
    </div>
    <div class="stat-card">
      <div class="stat-label">Trades</div>
      <div class="stat-value" id="stat-trades">—</div>
      <div class="stat-sub" id="stat-trades-sub">today</div>
    </div>
    <div class="stat-card">
      <div class="stat-label">Daily P&L</div>
      <div class="stat-value" id="stat-pnl">—</div>
      <div class="stat-sub" id="stat-scan">last scan —</div>
    </div>
  </div>

  <div class="section">
    <div class="section-header">
      <span class="section-dot green"></span>
      <span class="section-title">Stocks</span>
      <span class="section-count" id="stock-count">0 open</span>
    </div>
    <div id="positions-list">
      <div class="empty"><div class="empty-icon">📈</div>No open stock positions</div>
    </div>
  </div>

  <div class="section">
    <div class="section-header">
      <span class="section-dot purple"></span>
      <span class="section-title">Options</span>
      <span class="section-count" id="opt-count">0 open</span>
    </div>
    <div id="options-list">
      <div class="empty"><div class="empty-icon">⚡</div>No options open</div>
    </div>
  </div>

  <div class="actions">
    <div class="action-btn" onclick="switchTab('trades')">
      <span class="icon">📋</span>Trades
    </div>
    <div class="action-btn" onclick="switchTab('pnl')">
      <span class="icon">📊</span>P&L
    </div>
    <div class="action-btn" onclick="switchTab('settings')">
      <span class="icon">⚙️</span>Settings
    </div>
  </div>

  <div class="cta" onclick="switchTab('pnl')">
    <div>
      <div class="cta-text">View full P&L report</div>
      <div class="cta-sub">Wins, losses & breakdown</div>
    </div>
    <span class="cta-arrow">→</span>
  </div>

  <div class="refresh-bar" id="refresh-bar">Auto-refreshes every 30s</div>
</div>

<!-- ══ TRADES PAGE ════════════════════════════════════════════ -->
<div class="page" id="page-trades">
  <div class="hero" style="padding-bottom:20px">
    <div class="greeting">Closed positions</div>
    <div class="hero-title">📋 Today's Trades</div>
  </div>
  <div style="padding:16px" id="trades-list">
    <div class="empty"><div class="empty-icon">📋</div>No trades closed today yet</div>
  </div>
</div>

<!-- ══ P&L PAGE ══════════════════════════════════════════════ -->
<div class="page" id="page-pnl">
  <div class="pnl-hero">
    <div class="greeting">Today's performance</div>
    <div class="pnl-big zero" id="pnl-big">₹0</div>
    <div class="pnl-date" id="pnl-date">—</div>
  </div>
  <div class="pnl-grid">
    <div class="stat-card">
      <div class="stat-label">Capital</div>
      <div class="stat-value" id="pnl-capital">—</div>
      <div class="stat-sub">current</div>
    </div>
    <div class="stat-card">
      <div class="stat-label">Start</div>
      <div class="stat-value" id="pnl-start">₹5,000</div>
      <div class="stat-sub">today's base</div>
    </div>
    <div class="stat-card">
      <div class="stat-label">Wins</div>
      <div class="stat-value green" id="pnl-wins">—</div>
      <div class="stat-sub">profitable</div>
    </div>
    <div class="stat-card">
      <div class="stat-label">Losses</div>
      <div class="stat-value red" id="pnl-losses">—</div>
      <div class="stat-sub">stopped out</div>
    </div>
  </div>
  <div style="padding:0 16px 16px">
    <div class="stat-card" style="border-radius:16px">
      <div class="stat-label" style="margin-bottom:10px">Trade Breakdown</div>
      <div id="pnl-breakdown" style="color:var(--muted);font-size:13px">Loading...</div>
    </div>
  </div>
</div>

<!-- ══ SETTINGS PAGE ═════════════════════════════════════════ -->
<div class="page" id="page-settings">
  <div class="hero" style="padding-bottom:20px">
    <div class="greeting">Configuration</div>
    <div class="hero-title">⚙️ Settings</div>
  </div>
  <div style="padding:16px">
    <div class="settings-item"><span class="settings-label">Bot Status</span><span class="settings-val" id="cfg-status">—</span></div>
    <div class="settings-item"><span class="settings-label">Capital</span><span class="settings-val" id="cfg-capital">—</span></div>
    <div class="settings-item"><span class="settings-label">Mode</span><span class="settings-val">LIVE</span></div>
    <div class="settings-item"><span class="settings-label">Broker</span><span class="settings-val">Upstox</span></div>
    <div class="settings-item"><span class="settings-label">Scan Interval</span><span class="settings-val">90s</span></div>
    <div class="settings-item"><span class="settings-label">Min Signal Score</span><span class="settings-val">4 / 10</span></div>
    <div class="settings-item"><span class="settings-label">Options</span><span class="settings-val">Enabled (₹1,500/trade)</span></div>
    <div class="settings-item"><span class="settings-label">Max Positions</span><span class="settings-val">3 stocks + 2 options</span></div>
    <div class="settings-item"><span class="settings-label">Daily Loss Limit</span><span class="settings-val">₹500</span></div>
    <div class="settings-item"><span class="settings-label">Last Scan</span><span class="settings-val" id="cfg-scan">—</span></div>
  </div>
</div>

<!-- ══ BOTTOM NAV ═════════════════════════════════════════════ -->
<nav class="nav">
  <div class="nav-item active" id="nav-home" onclick="switchTab('home')">
    <svg viewBox="0 0 24 24"><path d="M3 9l9-7 9 7v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/><polyline points="9 22 9 12 15 12 15 22"/></svg>
    Home
  </div>
  <div class="nav-item" id="nav-pnl" onclick="switchTab('pnl')">
    <svg viewBox="0 0 24 24"><polyline points="22 12 18 12 15 21 9 3 6 12 2 12"/></svg>
    P&amp;L
  </div>
  <div class="nav-item" id="nav-trades" onclick="switchTab('trades')">
    <svg viewBox="0 0 24 24"><rect x="3" y="4" width="18" height="18" rx="2" ry="2"/><line x1="16" y1="2" x2="16" y2="6"/><line x1="8" y1="2" x2="8" y2="6"/><line x1="3" y1="10" x2="21" y2="10"/></svg>
    Trades
  </div>
  <div class="nav-item" id="nav-settings" onclick="switchTab('settings')">
    <svg viewBox="0 0 24 24"><circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 1 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 1 1-2.83-2.83l.06-.06A1.65 1.65 0 0 0 4.68 15a1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 1 1 2.83-2.83l.06.06A1.65 1.65 0 0 0 9 4.68a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 1 1 2.83 2.83l-.06.06A1.65 1.65 0 0 0 19.4 9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z"/></svg>
    Settings
  </div>
</nav>

<script>
// ── Helpers ──────────────────────────────────────────────────
const $ = id => document.getElementById(id);
const INR = n => '₹' + Math.abs(Number(n)).toLocaleString('en-IN', {maximumFractionDigits: 0});
const INRD = n => '₹' + Number(Math.abs(n)).toLocaleString('en-IN', {minimumFractionDigits: 2, maximumFractionDigits: 2});
const sign = n => n >= 0 ? '+' : '−';
const clr = n => n > 0 ? 'green' : n < 0 ? 'red' : 'zero';
const sym = s => (s || '').replace('.NS','').replace('^','');

function greeting(){
  const h = new Date().getHours();
  if (h < 12) return 'Good morning, Ankit';
  if (h < 17) return 'Good afternoon, Ankit';
  return 'Good evening, Ankit';
}

// ── Tab switching ─────────────────────────────────────────────
const tabs = ['home','pnl','trades','settings'];
function switchTab(tab){
  tabs.forEach(t => {
    $('page-'+t).classList.toggle('active', t===tab);
    $('nav-'+t) && $('nav-'+t).classList.toggle('active', t===tab);
  });
  if(tab==='pnl') renderPnl();
}

// ── Status pill ───────────────────────────────────────────────
function setPill(status){
  const pill = $('status-pill');
  const st = $('status-text');
  st.textContent = status;
  pill.style.background = status==='LIVE' ? 'var(--green-dim)' : status==='MARKET_CLOSED' ? 'var(--surface)' : 'var(--amber-dim)';
  pill.style.borderColor = status==='LIVE' ? '#00d08440' : status==='MARKET_CLOSED' ? 'var(--border)' : '#f59e0b40';
  pill.style.color = status==='LIVE' ? 'var(--green)' : status==='MARKET_CLOSED' ? 'var(--muted)' : 'var(--amber)';
}

// ── Fetch & render status ─────────────────────────────────────
let _trades = [];
async function fetchStatus(){
  try{
    const d = await (await fetch('/api/status')).json();
    $('greeting').textContent = greeting();

    // Capital
    const cap = d.capital || 0;
    $('hero-capital').textContent = cap.toLocaleString('en-IN');

    // P&L badge
    const pnl = d.daily_pnl || 0;
    const badge = $('hero-pnl-badge');
    badge.className = 'pnl-badge ' + clr(pnl);
    $('hero-pnl-arrow').textContent = sign(pnl);
    $('hero-pnl').textContent = INR(pnl) + ' today';

    // Status
    setPill(d.status || 'STARTING');

    // Stat cards
    const trades = _trades;
    const wins = trades.filter(t => t.pnl > 0).length;
    const total = trades.length;
    const wr = total ? Math.round(wins/total*100) : 0;
    $('stat-wr').textContent = total ? wr+'%' : '—';
    $('stat-wr').className = 'stat-value ' + (wr >= 50 ? 'green' : wr > 0 ? 'red' : '');
    $('stat-wr-sub').textContent = total ? wins+' of '+total+' wins' : 'no trades yet';
    $('stat-trades').textContent = total || 0;
    $('stat-pnl').textContent = pnl !== 0 ? sign(pnl)+INR(pnl) : '₹0';
    $('stat-pnl').className = 'stat-value ' + clr(pnl);
    $('stat-scan').textContent = 'scan ' + (d.last_scan || '—');

    // Positions
    const pos = d.positions || [];
    $('stock-count').textContent = pos.length + ' open';
    if(!pos.length){
      $('positions-list').innerHTML = '<div class="empty"><div class="empty-icon">📈</div>No open stock positions</div>';
    } else {
      $('positions-list').innerHTML = pos.map(p => {
        const pnlAmt = p.pnl || 0;
        const pnlPct = p.pnl_pct || 0;
        const cur = p.current_price || p.entry_price;
        return `<div class="pos-card green-border">
          <div>
            <div class="pos-name">${sym(p.symbol)}</div>
            <div class="pos-meta">Entry ${INRD(p.entry_price)} · Now ${INRD(cur)}</div>
          </div>
          <div>
            <div class="pos-pnl-amt ${clr(pnlAmt)}">${sign(pnlAmt)}${INR(pnlAmt)}</div>
            <div class="pos-pnl-pct">${sign(pnlPct)}${Number(pnlPct).toFixed(2)}%</div>
          </div>
        </div>`;
      }).join('');
    }

    // Options
    const opts = d.options || [];
    $('opt-count').textContent = opts.length + ' open';
    if(!opts.length){
      $('options-list').innerHTML = '<div class="empty"><div class="empty-icon">⚡</div>No options open</div>';
    } else {
      $('options-list').innerHTML = opts.map(o => {
        const ep = o.entry_premium || 0;
        const peak = o.highest_premium || ep;
        const lot = o.lot_size || 1;
        const pnl = ((o.current_premium||ep) - ep) * lot;
        return `<div class="pos-card purple-border">
          <div>
            <div class="pos-name" style="color:var(--purple)">${o.index_name||'OPT'} ${o.option_type||''}</div>
            <div class="pos-meta">Strike ₹${o.strike||'—'} · Premium ₹${ep}</div>
          </div>
          <div>
            <div class="pos-pnl-amt ${clr(pnl)}">${sign(pnl)}${INR(pnl)}</div>
            <div class="pos-pnl-pct">Peak ₹${peak}</div>
          </div>
        </div>`;
      }).join('');
    }

    $('refresh-bar').textContent = 'Updated ' + new Date().toLocaleTimeString('en-IN',{hour:'2-digit',minute:'2-digit'}) + ' · auto-refresh 30s';

    // Settings page
    $('cfg-status').textContent = d.status || '—';
    $('cfg-capital').textContent = INR(cap);
    $('cfg-scan').textContent = d.last_scan || '—';

    // P&L page capital
    $('pnl-capital').textContent = INR(cap);

  }catch(e){
    setPill('OFFLINE');
  }
}

async function fetchTrades(){
  try{
    const d = await (await fetch('/api/trades')).json();
    _trades = d.trades || [];

    // Trades page
    const el = $('trades-list');
    if(!_trades.length){
      el.innerHTML = '<div class="empty"><div class="empty-icon">📋</div>No trades closed today yet</div>';
    } else {
      el.innerHTML = _trades.map(t => `
        <div class="trade-item">
          <div>
            <div class="trade-sym">${sym(t.symbol)}</div>
            <div class="trade-time">${t.entry_time||''} → ${t.exit_time||''}</div>
            <span class="trade-reason">${t.reason||''}</span>
          </div>
          <div>
            <div class="trade-pnl ${clr(t.pnl)}">${sign(t.pnl)}${INR(t.pnl)}</div>
          </div>
        </div>`).join('');
    }
  }catch(e){}
}

function renderPnl(){
  const trades = _trades;
  const pnl = trades.reduce((s,t)=>s+(t.pnl||0),0);
  const wins = trades.filter(t=>t.pnl>0);
  const losses = trades.filter(t=>t.pnl<=0);
  const big = $('pnl-big');
  big.textContent = sign(pnl) + INR(pnl);
  big.className = 'pnl-big ' + clr(pnl);
  $('pnl-date').textContent = new Date().toLocaleDateString('en-IN',{weekday:'long',day:'numeric',month:'long'});
  $('pnl-wins').textContent = wins.length;
  $('pnl-losses').textContent = losses.length;
  if(!trades.length){
    $('pnl-breakdown').textContent = 'No trades yet today.';
  } else {
    const avgWin = wins.length ? wins.reduce((s,t)=>s+t.pnl,0)/wins.length : 0;
    const avgLoss = losses.length ? losses.reduce((s,t)=>s+t.pnl,0)/losses.length : 0;
    $('pnl-breakdown').innerHTML = `
      <div style="display:flex;justify-content:space-between;margin-bottom:8px">
        <span style="color:var(--muted)">Avg win</span>
        <span style="color:var(--green-text);font-weight:700">${avgWin?'+'+INR(avgWin):'—'}</span>
      </div>
      <div style="display:flex;justify-content:space-between;margin-bottom:8px">
        <span style="color:var(--muted)">Avg loss</span>
        <span style="color:var(--red);font-weight:700">${avgLoss?'−'+INR(Math.abs(avgLoss)):'—'}</span>
      </div>
      <div style="display:flex;justify-content:space-between">
        <span style="color:var(--muted)">Win rate</span>
        <span style="font-weight:700">${trades.length?Math.round(wins.length/trades.length*100)+'%':'—'}</span>
      </div>`;
  }
}

async function refresh(){
  await Promise.all([fetchStatus(), fetchTrades()]);
}

// ── Init ──────────────────────────────────────────────────────
refresh();
setInterval(refresh, 30000);
</script>
</body>
</html>
"""

def on_token(callback):
    """Register a callback to be called when token is obtained."""
    _token_callbacks.append(callback)

def get_upstox_token():
    return ACCESS_TOKEN

def set_angel_broker(angel_broker):
    """Stub — Angel One status shown on page if needed."""
    pass

def _fire_token_callbacks(token):
    for cb in _token_callbacks:
        try:
            cb(token)
        except Exception as e:
            print(f"[AUTH] Token callback error: {e}")

def get_totp():
    return pyotp.TOTP(TOTP_SECRET).now()

def auto_login():
    """Fully automated login using Upstox API + TOTP"""
    global ACCESS_TOKEN, TOKEN_EXPIRY
    print("[AUTH] Attempting automated Upstox login...")
    try:
        # Step 1: Get auth code via API (requires mobile + PIN + TOTP)
        session = requests.Session()
        
        # Step 2: Exchange for token using auth code flow
        # First get the login page to get the auth code
        auth_url = (
            f"https://api.upstox.com/v2/login/authorization/dialog"
            f"?response_type=code"
            f"&client_id={CLIENT_ID}"
            f"&redirect_uri={REDIRECT_URI}"
        )
        
        # Use Upstox login API directly
        totp = get_totp()
        print(f"[AUTH] TOTP generated: {totp}")
        
        # Login with credentials
        login_resp = session.post(
            "https://api.upstox.com/v2/login/authorization/dialog",
            data={
                'mobile': UPSTOX_MOBILE,
                'mpin': UPSTOX_PIN,
                'otp': totp,
                'client_id': CLIENT_ID,
                'redirect_uri': REDIRECT_URI,
            },
            allow_redirects=False
        )
        
        # Extract code from redirect
        location = login_resp.headers.get('Location', '')
        if 'code=' in location:
            code = location.split('code=')[1].split('&')[0]
            token = exchange_code(code)
            if token:
                ACCESS_TOKEN = token
                os.environ['UPSTOX_ACCESS_TOKEN'] = token
                _fire_token_callbacks(token)
                print("[AUTH] Auto-login successful!")
                return True
        
        print(f"[AUTH] Auto-login response: {login_resp.status_code}")
        print("[AUTH] Please login manually at the web URL")
        return False
    except Exception as e:
        print(f"[AUTH] Auto-login error: {e}")
        return False

def exchange_code(auth_code):
    global ACCESS_TOKEN
    try:
        response = requests.post(
            f"{BASE_URL}/login/authorization/token",
            headers={'Content-Type': 'application/x-www-form-urlencoded'},
            data={
                'code': auth_code,
                'client_id': CLIENT_ID,
                'client_secret': CLIENT_SECRET,
                'redirect_uri': REDIRECT_URI,
                'grant_type': 'authorization_code'
            }
        )
        data = response.json()
        if data.get('access_token'):
            print("[AUTH] Token obtained!")
            return data['access_token']
        print(f"[AUTH] Token exchange failed: {data}")
        return None
    except Exception as e:
        print(f"[AUTH] Exchange error: {e}")
        return None

def get_auth_url():
    return (
        f"https://api.upstox.com/v2/login/authorization/dialog"
        f"?response_type=code"
        f"&client_id={CLIENT_ID}"
        f"&redirect_uri={REDIRECT_URI}"
    )

def get_token():
    return ACCESS_TOKEN

def schedule_daily_login():
    """Runs at 9:00am IST every day to refresh token"""
    def loop():
        while True:
            now = datetime.now(IST)
            # Target: 9:00am IST
            target = now.replace(hour=9, minute=0, second=0, microsecond=0)
            if now >= target:
                # Already past 9am today — schedule for tomorrow
                from datetime import timedelta
                target = target + timedelta(days=1)
            wait_secs = (target - now).total_seconds()
            print(f"[AUTH] Next auto-login in {wait_secs/3600:.1f} hours (9:00am IST)")
            time.sleep(wait_secs)
            print("[AUTH] Scheduled daily auto-login starting...")
            auto_login()
    thread = threading.Thread(target=loop, daemon=True)
    thread.start()

def _db_query(sql, params=()):
    try:
        import psycopg2, os
        conn = psycopg2.connect(os.environ.get('DATABASE_URL'))
        cur = conn.cursor()
        cur.execute(sql, params)
        cols = [d[0] for d in cur.description]
        rows = [dict(zip(cols, row)) for row in cur.fetchall()]
        cur.close(); conn.close()
        return rows
    except Exception:
        return []

def _json_response(handler, data, status=200):
    import json
    body = json.dumps(data, default=str).encode()
    handler.send_response(status)
    handler.send_header('Content-Type', 'application/json')
    handler.send_header('Access-Control-Allow-Origin', '*')
    handler.send_header('Content-Length', str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)

class AuthHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args): pass

    def do_GET(self):
        global ACCESS_TOKEN
        parsed = urlparse(self.path)
        path = parsed.path
        params = parse_qs(parsed.query)

        # ── API endpoints ──────────────────────────────────
        if path == '/api/status':
            _json_response(self, _live_state)
            return

        if path == '/api/trades':
            today = datetime.now(IST).strftime('%Y-%m-%d')
            rows = _db_query(
                "SELECT * FROM trades WHERE DATE(created_at AT TIME ZONE 'Asia/Kolkata') = %s ORDER BY created_at DESC",
                (today,)
            )
            _json_response(self, {'date': today, 'trades': rows, 'count': len(rows)})
            return

        if path == '/api/summary':
            rows = _db_query("SELECT * FROM daily_summary ORDER BY date DESC LIMIT 30")
            _json_response(self, {'history': rows})
            return

        if path == '/health':
            _json_response(self, {'ok': True, 'time': datetime.now(IST).strftime('%H:%M:%S IST')})
            return

        if path == '/api/clear-dummy':
            # One-time: delete all trades/summaries that are dummy/test data
            # Keeps only rows where pnl is non-null and entry_price > 0
            try:
                import psycopg2, os as _os2
                conn = psycopg2.connect(_os2.environ.get('DATABASE_URL'))
                cur = conn.cursor()
                cur.execute("DELETE FROM trades WHERE entry_price IS NULL OR entry_price = 0 OR pnl IS NULL")
                deleted_trades = cur.rowcount
                cur.execute("DELETE FROM daily_summary WHERE total_trades = 0 OR total_pnl IS NULL")
                deleted_summary = cur.rowcount
                conn.commit()
                cur.close(); conn.close()
                _json_response(self, {'cleared': True, 'trades_deleted': deleted_trades, 'summary_deleted': deleted_summary})
            except Exception as e:
                _json_response(self, {'error': str(e)}, 500)
            return

        if path == '/api/wipe-all':
            # Nuclear: delete everything — use once to start fresh
            try:
                import psycopg2, os as _os3
                conn = psycopg2.connect(_os3.environ.get('DATABASE_URL'))
                cur = conn.cursor()
                cur.execute("DELETE FROM trades")
                t = cur.rowcount
                cur.execute("DELETE FROM daily_summary")
                s = cur.rowcount
                conn.commit()
                cur.close(); conn.close()
                _json_response(self, {'wiped': True, 'trades': t, 'summaries': s})
            except Exception as e:
                _json_response(self, {'error': str(e)}, 500)
            return

        # ── Dashboard (inlined so Railway filesystem path doesn't matter) ──
        if path == '/dashboard' or path == '/dashboard/':
            body = DASHBOARD_HTML.encode('utf-8')
            self.send_response(200)
            self.send_header('Content-Type', 'text/html; charset=utf-8')
            self.send_header('Content-Length', str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return

        if path == '/manifest.json':
            import json as _json
            body = _json.dumps({
                "name": "Intra Gini", "short_name": "IntraGini",
                "description": "Live trading dashboard",
                "start_url": "/dashboard", "display": "standalone",
                "background_color": "#0a0f0a", "theme_color": "#0a0f0a",
                "icons": []
            }).encode()
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return

        # ── OAuth callback ─────────────────────────────────
        auth_code = params.get('code', [None])[0]

        if auth_code:
            print(f"[AUTH] Got auth code from browser login")
            token = exchange_code(auth_code)
            if token:
                ACCESS_TOKEN = token
                os.environ['UPSTOX_ACCESS_TOKEN'] = token
                _fire_token_callbacks(token)
                self.send_response(200)
                self.send_header('Content-Type', 'text/html')
                self.end_headers()
                self.wfile.write(b"""
                <html><body style="font-family:sans-serif;padding:40px;background:#111;color:white;text-align:center">
                <h1 style="color:#22c55e">Login Successful!</h1>
                <p style="font-size:18px">Intra Gini is now placing real trades.</p>
                <p style="color:#6b7280">You can close this page.</p>
                </body></html>""")
                return

        # Show login page
        self.send_response(200)
        self.send_header('Content-Type', 'text/html; charset=utf-8')
        self.end_headers()
        status = "LOGGED IN ✅" if ACCESS_TOKEN else "WAITING FOR LOGIN"
        color = "#22c55e" if ACCESS_TOKEN else "#f97316"
        auth_url = get_auth_url()
        totp = get_totp() if TOTP_SECRET else "N/A"
        html = f"""
        <html><body style="font-family:-apple-system,sans-serif;padding:40px;background:#111;color:white;text-align:center;max-width:400px;margin:0 auto">
        <h1 style="font-size:32px;margin-bottom:8px">🔥 Intra Gini</h1>
        <p style="color:#6b7280;margin-bottom:24px">Intelligent Intraday Trading Bot</p>
        <div style="background:#1a1a1a;border-radius:16px;padding:20px;margin-bottom:24px">
          <p style="color:#6b7280;font-size:12px;margin-bottom:4px">STATUS</p>
          <p style="color:{color};font-size:18px;font-weight:700">{status}</p>
          {'<p style="color:#22c55e;font-size:14px">Bot is live trading with ₹5,000!</p>' if ACCESS_TOKEN else ''}
        </div>
        {'<div style="background:#1a1a1a;border-radius:16px;padding:20px;margin-bottom:24px"><p style="color:#6b7280;font-size:12px">TOTP (valid 30 secs)</p><p style="font-size:32px;font-weight:700;letter-spacing:8px">'+totp+'</p></div>' if TOTP_SECRET else ''}
        {f'<a href="{auth_url}" style="display:block;background:#7c3aed;color:white;padding:16px 28px;border-radius:12px;text-decoration:none;font-size:16px;font-weight:700">Login with Upstox</a>' if not ACCESS_TOKEN else ''}
        <p style="color:#374151;font-size:12px;margin-top:24px">Capital: ₹5,000 | Mode: {"LIVE" if not os.environ.get("PAPER_TRADE","true") == "true" else "PAPER"}</p>
        </body></html>"""
        self.wfile.write(html.encode())

def start_auth_server():
    server = HTTPServer(('0.0.0.0', 8080), AuthHandler)
    print(f"[AUTH] Web server ready at {REDIRECT_URI}")
    server.serve_forever()

def run_in_background():
    # Try auto-login first if TOTP available
    if TOTP_SECRET:
        threading.Thread(target=auto_login, daemon=True).start()
    # Schedule daily 9am login
    schedule_daily_login()
    # Start web server
    thread = threading.Thread(target=start_auth_server, daemon=True)
    thread.start()
    return thread

if __name__ == '__main__':
    start_auth_server()
