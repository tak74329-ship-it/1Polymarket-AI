import json
import requests
import psycopg2
from psycopg2.extras import Json
from backend.utils.config import DB_CONFIG

URL = "https://gamma-api.polymarket.com/markets"

def parse_json_list(value):
    if not value:
        return []
    if isinstance(value, list):
        return value
    try:
        return json.loads(value)
    except Exception:
        return []

def fetch_markets():
    """Fetch all active markets with automatic pagination."""
    all_markets = []
    seen_ids = set()
    offset = 0
    limit = 100
    consecutive_duplicates = 0
    max_consecutive_duplicates = 3
    
    while True:
        try:
            r = requests.get(
                URL, 
                params={"limit": limit, "offset": offset, "active": "true", "closed": "false"}, 
                timeout=20
            )
            r.raise_for_status()
            batch = r.json()
        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 422:
                # Reached API query limit, stop pagination
                print(f"Offset {offset}: Reached API limit (422), stopping pagination")
                break
            else:
                raise
        
        if not batch:
            print(f"Offset {offset}: Empty response, stopping pagination")
            break
        
        # Deduplicate by market_id
        new_markets = []
        batch_new_count = 0
        for market in batch:
            market_id = str(market.get("id"))
            if market_id not in seen_ids:
                seen_ids.add(market_id)
                new_markets.append(market)
                batch_new_count += 1
        
        all_markets.extend(new_markets)
        
        # Print per-page stats
        print(f"Offset {offset}: Returned {len(batch)}, New {batch_new_count}, Total {len(all_markets)}")
        
        # Check for consecutive duplicates to avoid infinite loop
        if batch_new_count == 0:
            consecutive_duplicates += 1
            if consecutive_duplicates >= max_consecutive_duplicates:
                print(f"Offset {offset}: {max_consecutive_duplicates} consecutive pages with no new markets, stopping")
                break
        else:
            consecutive_duplicates = 0
        
        # If we got fewer markets than requested, we've reached the end
        if len(batch) < limit:
            print(f"Offset {offset}: Fewer results than limit ({len(batch)} < {limit}), reached end")
            break
        
        offset += limit
    
    print(f"Total markets fetched: {len(all_markets)}")
    return all_markets

def normalize_value(value):
    """Normalize value for comparison - convert to consistent types with 6 decimal precision."""
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return round(float(value), 6)
    if isinstance(value, str):
        try:
            return round(float(value), 6)
        except ValueError:
            return value
    return value

