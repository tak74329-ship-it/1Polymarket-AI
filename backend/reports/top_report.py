import psycopg2
from backend.utils.config import DB_CONFIG


def print_rows(title, rows):
    print(f"\n===== {title} =====")
    for r in rows:
        print(r)


def run():
    conn = psycopg2.connect(**DB_CONFIG)
    cur = conn.cursor()

    cur.execute("""
        SELECT DISTINCT ON (a.market_id)
            a.market_id, m.question, a.ai_probability, a.confidence, a.created_at
        FROM ai_analysis a
        LEFT JOIN markets m ON m.market_id = a.market_id
        ORDER BY a.market_id, a.created_at DESC
    """)
    ai_rows = cur.fetchall()
    ai_rows = sorted(ai_rows, key=lambda x: float(x[3] or 0), reverse=True)[:10]
    print_rows("TOP AI - latest per market", ai_rows)

    cur.execute("""
        SELECT DISTINCT ON (s.market_id)
            s.market_id, m.question, s.signal, s.score, s.reason, s.created_at
        FROM signals s
        LEFT JOIN markets m ON m.market_id = s.market_id
        ORDER BY s.market_id, s.created_at DESC
    """)
    signal_rows = cur.fetchall()
    signal_rows = sorted(signal_rows, key=lambda x: float(x[3] or 0), reverse=True)[:10]
    print_rows("TOP SIGNALS - latest per market", signal_rows)

    cur.execute("""
        SELECT DISTINCT ON (mf.market_id)
            mf.market_id,
            m.question,
            mf.feature_json->>'latest_yes_price' AS yes_price,
            mf.feature_json->>'latest_signal_score' AS signal_score,
            mf.feature_json->>'news_score' AS news_score,
            mf.feature_json->>'orderbook_imbalance' AS imbalance,
            mf.created_at
        FROM market_features mf
        LEFT JOIN markets m ON m.market_id = mf.market_id
        ORDER BY mf.market_id, mf.created_at DESC
    """)
    feature_rows = cur.fetchall()
    feature_rows = sorted(
        feature_rows,
        key=lambda x: float(x[3] or 0) + float(x[4] or 0),
        reverse=True
    )[:10]
    print_rows("TOP FEATURES - signal_score + news_score", feature_rows)

    cur.execute("""
        SELECT
            nmm.market_id,
            m.question,
            COUNT(*) AS match_count,
            SUM(nmm.score) AS total_news_score,
            STRING_AGG(DISTINCT nmm.keywords, ',') AS keywords
        FROM news_market_matches nmm
        LEFT JOIN markets m ON m.market_id = nmm.market_id
        GROUP BY nmm.market_id, m.question
        ORDER BY total_news_score DESC
        LIMIT 10
    """)
    news_rows = cur.fetchall()
    print_rows("TOP NEWS MATCHES", news_rows)

    cur.close()
    conn.close()


if __name__ == "__main__":
    run()
