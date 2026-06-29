import traceback
import feedparser
import psycopg2
from psycopg2.extras import Json
from backend.utils.config import DB_CONFIG

RSS_FEEDS = [
    "https://www.reutersagency.com/feed/?best-topics=political-general&post_type=best",
    "https://feeds.bbci.co.uk/news/world/rss.xml",
    "https://www.aljazeera.com/xml/rss/all.xml",
    "https://cointelegraph.com/rss",
]

def save_news(items):
    conn = psycopg2.connect(**DB_CONFIG)
    cur = conn.cursor()

    inserted = 0
    skipped = 0

    for item in items:
        cur.execute("""
            INSERT INTO news_items (source, title, url, summary, published_at, raw)
            VALUES (%s, %s, %s, %s, NULL, %s)
            ON CONFLICT (url) DO NOTHING
        """, (
            item["source"],
            item["title"],
            item["url"],
            item["summary"],
            Json(item["raw"])
        ))

        if cur.rowcount == 1:
            inserted += 1
        else:
            skipped += 1

    conn.commit()
    cur.close()
    conn.close()

    return inserted, skipped

def run(limit_per_feed=20):
    try:
        print("▶️ Running News Job...")

        items = []

        for feed_url in RSS_FEEDS:
            feed = feedparser.parse(feed_url)
            source = feed.feed.get("title", feed_url)

            for entry in feed.entries[:limit_per_feed]:
                items.append({
                    "source": source,
                    "title": entry.get("title", ""),
                    "url": entry.get("link", ""),
                    "summary": entry.get("summary", ""),
                    "raw": dict(entry),
                })

        inserted, skipped = save_news(items)

        print("✅ News Job Finished")
        print(f"Fetched: {len(items)}")
        print(f"Inserted: {inserted}")
        print(f"Skipped: {skipped}")

        return {"fetched": len(items), "inserted": inserted, "skipped": skipped, "errors": 0}

    except Exception:
        print("❌ News Job Failed")
        traceback.print_exc()
        return {"errors": 1}

if __name__ == "__main__":
    run()
