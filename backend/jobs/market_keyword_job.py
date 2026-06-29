import re
import traceback
import psycopg2
from backend.utils.config import DB_CONFIG

STOPWORDS = {
    "will", "the", "a", "an", "by", "before", "after", "in", "on", "of",
    "to", "for", "and", "or", "with", "be", "is", "are", "win", "hit",
    "end", "new", "market", "yes", "no", "have", "has", "had", "top",
    "january", "february", "march", "april", "may", "june", "july",
    "august", "september", "october", "november", "december",
    "jan", "feb", "mar", "apr", "jun", "jul", "aug", "sep", "oct", "nov", "dec",
    "2024", "2025", "2026", "2027", "2028", "2029", "2030",
    "before", "after", "during", "over", "under", "above", "below",
    "more", "less", "than", "between", "from", "into", "out", "one", "first", "day", "days", "week", "weeks", "month", "months", "year", "years", "next", "last", "any", "all", "this", "that", "which", "what", "who", "when", "where", "why", "how", "world", "cup", "fifa", "race", "model", "time", "times", "its", "cut", "cuts", "rate", "rates", "change", "changes", "make", "made", "get", "gets", "still", "also", "about", "against", "again"
}

def extract_keywords(question):
    words = re.findall(r"[A-Za-z0-9]+", question or "")
    keywords = []

    for w in words:
        wl = w.lower()
        if len(wl) < 3:
            continue
        if wl in STOPWORDS:
            continue
        keywords.append(wl)

    return list(dict.fromkeys(keywords))

def run(limit=500):
    try:
        print("▶️ Running Market Keyword Job...")

        conn = psycopg2.connect(**DB_CONFIG)
        cur = conn.cursor()

        cur.execute("""
            SELECT market_id, question
            FROM markets
            WHERE active = true AND closed = false
            LIMIT %s
        """, (limit,))

        rows = cur.fetchall()

        inserted = 0
        skipped = 0

        for market_id, question in rows:
            keywords = extract_keywords(question)

            for kw in keywords:
                weight = 2 if kw[0].isupper() else 1

                cur.execute("""
                    INSERT INTO market_keywords (market_id, keyword, weight)
                    VALUES (%s, %s, %s)
                    ON CONFLICT (market_id, keyword) DO NOTHING
                """, (market_id, kw, weight))

                if cur.rowcount == 1:
                    inserted += 1
                else:
                    skipped += 1

        conn.commit()
        cur.close()
        conn.close()

        print("✅ Market Keyword Job Finished")
        print(f"Markets checked: {len(rows)}")
        print(f"Inserted: {inserted}")
        print(f"Skipped: {skipped}")

        return {"inserted": inserted, "skipped": skipped, "errors": 0}

    except Exception:
        print("❌ Market Keyword Job Failed")
        traceback.print_exc()
        return {"errors": 1}

if __name__ == "__main__":
    run()
