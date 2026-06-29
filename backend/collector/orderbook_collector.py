import json
import requests
import psycopg2
from psycopg2.extras import Json
from backend.utils.config import DB_CONFIG

CLOB_URL = "https://clob.polymarket.com/book"


def fetch_order_book(token_id):
    """Fetch order book for a specific token ID from Polymarket CLOB API."""
    try:
        r = requests.get(CLOB_URL, params={"token_id": token_id}, timeout=10)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        print(f"Error fetching order book for token {token_id}: {e}")
        return None


def save_order_book(market_id, order_book):
    """Save order book data to database."""
    conn = psycopg2.connect(**DB_CONFIG)
    cur = conn.cursor()
    
    saved_count = 0
    
    # Save bids
    for bid in order_book.get("bids", []):
        cur.execute("""
            INSERT INTO order_books (
                market_id, token_id, side, price, size, raw, created_at
            )
            VALUES (%s, %s, %s, %s, %s, %s, CURRENT_TIMESTAMP)
        """, (
            market_id,
            order_book.get("asset_id"),
            "bid",
            float(bid.get("price", 0)),
            float(bid.get("size", 0)),
            Json(bid),
        ))
        saved_count += 1
    
    # Save asks
    for ask in order_book.get("asks", []):
        cur.execute("""
            INSERT INTO order_books (
                market_id, token_id, side, price, size, raw, created_at
            )
            VALUES (%s, %s, %s, %s, %s, %s, CURRENT_TIMESTAMP)
        """, (
            market_id,
            order_book.get("asset_id"),
            "ask",
            float(ask.get("price", 0)),
            float(ask.get("size", 0)),
            Json(ask),
        ))
        saved_count += 1
    
    conn.commit()
    cur.close()
    conn.close()
    
    return saved_count


def log(component, level, message, raw=None):
    """Log to system_logs table."""
    conn = psycopg2.connect(**DB_CONFIG)
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO system_logs (component, level, message, raw)
        VALUES (%s, %s, %s, %s)
        """,
        (component, level, message, Json(raw or {}))
    )
    conn.commit()
    cur.close()
    conn.close()


def collect_order_books_for_markets(markets, limit=5):
    """Collect order books for a limited number of markets."""
    markets_tested = 0
    order_books_saved = 0
    errors = 0
    
    for market in markets[:limit]:
        market_id = market.get("id")
        clob_token_ids = market.get("clobTokenIds")
        
        if not clob_token_ids:
            print(f"Market {market_id} has no clobTokenIds")
            continue
        
        # Parse token IDs from JSON string
        try:
            if isinstance(clob_token_ids, str):
                token_ids = json.loads(clob_token_ids)
            else:
                token_ids = clob_token_ids
        except Exception as e:
            print(f"Error parsing clobTokenIds for market {market_id}: {e}")
            errors += 1
            continue
        
        # Fetch order book for each token ID
        for token_id in token_ids:
            order_book = fetch_order_book(token_id)
            if order_book:
                saved = save_order_book(market_id, order_book)
                order_books_saved += saved
                print(f"Saved {saved} order book entries for market {market_id} token {token_id}")
            else:
                errors += 1
        
        markets_tested += 1
    
    # Log results
    stats = {
        "markets_tested": markets_tested,
        "order_books_saved": order_books_saved,
        "errors": errors,
    }
    log("orderbook_collector", "INFO", f"Order book collection completed", stats)
    
    return stats


def main():
    """Test order book collection with first 5 markets from database."""
    from backend.collector.polymarket_collector import fetch_markets
    
    print("Fetching markets...")
    markets = fetch_markets()
    
    print(f"\nTesting order book collection for first 5 markets...")
    stats = collect_order_books_for_markets(markets, limit=5)
    
    print(f"\nResults:")
    print(f"Markets tested: {stats['markets_tested']}")
    print(f"Order books saved: {stats['order_books_saved']}")
    print(f"Errors: {stats['errors']}")


if __name__ == "__main__":
    main()
