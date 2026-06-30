import psycopg2
from backend.utils.config import DB_CONFIG
from backend.ranking.candidate_ranker import run as rank_candidates

START_CASH = 10000
TRADE_AMOUNT = 100
TAKE_PROFIT = 0.20
STOP_LOSS = -0.08

MIN_SIGNAL_SCORE = 20
MIN_NEWS_SCORE = 20
MIN_PRICE = 0.05
MAX_PRICE = 0.95
MIN_PRICE_SNAPSHOTS = 3


def f(v):
    return float(v or 0)


def simulate_trades(qualifying, cur, label="V3"):
    """Shared trade simulation logic. Returns (trades, stats_dict)."""
    cash = START_CASH
    wins = 0
    losses = 0
    flats = 0
    trades = []
    skipped_not_enough_prices = 0
    skipped_entry_price = 0
    total_candidates = len(qualifying)

    for item in qualifying:
        market_id = item["market_id"]
        question = item["question"]
        yes_price = item["yes_price"]
        signal_score = item.get("signal_score", 0)
        news_score = item.get("news_score", 0)
        imbalance = item.get("imbalance", 0)
        rank_reason = item.get("rank_reason", "")

        cur.execute("""
            SELECT yes_price, created_at
            FROM market_prices
            WHERE market_id = %s
            ORDER BY created_at ASC
        """, (market_id,))

        prices = cur.fetchall()

        if len(prices) < MIN_PRICE_SNAPSHOTS:
            skipped_not_enough_prices += 1
            continue

        entry_price = f(prices[0][0])
        if entry_price <= MIN_PRICE or entry_price >= MAX_PRICE:
            skipped_entry_price += 1
            continue

        qty = TRADE_AMOUNT / entry_price
        exit_price = f(prices[-1][0])
        exit_reason = "END"

        for price, created_at in prices[1:]:
            price = f(price)
            pnl_pct = (price - entry_price) / entry_price

            if pnl_pct >= TAKE_PROFIT:
                exit_price = price
                exit_reason = "TAKE_PROFIT"
                break

            if pnl_pct <= STOP_LOSS:
                exit_price = price
                exit_reason = "STOP_LOSS"
                break

        pnl = (exit_price * qty) - TRADE_AMOUNT
        cash += pnl

        if pnl > 0:
            wins += 1
        elif pnl < 0:
            losses += 1
        else:
            flats += 1

        trades.append({
            "market_id": market_id,
            "question": question,
            "entry": entry_price,
            "exit": exit_price,
            "pnl": pnl,
            "reason": exit_reason,
            "signal_score": signal_score,
            "news_score": news_score,
            "imbalance": imbalance,
            "rank_reason": rank_reason,
        })

    total = len(trades)
    roi = ((cash - START_CASH) / START_CASH) * 100
    win_rate = (wins / total * 100) if total else 0
    avg_pnl = (sum(t["pnl"] for t in trades) / total) if total else 0

    stats = {
        "label": label,
        "candidates": total_candidates,
        "trades_tested": total,
        "wins": wins,
        "losses": losses,
        "flat": flats,
        "win_rate": win_rate,
        "avg_pnl": avg_pnl,
        "roi": roi,
        "cash": cash,
        "skipped_not_enough_prices": skipped_not_enough_prices,
        "skipped_entry_price": skipped_entry_price,
    }

    return trades, stats


def print_backtest_result(trades, stats, extra_skip=None):
    """Pretty-print backtest results."""
    print(f"\n===== BACKTEST {stats['label']} RESULT =====")
    print(f"Candidates:                            {stats['candidates']}")
    if extra_skip:
        for k, v in extra_skip.items():
            print(f"  └─ Skipped ({k}):  {v}")
    print(f"  └─ Skipped (<{MIN_PRICE_SNAPSHOTS} price snapshots):     {stats['skipped_not_enough_prices']}")
    print(f"  └─ Skipped (entry price out of range): {stats['skipped_entry_price']}")
    print(f"Trades tested:                           {stats['trades_tested']}")
    print(f"Wins:  {stats['wins']}")
    print(f"Losses:{stats['losses']}")
    print(f"Flat:  {stats['flat']}")
    print(f"Win rate:           {stats['win_rate']:.2f}%")
    print(f"Average PnL/trade:  {stats['avg_pnl']:.2f}")
    print(f"Final cash:         {stats['cash']:.2f}")
    print(f"ROI:                {stats['roi']:.2f}%")

    best = sorted(trades, key=lambda x: x["pnl"], reverse=True)[:5]
    worst = sorted(trades, key=lambda x: x["pnl"])[:5]

    if best:
        print("\n===== BEST TRADES =====")
        for t in best:
            r = f" [{t['rank_reason']}]" if t.get("rank_reason") else ""
            print(t["market_id"], "| pnl:", round(t["pnl"], 2),
                  "| signal:", t["signal_score"], "| news:", t["news_score"],
                  "|", t["question"][:80], r)

    if worst:
        print("\n===== WORST TRADES =====")
        for t in worst:
            r = f" [{t['rank_reason']}]" if t.get("rank_reason") else ""
            print(t["market_id"], "| pnl:", round(t["pnl"], 2),
                  "| signal:", t["signal_score"], "| news:", t["news_score"],
                  "|", t["question"][:80], r)


