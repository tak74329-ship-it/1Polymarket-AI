import psycopg2
from backend.utils.config import DB_CONFIG


def get_market_context(market_id: str):
    conn = psycopg2.connect(**DB_CONFIG)
    cur = conn.cursor()

    cur.execute("""
        SELECT market_id, question, volume, liquidity, active, closed
        FROM markets
        WHERE market_id = %s
        LIMIT 1
    """, (market_id,))
    market = cur.fetchone()

    cur.execute("""
        SELECT yes_price, no_price, spread, created_at
        FROM market_prices
        WHERE market_id = %s
        ORDER BY created_at DESC
        LIMIT 5
    """, (market_id,))
    prices = cur.fetchall()

    cur.execute("""
        SELECT signal, score, reason, created_at
        FROM signals
        WHERE market_id = %s
        ORDER BY created_at DESC
        LIMIT 10
    """, (market_id,))
    signals = cur.fetchall()

    cur.execute("""
        SELECT n.title, n.source, nmm.score, nmm.keywords
        FROM news_market_matches nmm
        JOIN news_items n ON n.id = nmm.news_id
        WHERE nmm.market_id = %s
        ORDER BY nmm.created_at DESC
        LIMIT 10
    """, (market_id,))
    news = cur.fetchall()

    cur.close()
    conn.close()

    if not market:
        return None

    return {
        "market": {
            "market_id": market[0],
            "question": market[1],
            "volume": float(market[2] or 0),
            "liquidity": float(market[3] or 0),
            "active": market[4],
            "closed": market[5],
        },
        "prices": [
            {
                "yes_price": float(p[0] or 0),
                "no_price": float(p[1] or 0),
                "spread": float(p[2] or 0),
                "created_at": str(p[3]),
            }
            for p in prices
        ],
        "signals": [
            {
                "signal": s[0],
                "score": float(s[1] or 0),
                "reason": s[2],
                "created_at": str(s[3]),
            }
            for s in signals
        ],
        "news": [
            {
                "title": n[0],
                "source": n[1],
                "score": float(n[2] or 0),
                "keywords": n[3],
            }
            for n in news
        ],
    }
