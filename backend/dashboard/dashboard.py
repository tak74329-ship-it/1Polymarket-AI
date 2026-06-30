"""Polymarket-AI Dashboard — FastAPI server serving API + static HTML."""

from datetime import datetime
from fastapi import FastAPI
from fastapi.responses import HTMLResponse
import psycopg2
from backend.utils.config import DB_CONFIG

app = FastAPI(title="Polymarket-AI Dashboard")

TABLES = [
    "markets", "market_prices", "order_books", "news_items",
    "news_market_matches", "market_keywords", "signals", "ai_analysis",
    "market_features", "paper_positions", "paper_orders", "paper_balance",
    "system_logs",
]


def f(v):
    return float(v or 0)


def db_query(sql, params=None):
    conn = psycopg2.connect(**DB_CONFIG)
    cur = conn.cursor()
    cur.execute(sql, params or ())
    rows = cur.fetchall()
    cols = [desc[0] for desc in cur.description]
    cur.close()
    conn.close()
    return [dict(zip(cols, r)) for r in rows]


# ── API Endpoints ─────────────────────────────────────────────────────


@app.get("/api/health")
def api_health():
    data = {}
    for table in TABLES:
        r = db_query(f"SELECT COUNT(*) AS cnt FROM {table}")
        data[table] = r[0]["cnt"]

    # Latest timestamps
    checks = {
        "latest_price": "SELECT MAX(created_at) AS ts FROM market_prices",
        "latest_ai": "SELECT MAX(created_at) AS ts FROM ai_analysis",
        "latest_feature": "SELECT MAX(created_at) AS ts FROM market_features",
        "latest_signal": "SELECT MAX(created_at) AS ts FROM signals",
        "latest_order": "SELECT MAX(created_at) AS ts FROM paper_orders",
        "latest_news": "SELECT MAX(created_at) AS ts FROM news_items",
    }
    for key, sql in checks.items():
        r = db_query(sql)
        data[key] = str(r[0]["ts"]) if r[0]["ts"] else "—"

    return data


@app.get("/api/portfolio")
def api_portfolio():
    bal = db_query("""
        SELECT cash, equity, pnl, roi, updated_at
        FROM paper_balance ORDER BY id DESC LIMIT 1
    """)
    if not bal:
        return {"cash": 10000, "equity": 10000, "pnl": 0, "roi": 0}

    pos = db_query("""
        SELECT COUNT(*) AS cnt,
               COALESCE(SUM(invested), 0) AS total_invested
        FROM paper_positions WHERE status = 'OPEN'
    """)

    result = dict(bal[0])
    result["open_positions"] = pos[0]["cnt"]
    result["total_invested"] = float(pos[0]["total_invested"])
    for k in ("cash", "equity", "pnl", "roi"):
        result[k] = float(result[k])
    return result


@app.get("/api/positions")
def api_positions():
    rows = db_query("""
        SELECT
            p.id,
            p.market_id,
            (SELECT question FROM markets m WHERE m.market_id = p.market_id) AS question,
            p.entry_price,
            p.qty,
            p.invested,
            p.created_at,
            (SELECT yes_price FROM market_prices mp
             WHERE mp.market_id = p.market_id
             ORDER BY mp.created_at DESC LIMIT 1) AS latest_price,
            (SELECT raw->'analysis'->>'action' FROM ai_analysis a
             WHERE a.market_id = p.market_id
             ORDER BY a.created_at DESC LIMIT 1) AS ai_action,
            (SELECT confidence FROM ai_analysis a
             WHERE a.market_id = p.market_id
             ORDER BY a.created_at DESC LIMIT 1) AS ai_confidence,
            (SELECT raw->'analysis'->>'risk_level' FROM ai_analysis a
             WHERE a.market_id = p.market_id
             ORDER BY a.created_at DESC LIMIT 1) AS risk_level
        FROM paper_positions p
        WHERE p.status = 'OPEN'
        ORDER BY p.created_at DESC
    """)

    out = []
    for r in rows:
        ep = f(r["entry_price"])
        lp = f(r["latest_price"]) if r["latest_price"] else ep
        qty = f(r["qty"])
        invested = f(r["invested"])
        current_value = lp * qty
        unrealized_pnl = current_value - invested
        unrealized_roi = (unrealized_pnl / invested * 100) if invested else 0

        out.append({
            "market_id": r["market_id"],
            "question": (r["question"] or "")[:80],
            "entry_price": round(ep, 4),
            "latest_price": round(lp, 4),
            "qty": round(qty, 1),
            "invested": round(invested, 2),
            "current_value": round(current_value, 2),
            "unrealized_pnl": round(unrealized_pnl, 2),
            "unrealized_roi": round(unrealized_roi, 2),
            "ai_action": r["ai_action"] or "—",
            "ai_confidence": round(f(r["ai_confidence"]), 1),
            "risk_level": r["risk_level"] or "—",
        })
    return out


