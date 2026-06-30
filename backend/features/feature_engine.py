import statistics
import psycopg2
from psycopg2.extras import Json
from backend.utils.config import DB_CONFIG


def n(v):
    """Convert value to float, defaulting to 0.0 if None."""
    if v is None:
        return 0.0
    return float(v)


def build_features(market_id):
    """Build a rich feature set for a single market.

    Returns a dict with all required feature fields. Every numeric
    value is converted to float before calculation/storage.
    """
    conn = psycopg2.connect(**DB_CONFIG)
    cur = conn.cursor()

    # ── 1. Market metadata ────────────────────────────────────────────
    cur.execute("""
        SELECT volume, liquidity, active, closed
        FROM markets
        WHERE market_id = %s
    """, (market_id,))
    market = cur.fetchone()

    volume = n(market[0]) if market else 0.0
    liquidity = n(market[1]) if market else 0.0
    is_active = bool(market[2]) if market else False
    is_closed = bool(market[3]) if market else False
    volume_liquidity_ratio = volume / liquidity if liquidity > 0 else 0.0

    # ── 2. Price data (last 30 snapshots) ─────────────────────────────
    cur.execute("""
        SELECT yes_price, no_price, spread
        FROM market_prices
        WHERE market_id = %s
        ORDER BY created_at DESC
        LIMIT 30
    """, (market_id,))
    prices = cur.fetchall()

    yes_prices = [n(p[0]) for p in prices]
    no_prices = [n(p[1]) for p in prices]
    spreads = [n(p[2]) for p in prices]

    latest_yes = yes_prices[0] if yes_prices else 0.0
    latest_no = no_prices[0] if no_prices else 0.0

    # Price changes (absolute)
    price_change_5 = yes_prices[0] - yes_prices[4] if len(yes_prices) >= 5 else 0.0
    price_change_10 = yes_prices[0] - yes_prices[9] if len(yes_prices) >= 10 else 0.0
    price_change_30 = yes_prices[0] - yes_prices[-1] if len(yes_prices) >= 2 else 0.0

    # Price return percentages
    price_return_pct_5 = (
        (yes_prices[0] - yes_prices[4]) / yes_prices[4] * 100
        if len(yes_prices) >= 5 and yes_prices[4] > 0 else 0.0
    )
    price_return_pct_10 = (
        (yes_prices[0] - yes_prices[9]) / yes_prices[9] * 100
        if len(yes_prices) >= 10 and yes_prices[9] > 0 else 0.0
    )
    price_return_pct_30 = (
        (yes_prices[0] - yes_prices[-1]) / yes_prices[-1] * 100
        if len(yes_prices) >= 2 and yes_prices[-1] > 0 else 0.0
    )

    # High, low, volatility over 30 snapshots
    high_30 = max(yes_prices) if yes_prices else 0.0
    low_30 = min(yes_prices) if yes_prices else 0.0
    volatility_30 = statistics.stdev(yes_prices) if len(yes_prices) >= 2 else 0.0

    # ── 3. Signal data (latest score + total over last 20) ────────────
    cur.execute("""
        SELECT score
        FROM signals
        WHERE market_id = %s
        ORDER BY created_at DESC
        LIMIT 20
    """, (market_id,))
    signals = cur.fetchall()

    signal_scores = [n(s[0]) for s in signals]
    latest_signal_score = signal_scores[0] if signal_scores else 0.0
    total_signal_score_20 = sum(signal_scores)
    has_signal = len(signal_scores) > 0

    # ── 4. News data ──────────────────────────────────────────────────
    cur.execute("""
        SELECT COUNT(*), COALESCE(SUM(score), 0), COALESCE(MAX(keywords), '')
        FROM news_market_matches
        WHERE market_id = %s
    """, (market_id,))
    news = cur.fetchone()
    news_count = int(news[0] or 0)
    news_score = n(news[1])
    matched_keywords = news[2] or ""
    has_news = news_count > 0

    # ── 5. Order book data (latest 200 rows ≈ latest snapshot) ────────
    cur.execute("""
        SELECT side, price, size
        FROM order_books
        WHERE market_id = %s
        ORDER BY created_at DESC
        LIMIT 200
    """, (market_id,))
    ob = cur.fetchall()

    bids = [x for x in ob if x[0] == "bid"]
    asks = [x for x in ob if x[0] == "ask"]

    bid_size = sum(n(x[2]) for x in bids)
    ask_size = sum(n(x[2]) for x in asks)
    total_depth = bid_size + ask_size
    orderbook_imbalance = (bid_size - ask_size) / total_depth if total_depth > 0 else 0.0

    best_bid = max(n(x[1]) for x in bids) if bids else 0.0
    best_ask = min(n(x[1]) for x in asks) if asks else 0.0
    spread = best_ask - best_bid if best_bid > 0 and best_ask > 0 else 0.0
    has_orderbook = len(ob) > 0

    cur.close()
    conn.close()

    return {
        "market_id": market_id,
        "latest_yes_price": latest_yes,
        "latest_no_price": latest_no,
        "price_change_5_snapshots": price_change_5,
        "price_change_10_snapshots": price_change_10,
        "price_change_30_snapshots": price_change_30,
        "price_return_pct_5": price_return_pct_5,
        "price_return_pct_10": price_return_pct_10,
        "price_return_pct_30": price_return_pct_30,
        "high_30_snapshots": high_30,
        "low_30_snapshots": low_30,
        "volatility_30_snapshots": volatility_30,
        "volume": volume,
        "liquidity": liquidity,
        "volume_liquidity_ratio": volume_liquidity_ratio,
        "bid_size": bid_size,
        "ask_size": ask_size,
        "total_depth": total_depth,
        "orderbook_imbalance": orderbook_imbalance,
        "spread": spread,
        "best_bid": best_bid,
        "best_ask": best_ask,
        "latest_signal_score": latest_signal_score,
        "total_signal_score_20": total_signal_score_20,
        "news_count": news_count,
        "news_score": news_score,
        "matched_keywords": matched_keywords,
        "is_active": is_active,
        "is_closed": is_closed,
        "has_orderbook": has_orderbook,
        "has_news": has_news,
        "has_signal": has_signal,
    }


def save_features(features):
    """Save feature dict to market_features.feature_json."""
    conn = psycopg2.connect(**DB_CONFIG)
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO market_features (market_id, feature_json)
        VALUES (%s, %s)
    """, (features["market_id"], Json(features)))
    conn.commit()
    cur.close()
    conn.close()


def run(limit=50):
    """Select qualifying markets, build features, save, and print one-line summary."""
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
          AND p.yes_price >= 0.03
          AND p.yes_price <= 0.97
        ORDER BY m.volume DESC, m.liquidity DESC
        LIMIT %s
    """, (limit,))

    market_ids = [r[0] for r in cur.fetchall()]
    cur.close()
    conn.close()

    count = 0
    for market_id in market_ids:
        features = build_features(market_id)
        save_features(features)
        count += 1
        print(
            f"{market_id} | "
            f"yes_price={features['latest_yes_price']:.4f} | "
            f"signal_score={features['latest_signal_score']:.1f} | "
            f"news_score={features['news_score']:.1f} | "
            f"imbalance={features['orderbook_imbalance']:.4f} | "
            f"volatility={features['volatility_30_snapshots']:.4f}"
        )

    print(f"\n✅ Feature V2 complete: {count} markets processed")


if __name__ == "__main__":
    run()
