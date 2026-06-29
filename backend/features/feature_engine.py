import psycopg2
from psycopg2.extras import Json
from backend.utils.config import DB_CONFIG


def n(v):
    if v is None:
        return 0.0
    return float(v)


def build_features(market_id):
    conn = psycopg2.connect(**DB_CONFIG)
    cur = conn.cursor()

    cur.execute("""
        SELECT volume, liquidity
        FROM markets
        WHERE market_id = %s
    """, (market_id,))
    market = cur.fetchone()

    cur.execute("""
        SELECT yes_price, no_price, spread
        FROM market_prices
        WHERE market_id = %s
        ORDER BY created_at DESC
        LIMIT 30
    """, (market_id,))
    prices = cur.fetchall()

    cur.execute("""
        SELECT signal, score
        FROM signals
        WHERE market_id = %s
        ORDER BY created_at DESC
        LIMIT 20
    """, (market_id,))
    signals = cur.fetchall()

    cur.execute("""
        SELECT COUNT(*), COALESCE(SUM(score), 0)
        FROM news_market_matches
        WHERE market_id = %s
    """, (market_id,))
    news = cur.fetchone()

    cur.execute("""
        SELECT side, price, size
        FROM order_books
        WHERE market_id = %s
        ORDER BY created_at DESC
        LIMIT 100
    """, (market_id,))
    ob = cur.fetchall()

    cur.close()
    conn.close()

    yes_prices = [n(p[0]) for p in prices if p[0] is not None]
    latest_yes = yes_prices[0] if yes_prices else 0.0
    oldest_yes = yes_prices[-1] if yes_prices else latest_yes
    price_change = latest_yes - oldest_yes

    bid_size = sum(n(x[2]) for x in ob if x[0] == "bid")
    ask_size = sum(n(x[2]) for x in ob if x[0] == "ask")
    total_depth = bid_size + ask_size
    imbalance = (bid_size - ask_size) / total_depth if total_depth else 0.0

    signal_score = sum(n(s[1]) for s in signals)
    news_count = int(news[0] or 0)
    news_score = n(news[1])

    return {
        "market_id": market_id,
        "volume": n(market[0]) if market else 0.0,
        "liquidity": n(market[1]) if market else 0.0,
        "latest_yes_price": latest_yes,
        "price_change_last_30_snapshots": price_change,
        "signal_score": signal_score,
        "news_count": news_count,
        "news_score": news_score,
        "bid_size": bid_size,
        "ask_size": ask_size,
        "orderbook_imbalance": imbalance,
    }


def save_features(features):
    conn = psycopg2.connect(**DB_CONFIG)
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO market_features (market_id, feature_json)
        VALUES (%s, %s)
    """, (features["market_id"], Json(features)))
    conn.commit()
    cur.close()
    conn.close()


def run(limit=10):
    conn = psycopg2.connect(**DB_CONFIG)
    cur = conn.cursor()

    cur.execute("""
        SELECT m.market_id
        FROM markets m
        JOIN LATERAL (
            SELECT yes_price
            FROM market_prices mp
            WHERE mp.market_id = m.market_id
            ORDER BY mp.created_at DESC
            LIMIT 1
        ) p ON true
        WHERE m.active = true
          AND m.closed = false
          AND COALESCE(m.liquidity, 0) > 1000
          AND COALESCE(m.volume, 0) > 10000
          AND p.yes_price > 0.05
          AND p.yes_price < 0.95
        ORDER BY m.volume DESC
        LIMIT %s
    """, (limit,))

    market_ids = [r[0] for r in cur.fetchall()]
    cur.close()
    conn.close()

    for market_id in market_ids:
        features = build_features(market_id)
        save_features(features)
        print(features)


if __name__ == "__main__":
    run()