@app.get("/api/ai-decisions")
def api_ai_decisions():
    rows = db_query("""
        SELECT a.market_id,
               (SELECT question FROM markets m WHERE m.market_id = a.market_id) AS question,
               a.model, a.ai_probability, a.confidence,
               a.raw->'analysis'->>'action' AS ai_action,
               a.raw->'analysis'->>'risk_level' AS risk_level,
               a.raw->'analysis'->>'reason' AS reason,
               a.created_at
        FROM ai_analysis a
        ORDER BY a.created_at DESC
        LIMIT 20
    """)
    for r in rows:
        r["ai_probability"] = float(r["ai_probability"] or 0)
        r["confidence"] = float(r["confidence"] or 0)
        r["created_at"] = str(r["created_at"])
    return rows


@app.get("/api/ranked-markets")
def api_ranked_markets():
    rows = db_query("""
        SELECT DISTINCT ON (mf.market_id)
            mf.market_id,
            (SELECT question FROM markets m WHERE m.market_id = mf.market_id) AS question,
            (mf.feature_json->>'latest_yes_price')::numeric AS yes_price,
            (mf.feature_json->>'latest_signal_score')::numeric AS signal_score,
            (mf.feature_json->>'total_signal_score_20')::numeric AS sig20,
            (mf.feature_json->>'news_score')::numeric AS news_score,
            (mf.feature_json->>'orderbook_imbalance')::numeric AS imbalance,
            (mf.feature_json->>'volatility_30_snapshots')::numeric AS volatility,
            (mf.feature_json->>'liquidity')::numeric AS liquidity,
            (mf.feature_json->>'volume')::numeric AS volume,
            mf.created_at
        FROM market_features mf
        WHERE (mf.feature_json->>'has_signal')::bool = true
          AND (mf.feature_json->>'is_active')::bool = true
          AND (mf.feature_json->>'is_closed')::bool = false
        ORDER BY mf.market_id, mf.created_at DESC
        LIMIT 20
    """)
    for r in rows:
        for k in ("yes_price", "signal_score", "sig20", "news_score",
                   "imbalance", "volatility", "liquidity", "volume"):
            r[k] = float(r[k] or 0) if r[k] is not None else 0
        r["created_at"] = str(r["created_at"])
    # Sort by signal descending
    rows.sort(key=lambda x: x["signal_score"] + x["news_score"], reverse=True)
    return rows[:20]


@app.get("/api/news-matches")
def api_news_matches():
    rows = db_query("""
        SELECT nmm.market_id,
               (SELECT question FROM markets m WHERE m.market_id = nmm.market_id) AS question,
               nmm.score, nmm.keywords, nmm.created_at
        FROM news_market_matches nmm
        ORDER BY nmm.created_at DESC
        LIMIT 20
    """)
    for r in rows:
        r["score"] = float(r["score"] or 0)
        r["created_at"] = str(r["created_at"])
    return rows


