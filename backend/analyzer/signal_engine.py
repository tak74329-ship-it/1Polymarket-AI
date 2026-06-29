import psycopg2
from psycopg2.extras import Json
from backend.utils.config import DB_CONFIG
import statistics
from datetime import datetime, timedelta


def normalize_number(v):
    """Normalize value to float for consistent numeric operations."""
    if v is None:
        return 0.0
    return float(v)


class SignalEngine:
    """Rule-based signal engine for trading signals."""
    
    def __init__(self):
        self.db_config = DB_CONFIG
    
    def get_historical_prices(self, market_id, hours=24):
        """Get historical price data for a market."""
        conn = psycopg2.connect(**self.db_config)
        cur = conn.cursor()
        
        cutoff_time = datetime.now() - timedelta(hours=hours)
        
        cur.execute("""
            SELECT yes_price, no_price, created_at
            FROM market_prices
            WHERE market_id = %s AND created_at >= %s
            ORDER BY created_at ASC
        """, (market_id, cutoff_time))
        
        results = cur.fetchall()
        cur.close()
        conn.close()
        
        return [{"yes_price": normalize_number(r[0]), "no_price": normalize_number(r[1]), "created_at": r[2]} for r in results]
    
    def get_order_book_snapshot(self, market_id):
        """Get latest order book snapshot for a market."""
        conn = psycopg2.connect(**self.db_config)
        cur = conn.cursor()
        
        cur.execute("""
            SELECT side, price, size, created_at
            FROM order_books
            WHERE market_id = %s
            ORDER BY created_at DESC
            LIMIT 100
        """, (market_id,))
        
        results = cur.fetchall()
        cur.close()
        conn.close()
        
        bids = []
        asks = []
        for r in results:
            if r[0] == 'bid':
                bids.append({"price": normalize_number(r[1]), "size": normalize_number(r[2]), "created_at": r[3]})
            else:
                asks.append({"price": normalize_number(r[1]), "size": normalize_number(r[2]), "created_at": r[3]})
        
        return {"bids": bids, "asks": asks}
    
    def detect_order_book_changes(self, market_id):
        """Detect sudden changes in order book."""
        order_book = self.get_order_book_snapshot(market_id)
        bids = order_book["bids"]
        asks = order_book["asks"]
        
        if not bids or not asks:
            return {"changed": False, "reason": "Insufficient order book data"}
        
        # Get best bid and ask
        best_bid = bids[0]["price"] if bids else 0
        best_ask = asks[0]["price"] if asks else 0
        spread = best_ask - best_bid
        
        # Calculate total bid and ask size
        total_bid_size = sum(b["size"] for b in bids[:5])  # Top 5 levels
        total_ask_size = sum(a["size"] for a in asks[:5])  # Top 5 levels
        
        # Compare with previous snapshot (5 minutes ago)
        conn = psycopg2.connect(**self.db_config)
        cur = conn.cursor()
        
        five_min_ago = datetime.now() - timedelta(minutes=5)
        cur.execute("""
            SELECT side, price, size
            FROM order_books
            WHERE market_id = %s AND created_at <= %s
            ORDER BY created_at DESC
            LIMIT 20
        """, (market_id, five_min_ago))
        
        old_results = cur.fetchall()
        cur.close()
        conn.close()
        
        if len(old_results) < 10:
            return {"changed": False, "reason": "Insufficient historical data"}
        
        old_bids = [r for r in old_results if r[0] == 'bid']
        old_asks = [r for r in old_results if r[0] == 'ask']
        
        old_best_bid = normalize_number(old_bids[0][1]) if old_bids else 0.0
        old_best_ask = normalize_number(old_asks[0][1]) if old_asks else 0.0
        old_total_bid_size = sum(normalize_number(r[2]) for r in old_bids[:5])
        old_total_ask_size = sum(normalize_number(r[2]) for r in old_asks[:5])
        
        changes = []
        score = 0
        
        # Bid increase > 30%
        if old_best_bid > 0:
            bid_change = (best_bid - old_best_bid) / old_best_bid
            if bid_change > 0.3:
                changes.append(f"Bid increased {bid_change:.1%}")
                score += 20
        
        # Ask decrease > 30%
        if old_best_ask > 0:
            ask_change = (old_best_ask - best_ask) / old_best_ask
            if ask_change > 0.3:
                changes.append(f"Ask decreased {ask_change:.1%}")
                score += 20
        
        # Spread suddenly narrowed
        old_spread = old_best_ask - old_best_bid
        if old_spread > 0:
            spread_change = (old_spread - spread) / old_spread
            if spread_change > 0.3:
                changes.append(f"Spread narrowed {spread_change:.1%}")
                score += 15
        
        # Liquidity increase
        if old_total_bid_size > 0:
            liquidity_change = (total_bid_size - old_total_bid_size) / old_total_bid_size
            if liquidity_change > 0.5:
                changes.append(f"Bid liquidity increased {liquidity_change:.1%}")
                score += 15
        
        return {
            "changed": len(changes) > 0,
            "changes": changes,
            "score": score,
            "current": {
                "best_bid": best_bid,
                "best_ask": best_ask,
                "spread": spread,
                "total_bid_size": total_bid_size,
                "total_ask_size": total_ask_size
            },
            "previous": {
                "best_bid": old_best_bid,
                "best_ask": old_best_ask,
                "spread": old_spread,
                "total_bid_size": old_total_bid_size,
                "total_ask_size": old_total_ask_size
            }
        }
    
    def detect_price_breakout(self, market_id):
        """Detect price breakouts (30min and 24h)."""
        prices = self.get_historical_prices(market_id, hours=24)
        
        if len(prices) < 10:
            return {"breakout": False, "reason": "Insufficient price data"}
        
        current_price = prices[-1]["yes_price"] if prices else 0
        if not current_price:
            return {"breakout": False, "reason": "No current price"}
        
        # 30-minute high
        thirty_min_ago = datetime.now() - timedelta(minutes=30)
        prices_30min = [p for p in prices if p["created_at"] >= thirty_min_ago]
        high_30min = max(p["yes_price"] for p in prices_30min) if prices_30min else current_price
        
        # 24-hour high
        high_24h = max(p["yes_price"] for p in prices) if prices else current_price
        
        breakouts = []
        score = 0
        
        # 30-minute breakout
        if current_price > high_30min * 1.05:  # 5% above 30min high
            breakouts.append(f"30min breakout: {current_price:.4f} > {high_30min:.4f}")
            score += 25
        
        # 24-hour breakout
        if current_price > high_24h * 1.10:  # 10% above 24h high
            breakouts.append(f"24h breakout: {current_price:.4f} > {high_24h:.4f}")
            score += 35
        
        return {
            "breakout": len(breakouts) > 0,
            "breakouts": breakouts,
            "score": score,
            "current_price": current_price,
            "high_30min": high_30min,
            "high_24h": high_24h
        }
    
    def detect_volume_anomaly(self, market_id):
        """Detect volume anomalies using Z-score."""
        conn = psycopg2.connect(**self.db_config)
        cur = conn.cursor()
        
        # Get volume data from markets table
        cur.execute("""
            SELECT volume, created_at
            FROM (
                SELECT 
                    m.volume,
                    mp.created_at
                FROM markets m
                CROSS JOIN LATERAL (
                    SELECT created_at FROM market_prices 
                    WHERE market_id = m.market_id 
                    ORDER BY created_at DESC LIMIT 1
                ) mp
                WHERE m.market_id = %s
            ) recent
            ORDER BY created_at DESC
            LIMIT 100
        """, (market_id,))
        
        results = cur.fetchall()
        cur.close()
        conn.close()
        
        if len(results) < 20:
            return {"anomaly": False, "reason": "Insufficient volume data"}
        
        volumes = [normalize_number(r[0]) for r in results if r[0]]
        current_volume = volumes[0] if volumes else 0
        
        if not current_volume:
            return {"anomaly": False, "reason": "No current volume"}
        
        # Calculate Z-score
        mean = statistics.mean(volumes[1:])  # Exclude current
        stdev = statistics.stdev(volumes[1:]) if len(volumes) > 2 else 0
        
        if stdev == 0:
            return {"anomaly": False, "reason": "No volume variance"}
        
        z_score = (current_volume - mean) / stdev
        
        anomalies = []
        score = 0
        
        # High volume anomaly (Z-score > 2)
        if z_score > 2:
            anomalies.append(f"High volume anomaly: Z-score {z_score:.2f}")
            score += 30
        
        # Low volume anomaly (Z-score < -2)
        if z_score < -2:
            anomalies.append(f"Low volume anomaly: Z-score {z_score:.2f}")
            score += 15
        
        return {
            "anomaly": len(anomalies) > 0,
            "anomalies": anomalies,
            "score": score,
            "current_volume": current_volume,
            "mean_volume": mean,
            "z_score": z_score
        }
    
    def detect_order_book_imbalance(self, market_id):
        """Detect order book imbalance."""
        order_book = self.get_order_book_snapshot(market_id)
        bids = order_book["bids"]
        asks = order_book["asks"]
        
        if not bids or not asks:
            return {"imbalance": False, "reason": "Insufficient order book data"}
        
        # Calculate total bid and ask size (top 10 levels)
        total_bid_size = sum(b["size"] for b in bids[:10])
        total_ask_size = sum(a["size"] for a in asks[:10])
        
        total_size = total_bid_size + total_ask_size
        if total_size == 0:
            return {"imbalance": False, "reason": "No order book size"}
        
        # Calculate imbalance ratio
        bid_ratio = total_bid_size / total_size
        ask_ratio = total_ask_size / total_size
        
        imbalances = []
        score = 0
        
        # Strong buying pressure (bid ratio > 0.7)
        if bid_ratio > 0.7:
            imbalances.append(f"Strong buying pressure: bid ratio {bid_ratio:.2%}")
            score += 25
        
        # Strong selling pressure (ask ratio > 0.7)
        if ask_ratio > 0.7:
            imbalances.append(f"Strong selling pressure: ask ratio {ask_ratio:.2%}")
            score += 25
        
        # Moderate buying pressure (bid ratio > 0.6)
        if 0.6 < bid_ratio <= 0.7:
            imbalances.append(f"Moderate buying pressure: bid ratio {bid_ratio:.2%}")
            score += 15
        
        # Moderate selling pressure (ask ratio > 0.6)
        if 0.6 < ask_ratio <= 0.7:
            imbalances.append(f"Moderate selling pressure: ask ratio {ask_ratio:.2%}")
            score += 15
        
        return {
            "imbalance": len(imbalances) > 0,
            "imbalances": imbalances,
            "score": score,
            "total_bid_size": total_bid_size,
            "total_ask_size": total_ask_size,
            "bid_ratio": bid_ratio,
            "ask_ratio": ask_ratio
        }
    
    def calculate_signal(self, market_id):
        """Calculate comprehensive trading signal for a market."""
        # Run all detectors
        order_book_changes = self.detect_order_book_changes(market_id)
        price_breakout = self.detect_price_breakout(market_id)
        volume_anomaly = self.detect_volume_anomaly(market_id)
        order_imbalance = self.detect_order_book_imbalance(market_id)
        
        # Calculate total score
        total_score = (
            order_book_changes.get("score", 0) +
            price_breakout.get("score", 0) +
            volume_anomaly.get("score", 0) +
            order_imbalance.get("score", 0)
        )
        
        # Cap score at 100
        total_score = min(total_score, 100)
        
        # Determine signal type
        all_reasons = []
        
        if order_book_changes["changed"]:
            all_reasons.extend(order_book_changes["changes"])
        
        if price_breakout["breakout"]:
            all_reasons.extend(price_breakout["breakouts"])
        
        if volume_anomaly["anomaly"]:
            all_reasons.extend(volume_anomaly["anomalies"])
        
        if order_imbalance["imbalance"]:
            all_reasons.extend(order_imbalance["imbalances"])
        
        # Determine signal based on score and buying/selling pressure
        signal = "WATCH"
        
        if total_score >= 70:
            # High score - check for buying/selling pressure
            if order_imbalance.get("bid_ratio", 0.5) > 0.6:
                signal = "BUY"
            elif order_imbalance.get("ask_ratio", 0.5) > 0.6:
                signal = "SELL"
            else:
                signal = "WATCH"
        elif total_score >= 40:
            signal = "WATCH"
        
        return {
            "market_id": market_id,
            "signal": signal,
            "score": total_score,
            "reason": "; ".join(all_reasons) if all_reasons else "No significant signals",
            "metrics": {
                "order_book_changes": order_book_changes,
                "price_breakout": price_breakout,
                "volume_anomaly": volume_anomaly,
                "order_imbalance": order_imbalance
            }
        }
    
    def save_signal(self, signal_data):
        """Save signal to database."""
        conn = psycopg2.connect(**self.db_config)
        cur = conn.cursor()
        
        cur.execute("""
            INSERT INTO signals (
                market_id, signal, score, reason, raw, created_at
            )
            VALUES (%s, %s, %s, %s, %s, CURRENT_TIMESTAMP)
        """, (
            signal_data["market_id"],
            signal_data["signal"],
            signal_data["score"],
            signal_data["reason"],
            Json(signal_data["metrics"]),
        ))
        
        conn.commit()
        cur.close()
        conn.close()
    
    def generate_signals_for_markets(self, market_ids, limit=10):
        """Generate signals for multiple markets."""
        results = {
            "total_tested": 0,
            "buy_signals": 0,
            "sell_signals": 0,
            "watch_signals": 0,
            "errors": 0
        }
        
        for market_id in market_ids[:limit]:
            try:
                signal = self.calculate_signal(market_id)
                self.save_signal(signal)
                
                results["total_tested"] += 1
                
                if signal["signal"] == "BUY":
                    results["buy_signals"] += 1
                elif signal["signal"] == "SELL":
                    results["sell_signals"] += 1
                else:
                    results["watch_signals"] += 1
                
                print(f"Market {market_id}: {signal['signal']} (score: {signal['score']})")
            except Exception as e:
                print(f"Error generating signal for market {market_id}: {e}")
                results["errors"] += 1
        
        return results


def main():
    """Test signal generation."""
    engine = SignalEngine()
    
    # Get some market IDs from database
    conn = psycopg2.connect(**DB_CONFIG)
    cur = conn.cursor()
    cur.execute("SELECT market_id FROM markets LIMIT 10")
    market_ids = [r[0] for r in cur.fetchall()]
    cur.close()
    conn.close()
    
    print(f"Testing signal generation for {len(market_ids)} markets...")
    results = engine.generate_signals_for_markets(market_ids, limit=5)
    
    print(f"\nResults:")
    print(f"Total tested: {results['total_tested']}")
    print(f"BUY signals: {results['buy_signals']}")
    print(f"SELL signals: {results['sell_signals']}")
    print(f"WATCH signals: {results['watch_signals']}")
    print(f"Errors: {results['errors']}")


if __name__ == "__main__":
    main()
