import traceback
import psycopg2
from psycopg2.extras import Json
from backend.utils.config import DB_CONFIG


def run(limit=50):
    try:
        print("▶️ Running News Signal Job...")

        conn = psycopg2.connect(**DB_CONFIG)
        cur = conn.cursor()

        cur.execute("""
            SELECT
                nmm.market_id,
                COUNT(*) AS match_count,
                SUM(nmm.score) AS news_score,
                STRING_AGG(DISTINCT nmm.keywords, ',') AS keywords
            FROM news_market_matches nmm
            GROUP BY nmm.market_id
            ORDER BY news_score DESC
            LIMIT %s
        """, (limit,))

        rows = cur.fetchall()

        inserted = 0

        for market_id, match_count, news_score, keywords in rows:
            score = min(float(news_score or 0), 100)

            if score >= 60:
                signal = "WATCH"
                reason = f"High news activity: {match_count} matched news items. Keywords: {keywords}"
            elif score >= 30:
                signal = "WATCH"
                reason = f"Moderate news activity: {match_count} matched news items. Keywords: {keywords}"
            else:
                signal = "WATCH"
                reason = f"Low news activity: {match_count} matched news items. Keywords: {keywords}"

            cur.execute("""
                INSERT INTO signals (market_id, signal, score, reason, raw, created_at)
                VALUES (%s, %s, %s, %s, %s, CURRENT_TIMESTAMP)
            """, (
                market_id,
                signal,
                score,
                reason,
                Json({
                    "type": "news_signal",
                    "match_count": int(match_count),
                    "news_score": score,
                    "keywords": keywords
                })
            ))

            inserted += 1

        conn.commit()
        cur.close()
        conn.close()

        print("✅ News Signal Job Finished")
        print(f"Signals inserted: {inserted}")

        return {"inserted": inserted, "errors": 0}

    except Exception:
        print("❌ News Signal Job Failed")
        traceback.print_exc()
        return {"errors": 1}


if __name__ == "__main__":
    run()
