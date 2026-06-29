import re
import traceback
import psycopg2
from backend.utils.config import DB_CONFIG


def normalize(text):
    return (text or "").lower()


def run(limit_news=50, limit_markets=500):
    try:
        print("▶️ Running News-Market Match Job V2...")

        conn = psycopg2.connect(**DB_CONFIG)
        cur = conn.cursor()

        cur.execute("""
            SELECT id, title, summary
            FROM news_items
            ORDER BY id DESC
            LIMIT %s
        """, (limit_news,))
        news = cur.fetchall()

        cur.execute("""
            SELECT mk.market_id, mk.keyword, mk.weight
            FROM market_keywords mk
            JOIN markets m ON m.market_id = mk.market_id
            WHERE m.active = true AND m.closed = false
            LIMIT %s
        """, (limit_markets * 10,))
        keyword_rows = cur.fetchall()

        market_keywords = {}
        for market_id, keyword, weight in keyword_rows:
            market_keywords.setdefault(market_id, []).append((keyword, float(weight or 1)))

        matches = []

        for news_id, title, summary in news:
            news_text = normalize(title + " " + (summary or ""))

            for market_id, kws in market_keywords.items():
                score = 0
                hit_words = []

                for keyword, weight in kws:
                    k = normalize(keyword)
                    if len(k) < 3:
                        continue
                    if re.search(rf"\b{re.escape(k)}\b", news_text):
                        score += 10 * weight
                        hit_words.append(k)

                # Require stronger evidence:
                # - at least 2 matched keywords, OR
                # - total score >= 20
                unique_hits = sorted(set(hit_words))
                if len(unique_hits) >= 2 or score >= 20:
                    matches.append((news_id, market_id, score, ",".join(unique_hits)))

        inserted = 0
        skipped = 0

        for news_id, market_id, score, keywords in matches:
            cur.execute("""
                INSERT INTO news_market_matches (news_id, market_id, score, keywords)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT (news_id, market_id) DO NOTHING
            """, (news_id, market_id, score, keywords))

            if cur.rowcount == 1:
                inserted += 1
            else:
                skipped += 1

        conn.commit()

        print(f"News checked: {len(news)}")
        print(f"Markets with keywords checked: {len(market_keywords)}")
        print(f"Matches found: {len(matches)}")
        print(f"Inserted: {inserted}")
        print(f"Skipped: {skipped}")

        for m in matches[:20]:
            print(f"news_id={m[0]} market_id={m[1]} score={m[2]} keywords={m[3]}")

        cur.close()
        conn.close()

        return {"matches": len(matches), "inserted": inserted, "skipped": skipped, "errors": 0}

    except Exception:
        print("❌ News-Market Match Job Failed")
        traceback.print_exc()
        return {"errors": 1}


if __name__ == "__main__":
    run()