@app.get("/api/performance")
def api_performance():
    """Paper trading performance over time (last 50 orders)."""
    orders = db_query("""
        SELECT o.market_id,
               (SELECT question FROM markets m WHERE m.market_id = o.market_id) AS question,
               o.side, o.price, o.qty, o.amount, o.reason, o.created_at
        FROM paper_orders o
        ORDER BY o.id DESC
        LIMIT 50
    """)
    for r in orders:
        r["price"] = float(r["price"] or 0)
        r["qty"] = float(r["qty"] or 0)
        r["amount"] = float(r["amount"] or 0)
        r["created_at"] = str(r["created_at"])
    return orders


@app.get("/", response_class=HTMLResponse)
def index():
    return HTMLResponse(DASHBOARD_HTML)


# ═══════════════════════════════════════════════════════════════════════
#  Static HTML dashboard
# ═══════════════════════════════════════════════════════════════════════

DASHBOARD_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Polymarket-AI Dashboard</title>
<style>
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body {
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
    background: #0d1117; color: #c9d1d9; padding: 20px;
  }
  .container { max-width: 1400px; margin: 0 auto; }
  header {
    display: flex; justify-content: space-between; align-items: center;
    padding: 16px 0; border-bottom: 1px solid #30363d; margin-bottom: 20px;
  }
  h1 { font-size: 1.5rem; color: #58a6ff; }
  .last-updated { font-size: 0.85rem; color: #8b949e; }
  .grid {
    display: grid; grid-template-columns: repeat(auto-fit, minmax(320px, 1fr));
    gap: 16px; margin-bottom: 20px;
  }
  .card {
    background: #161b22; border: 1px solid #30363d; border-radius: 8px;
    padding: 16px; overflow: hidden;
  }
  .card h2 {
    font-size: 1rem; color: #58a6ff; margin-bottom: 12px;
    padding-bottom: 8px; border-bottom: 1px solid #21262d;
  }
  .card table {
    width: 100%; border-collapse: collapse; font-size: 0.8rem;
  }
  .card th, .card td {
    text-align: left; padding: 6px 4px; border-bottom: 1px solid #21262d;
    white-space: nowrap;
  }
  .card th { color: #8b949e; font-weight: 500; }
  .stat-row { display: flex; justify-content: space-between; padding: 4px 0; }
  .stat-label { color: #8b949e; }
  .stat-value { font-weight: 600; }
  .positive { color: #3fb950; }
  .negative { color: #f85149; }
  .neutral { color: #d29922; }
  .badge {
    display: inline-block; padding: 2px 8px; border-radius: 12px;
    font-size: 0.7rem; font-weight: 600;
  }
  .badge-buy { background: #1a3a2a; color: #3fb950; }
  .badge-watch { background: #1a2d3a; color: #58a6ff; }
  .badge-skip { background: #3a1a1a; color: #f85149; }
  .badge-low { background: #1a3a2a; color: #3fb950; }
  .badge-medium { background: #3a2a1a; color: #d29922; }
  .badge-high { background: #3a1a1a; color: #f85149; }
  .text-truncate {
    max-width: 200px; overflow: hidden; text-overflow: ellipsis;
    display: inline-block; vertical-align: middle;
  }
  .section-title {
    font-size: 1.1rem; color: #58a6ff; margin: 20px 0 12px;
    padding-bottom: 8px; border-bottom: 1px solid #30363d;
  }
  .scroll-x { overflow-x: auto; }
  @media (max-width: 768px) {
    .grid { grid-template-columns: 1fr; }
    .text-truncate { max-width: 120px; }
  }
</style>
</head>
<body>
<div class="container">
  <header>
    <h1>📊 Polymarket-AI Dashboard</h1>
    <span class="last-updated" id="lastUpdated">Loading...</span>
  </header>

  <!-- Portfolio -->
  <div class="card" style="grid-column: 1 / -1;">
    <h2>💰 Portfolio</h2>
    <div id="portfolioGrid" style="display: grid; grid-template-columns: repeat(auto-fit, minmax(140px, 1fr)); gap: 12px;"></div>
  </div>

  <!-- Health + Performance side by side -->
  <div class="grid">
    <div class="card">
      <h2>⚙️ System Health</h2>
      <div id="healthTable"></div>
    </div>
    <div class="card">
      <h2>📈 Performance</h2>
      <div id="perfTable" class="scroll-x"></div>
    </div>
  </div>

  <h2 class="section-title">📋 Open Positions</h2>
  <div class="card">
    <div id="positionsTable" class="scroll-x"></div>
  </div>

  <h2 class="section-title">🤖 Latest AI Decisions</h2>
  <div class="card">
    <div id="aiTable" class="scroll-x"></div>
  </div>

  <h2 class="section-title">🏆 Top Ranked Markets</h2>
  <div class="card">
    <div id="rankedTable" class="scroll-x"></div>
  </div>

  <h2 class="section-title">📰 Latest News Matches</h2>
  <div class="card">
    <div id="newsTable" class="scroll-x"></div>
  </div>
</div>

<script>
const REFRESH_MS = 30000;

function $(id) { return document.getElementById(id); }

async function fetchJSON(url) {
  const r = await fetch(url);
  return r.json();
}

function fmt(v, d=2) { return Number(v).toFixed(d); }
function pct(v) { return Number(v).toFixed(2) + '%'; }

function badge(text, cls) {
  return `<span class="badge badge-${cls}">${text}</span>`;
}

function render() {
  const now = new Date().toLocaleTimeString();
  $('lastUpdated').textContent = 'Last updated: ' + now;

  // ── Portfolio ────────────────────────────────────
  fetchJSON('/api/portfolio').then(d => {
    const grid = $('portfolioGrid');
    const items = [
      ['Cash', '$' + fmt(d.cash), ''],
      ['Equity', '$' + fmt(d.equity), ''],
      ['PnL', (d.pnl >= 0 ? '+' : '') + '$' + fmt(d.pnl), d.pnl >= 0 ? 'positive' : 'negative'],
      ['ROI', (d.roi >= 0 ? '+' : '') + pct(d.roi), d.roi >= 0 ? 'positive' : 'negative'],
      ['Open', d.open_positions, ''],
      ['Invested', '$' + fmt(d.total_invested), ''],
    ];
    grid.innerHTML = items.map(([label, val, cls]) =>
      `<div class="stat-row"><span class="stat-label">${label}</span><span class="stat-value ${cls}">${val}</span></div>`
    ).join('');
  });

  // ── Health ───────────────────────────────────────
  fetchJSON('/api/health').then(d => {
    const tables = ['markets','market_prices','ai_analysis','market_features',
                    'signals','order_books','news_items','news_market_matches',
                    'paper_positions','paper_orders'];
    const html = '<table>' +
      tables.map(t => `<tr><th>${t}</th><td>${d[t]||0}</td></tr>`).join('') +
      '</table>';
    $('healthTable').innerHTML = html;
  });

  // ── Performance ──────────────────────────────────
  fetchJSON('/api/performance').then(orders => {
    let html = '<table><tr><th>Market</th><th>Side</th><th>Price</th><th>Amount</th><th>Reason</th></tr>';
    orders.slice(0, 10).forEach(o => {
      const side = o.side === 'BUY' ? badge('BUY','buy') : badge('SELL','high');
      html += `<tr><td class="text-truncate">${o.market_id}</td><td>${side}</td>
        <td>$${fmt(o.price,4)}</td><td>$${fmt(o.amount)}</td>
        <td class="text-truncate">${o.reason||'—'}</td></tr>`;
    });
    html += '</table>';
    $('perfTable').innerHTML = html;
  });

  // ── Positions ────────────────────────────────────
  fetchJSON('/api/positions').then(rows => {
    if (!rows.length) { $('positionsTable').innerHTML = '<p>No open positions.</p>'; return; }
    let html = '<table><tr><th>Market</th><th>Question</th><th>Entry</th><th>Last</th><th>uPnL</th><th>uROI</th><th>Action</th><th>Conf</th><th>Risk</th></tr>';
    rows.forEach(r => {
      const pnlCls = r.unrealized_pnl > 0 ? 'positive' : r.unrealized_pnl < 0 ? 'negative' : '';
      const actBadge = badge(r.ai_action, r.ai_action.toLowerCase());
      const riskBadge = badge(r.risk_level, r.risk_level.toLowerCase());
      html += `<tr><td>${r.market_id}</td><td class="text-truncate">${r.question}</td>
        <td>$${r.entry_price}</td><td>$${r.latest_price}</td>
        <td class="${pnlCls}">${r.unrealized_pnl >= 0 ? '+' : ''}$${r.unrealized_pnl}</td>
        <td class="${pnlCls}">${r.unrealized_roi >= 0 ? '+' : ''}${pct(r.unrealized_roi)}</td>
        <td>${actBadge}</td><td>${r.ai_confidence}</td><td>${riskBadge}</td></tr>`;
    });
    html += '</table>';
    $('positionsTable').innerHTML = html;
  });

  // ── AI Decisions ─────────────────────────────────
  fetchJSON('/api/ai-decisions').then(rows => {
    if (!rows.length) { $('aiTable').innerHTML = '<p>No AI decisions yet.</p>'; return; }
    let html = '<table><tr><th>Market</th><th>Question</th><th>Action</th><th>Prob</th><th>Conf</th><th>Risk</th><th>Reason</th></tr>';
    rows.slice(0, 10).forEach(r => {
      const actBadge = badge(r.ai_action, (r.ai_action||'skip').toLowerCase());
      const riskBadge = badge(r.risk_level, (r.risk_level||'medium').toLowerCase());
      html += `<tr><td>${r.market_id}</td><td class="text-truncate">${r.question||'—'}</td>
        <td>${actBadge}</td><td>${fmt(r.ai_probability,0)}</td><td>${fmt(r.confidence,0)}</td>
        <td>${riskBadge}</td><td class="text-truncate">${r.reason||'—'}</td></tr>`;
    });
    html += '</table>';
    $('aiTable').innerHTML = html;
  });

  // ── Ranked Markets ───────────────────────────────
  fetchJSON('/api/ranked-markets').then(rows => {
    if (!rows.length) { $('rankedTable').innerHTML = '<p>No ranked markets.</p>'; return; }
    let html = '<table><tr><th>Market</th><th>Question</th><th>Price</th><th>Signal</th><th>Sig20</th><th>News</th><th>Imbal</th><th>Vol</th></tr>';
    rows.slice(0, 10).forEach(r => {
      html += `<tr><td>${r.market_id}</td><td class="text-truncate">${r.question||'—'}</td>
        <td>${fmt(r.yes_price,4)}</td><td>${fmt(r.signal_score,0)}</td>
        <td>${fmt(r.sig20,0)}</td><td>${fmt(r.news_score,0)}</td>
        <td>${fmt(r.imbalance,4)}</td><td>${fmt(r.volatility,4)}</td></tr>`;
    });
    html += '</table>';
    $('rankedTable').innerHTML = html;
  });

  // ── News Matches ─────────────────────────────────
  fetchJSON('/api/news-matches').then(rows => {
    if (!rows.length) { $('newsTable').innerHTML = '<p>No news matches yet.</p>'; return; }
    let html = '<table><tr><th>Market</th><th>Question</th><th>Score</th><th>Keywords</th></tr>';
    rows.slice(0, 10).forEach(r => {
      html += `<tr><td>${r.market_id}</td><td class="text-truncate">${r.question||'—'}</td>
        <td>${fmt(r.score,0)}</td><td class="text-truncate">${r.keywords||'—'}</td></tr>`;
    });
    html += '</table>';
    $('newsTable').innerHTML = html;
  });
}

render();
setInterval(render, REFRESH_MS);
</script>
</body>
</html>
"""


def main():
    import uvicorn
    print("▶️ Starting Dashboard on http://0.0.0.0:8080")
    uvicorn.run(app, host="0.0.0.0", port=8080, log_level="info")


if __name__ == "__main__":
    main()
