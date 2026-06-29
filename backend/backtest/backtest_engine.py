import psycopg2
from backend.utils.config import DB_CONFIG

START_CASH = 10000
TRADE_AMOUNT = 100
TAKE_PROFIT = 0.20
STOP_LOSS = -0.08

MIN_SIGNAL_SCORE = 20
MIN_NEWS_SCORE = 20
MIN_PRICE = 0.05
MAX_PRICE = 0.95


def f(v):
    return float(v or 0)


def run(limit=100):
    conn = psycopg2.connect(**DB_CONFIG)
    cur = conn.cursor()

    print("▶️ Running Backtest Engine V2...")

    cur.execute("""
        SELECT DISTINCT ON (mf.market_id)
            mf.market_id,
            m.question,
            (mf.feature_json->>'latest_yes_price')::numeric AS yes_price,
            (mf.feature_json->>'signal_score')::numeric AS signal_score,
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

    candidates = []
    for market_id, question, yes_price, signal_score, news_score, imbalance in rows:
        yes_price = f(yes_price)
        signal_score = f(signal_score)
        news_score = f(news_score)
        imbalance = f(imbalance)

        if yes_price <= MIN_PRICE or yes_price >= MAX_PRICE:
            continue

        if signal_score < MIN_SIGNAL_SCORE and news_score < MIN_NEWS_SCORE:
            continue

        candidates.append((market_id, question, yes_price, signal_score, news_score, imbalance))

    candidates = candidates[:limit]

    cash = START_CASH
    wins = 0
    losses = 0
    flats = 0
    trades = []

    for market_id, question, yes_price, signal_score, news_score, imbalance in candidates:
        cur.execute("""
            SELECT yes_price, created_at
            FROM market_prices
            WHERE market_id = %s
            ORDER BY created_at ASC
        """, (market_id,))

        prices = cur.fetchall()
        if len(prices) < 3:
            continue

        entry_price = f(prices[0][0])
        if entry_price <= MIN_PRICE or entry_price >= MAX_PRICE:
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
        })

    total = len(trades)
    roi = ((cash - START_CASH) / START_CASH) * 100
    win_rate = (wins / total * 100) if total else 0
    avg_pnl = (sum(t["pnl"] for t in trades) / total) if total else 0

    best = sorted(trades, key=lambda x: x["pnl"], reverse=True)[:5]
    worst = sorted(trades, key=lambda x: x["pnl"])[:5]

    print("\n===== BACKTEST V2 RESULT =====")
    print(f"Candidates after filter: {len(candidates)}")
    print(f"Trades tested: {total}")
    print(f"Wins: {wins}")
    print(f"Losses: {losses}")
    print(f"Flat: {flats}")
    print(f"Win rate: {win_rate:.2f}%")
    print(f"Average PnL per trade: {avg_pnl:.2f}")
    print(f"Final cash: {cash:.2f}")
    print(f"ROI: {roi:.2f}%")

    print("\n===== BEST TRADES =====")
    for t in best:
        print(t["market_id"], "| pnl:", round(t["pnl"], 2), "| signal:", t["signal_score"], "| news:", t["news_score"], "|", t["question"][:80])

    print("\n===== WORST TRADES =====")
    for t in worst:
        print(t["market_id"], "| pnl:", round(t["pnl"], 2), "| signal:", t["signal_score"], "| news:", t["news_score"], "|", t["question"][:80])

    cur.close()
    conn.close()


if __name__ == "__main__":
    run()