def run(limit=100):
    """Run Backtest V3 (SQL-based filtering) + V4 (Ranking-based)."""
    conn = psycopg2.connect(**DB_CONFIG)
    cur = conn.cursor()

    # ═══════════════════════════════════════════════════════════════════
    # V3:  Original SQL-based candidate selection
    # ═══════════════════════════════════════════════════════════════════
    print("▶️ Running Backtest Engine V3 (SQL filter)...")

    cur.execute("""
        SELECT DISTINCT ON (mf.market_id)
            mf.market_id,
            m.question,
            (mf.feature_json->>'latest_yes_price')::numeric AS yes_price,
            (mf.feature_json->>'latest_signal_score')::numeric AS signal_score,
            (mf.feature_json->>'news_score')::numeric AS news_score,
            (mf.feature_json->>'orderbook_imbalance')::numeric AS imbalance
        FROM market_features mf
        JOIN markets m ON m.market_id = mf.market_id
        WHERE m.active = true
          AND m.closed = false
          AND COALESCE(m.liquidity, 0) > 1000
          AND COALESCE(m.volume, 0) > 10000
        ORDER BY mf.market_id, mf.created_at DESC
    """)
    rows = cur.fetchall()

    candidates_v3 = 0
    skipped_price_range = 0
    skipped_low_score = 0
    qualifying_v3 = []

    for row in rows:
        market_id, question, yes_price, signal_score, news_score, imbalance = row
        yes_price = f(yes_price)
        signal_score = f(signal_score)
        news_score = f(news_score)
        imbalance = f(imbalance)

        if yes_price <= MIN_PRICE or yes_price >= MAX_PRICE:
            skipped_price_range += 1
            continue
        if signal_score < MIN_SIGNAL_SCORE and news_score < MIN_NEWS_SCORE:
            skipped_low_score += 1
            continue

        candidates_v3 += 1
        qualifying_v3.append({
            "market_id": market_id,
            "question": question,
            "yes_price": yes_price,
            "signal_score": signal_score,
            "news_score": news_score,
            "imbalance": imbalance,
        })

    qualifying_v3 = qualifying_v3[:limit]

    trades_v3, stats_v3 = simulate_trades(qualifying_v3, cur, label="V3")
    print_backtest_result(trades_v3, stats_v3, extra_skip={
        "price out of 0.05-0.95": skipped_price_range,
        f"signal<{MIN_SIGNAL_SCORE} AND news<{MIN_NEWS_SCORE}": skipped_low_score,
    })

    # ═══════════════════════════════════════════════════════════════════
    # V4:  Ranking-based candidate selection
    # ═══════════════════════════════════════════════════════════════════
    print("\n" + "=" * 60)
    print("▶️ Running Backtest Engine V4 (Ranking filter)...")

    ranked = rank_candidates(limit=20)

    qualifying_v4 = []
    for r in ranked:
        qualifying_v4.append({
            "market_id": r["market_id"],
            "question": r["question"],
            "yes_price": r["latest_yes_price"],
            "signal_score": r["latest_signal_score"],
            "news_score": r["news_score"],
            "imbalance": r["orderbook_imbalance"],
            "rank_reason": r["rank_reason"],
        })

    trades_v4, stats_v4 = simulate_trades(qualifying_v4, cur, label="V4")
    print_backtest_result(trades_v4, stats_v4)

    # ── Summary ──────────────────────────────────────────────────────
    print("\n" + "=" * 60)
    print("===== BACKTEST V3 vs V4 SUMMARY =====")
    print(f"{'Metric':<25} {'V3 (SQL)':>12} {'V4 (Ranking)':>14}")
    print("-" * 55)
    print(f"{'Candidates':<25} {stats_v3['candidates']:>12} {stats_v4['candidates']:>14}")
    print(f"{'Trades tested':<25} {stats_v3['trades_tested']:>12} {stats_v4['trades_tested']:>14}")
    print(f"{'Wins':<25} {stats_v3['wins']:>12} {stats_v4['wins']:>14}")
    print(f"{'Losses':<25} {stats_v3['losses']:>12} {stats_v4['losses']:>14}")
    print(f"{'Flat':<25} {stats_v3['flat']:>12} {stats_v4['flat']:>14}")
    print(f"{'Win rate':<25} {stats_v3['win_rate']:>11.2f}% {stats_v4['win_rate']:>13.2f}%")
    print(f"{'Avg PnL':<25} {stats_v3['avg_pnl']:>12.2f} {stats_v4['avg_pnl']:>14.2f}")
    print(f"{'ROI':<25} {stats_v3['roi']:>11.2f}% {stats_v4['roi']:>13.2f}%")

    cur.close()
    conn.close()


if __name__ == "__main__":
    run()