def save_markets(markets):
    """Save markets with change detection and return statistics."""
    conn = psycopg2.connect(**DB_CONFIG)
    cur = conn.cursor()
    
    total_fetched = len(markets)
    inserted_count = 0
    updated_count = 0
    skipped_count = 0
    price_snapshots_count = 0
    
    # Track field changes
    field_changes = {
        "question": 0,
        "slug": 0,
        "active": 0,
        "closed": 0,
        "volume": 0,
        "liquidity": 0,
        "outcomes": 0,
        "bestBid": 0,
        "bestAsk": 0,
        "lastTradePrice": 0,
    }
    
    for m in markets:
        market_id = str(m.get("id"))
        outcomes = parse_json_list(m.get("outcomes"))
        prices = parse_json_list(m.get("outcomePrices"))
        
        yes_price = float(prices[0]) if len(prices) > 0 else None
        no_price = float(prices[1]) if len(prices) > 1 else None
        spread = float(m.get("spread")) if m.get("spread") is not None else None
        
        # Check if market exists and compare key fields
        cur.execute("""
            SELECT question, slug, active, closed, volume, liquidity, outcomes, raw
            FROM markets WHERE market_id = %s
        """, (market_id,))
        
        existing = cur.fetchone()
        
        # Normalize new values for comparison
        new_question = m.get("question")
        new_slug = m.get("slug")
        new_active = m.get("active")
        new_closed = m.get("closed")
        new_volume = normalize_value(m.get("volumeNum") or m.get("volume"))
        new_liquidity = normalize_value(m.get("liquidityNum") or m.get("liquidity"))
        new_best_bid = normalize_value(m.get("bestBid"))
        new_best_ask = normalize_value(m.get("bestAsk"))
        new_last_trade_price = normalize_value(m.get("lastTradePrice"))
        
        # For storage, keep original values
        new_outcomes = Json(outcomes)
        new_raw = Json(m)
        
        if existing is None:
            # Insert new market
            cur.execute("""
                INSERT INTO markets (
                    market_id, question, slug, category, active, closed,
                    volume, liquidity, outcomes, raw, updated_at
                )
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,CURRENT_TIMESTAMP)
            """, (
                market_id,
                new_question,
                new_slug,
                m.get("category"),
                new_active,
                new_closed,
                m.get("volumeNum") or m.get("volume"),
                m.get("liquidityNum") or m.get("liquidity"),
                new_outcomes,
                new_raw,
            ))
            inserted_count += 1
        else:
            # Check if key fields changed
            (old_question, old_slug, old_active, old_closed, 
             old_volume, old_liquidity, old_outcomes, old_raw) = existing
            
            # Normalize old values for comparison
            old_volume_norm = normalize_value(old_volume)
            old_liquidity_norm = normalize_value(old_liquidity)
            
            # Extract old price fields from raw JSON and normalize
            old_best_bid_norm = normalize_value(old_raw.get("bestBid") if old_raw else None)
            old_best_ask_norm = normalize_value(old_raw.get("bestAsk") if old_raw else None)
            old_last_trade_price_norm = normalize_value(old_raw.get("lastTradePrice") if old_raw else None)
            
            # Compare outcomes as lists, not Json objects
            old_outcomes_list = parse_json_list(old_outcomes)
            
            # Track which fields changed
            changed_fields = []
            if old_question != new_question:
                changed_fields.append("question")
                field_changes["question"] += 1
            if old_slug != new_slug:
                changed_fields.append("slug")
                field_changes["slug"] += 1
            if old_active != new_active:
                changed_fields.append("active")
                field_changes["active"] += 1
            if old_closed != new_closed:
                changed_fields.append("closed")
                field_changes["closed"] += 1
            if old_volume_norm != new_volume:
                changed_fields.append("volume")
                field_changes["volume"] += 1
            if old_liquidity_norm != new_liquidity:
                changed_fields.append("liquidity")
                field_changes["liquidity"] += 1
            if old_outcomes_list != outcomes:
                changed_fields.append("outcomes")
                field_changes["outcomes"] += 1
            if old_best_bid_norm != new_best_bid:
                changed_fields.append("bestBid")
                field_changes["bestBid"] += 1
            if old_best_ask_norm != new_best_ask:
                changed_fields.append("bestAsk")
                field_changes["bestAsk"] += 1
            if old_last_trade_price_norm != new_last_trade_price:
                changed_fields.append("lastTradePrice")
                field_changes["lastTradePrice"] += 1
            
            key_fields_changed = len(changed_fields) > 0
            
            if key_fields_changed:
                cur.execute("""
                    UPDATE markets SET
                        question = %s,
                        slug = %s,
                        category = %s,
                        active = %s,
                        closed = %s,
                        volume = %s,
                        liquidity = %s,
                        outcomes = %s,
                        raw = %s,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE market_id = %s
                """, (
                    new_question,
                    new_slug,
                    m.get("category"),
                    new_active,
                    new_closed,
                    m.get("volumeNum") or m.get("volume"),
                    m.get("liquidityNum") or m.get("liquidity"),
                    new_outcomes,
                    new_raw,
                    market_id,
                ))
                updated_count += 1
            else:
                skipped_count += 1
        
        # Always insert price snapshot
        cur.execute("""
            INSERT INTO market_prices (
                market_id, yes_price, no_price, spread, raw
            )
            VALUES (%s,%s,%s,%s,%s)
        """, (
            market_id,
            yes_price,
            no_price,
            spread,
            Json({"outcomePrices": prices, "bestBid": m.get("bestBid"), "bestAsk": m.get("bestAsk")}),
        ))
        price_snapshots_count += 1
    
    conn.commit()
    cur.close()
    conn.close()
    
    # Print field change statistics
    print("\nField Changes:")
    for field, count in field_changes.items():
        if count > 0:
            print(f"  {field:15} {count}")
    
    return {
        "total_fetched": total_fetched,
        "inserted_count": inserted_count,
        "updated_count": updated_count,
        "skipped_count": skipped_count,
        "price_snapshots_count": price_snapshots_count,
        "field_changes": field_changes,
    }

def main():
    markets = fetch_markets(limit=20)
    save_markets(markets)
    print(f"✅ 已保存 {len(markets)} 个市场")
    print("✅ 已写入 markets 和 market_prices")

if __name__ == "__main__":
    main()
