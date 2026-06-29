import traceback
import psycopg2
from psycopg2.extras import Json

from backend.utils.config import DB_CONFIG
from backend.ai.market_context import get_market_context


def local_rule_analysis(context: dict):
    market = context["market"]
    signals = context["signals"]
    news = context["news"]
    prices = context["prices"]

    signal_score = sum(s["score"] for s in signals[:5])
    news_score = sum(n["score"] for n in news[:10])
    latest_price = prices[0]["yes_price"] if prices else 0.5

    confidence = min(30 + signal_score * 0.4 + news_score * 0.3, 95)
    probability = min(max(latest_price * 100 + signal_score * 0.1 + news_score * 0.05, 1), 99)

    action = "WATCH"
    risk = "MEDIUM"

    if confidence >= 70 and probability >= 65:
        action = "BUY_CANDIDATE"
    elif confidence >= 70 and probability <= 35:
        action = "SELL_CANDIDATE"

    if market["liquidity"] < 1000:
        risk = "HIGH"
    elif market["liquidity"] > 20000:
        risk = "LOW"

    reason = (
        f"Local AI-rule analysis. Latest YES price={latest_price:.2f}. "
        f"Signal score={signal_score:.1f}. News score={news_score:.1f}. "
        f"Liquidity={market['liquidity']:.1f}."
    )

    return {
        "model": "local-rule-v1",
        "probability": round(probability, 2),
        "confidence": round(confidence, 2),
        "action": action,
        "risk": risk,
        "reason": reason,
    }


def save_ai_analysis(market_id: str, analysis: dict, raw_context: dict):
    conn = psycopg2.connect(**DB_CONFIG)
    cur = conn.cursor()

    cur.execute("""
        INSERT INTO ai_analysis (
            market_id, model, ai_probability, confidence, reason, raw, created_at
        )
        VALUES (%s, %s, %s, %s, %s, %s, CURRENT_TIMESTAMP)
    """, (
        market_id,
        analysis["model"],
        analysis["probability"],
        analysis["confidence"],
        analysis["reason"],
        Json({
            "analysis": analysis,
            "context": raw_context,
        })
    ))

    conn.commit()
    cur.close()
    conn.close()


def analyze_market(market_id: str):
    context = get_market_context(market_id)
    if not context:
        return None

    analysis = local_rule_analysis(context)
    save_ai_analysis(market_id, analysis, context)
    return analysis


def run(limit=10):
    try:
        print("▶️ Running AI Engine...")

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
            ) latest_price ON true
            WHERE m.active = true
              AND m.closed = false
              AND COALESCE(m.liquidity, 0) > 1000
              AND COALESCE(m.volume, 0) > 10000
              AND latest_price.yes_price > 0.05
              AND latest_price.yes_price < 0.95
            ORDER BY m.volume DESC
            LIMIT %s
        """, (limit,))
        market_ids = [r[0] for r in cur.fetchall()]
        cur.close()
        conn.close()

        tested = 0
        errors = 0

        for market_id in market_ids:
            try:
                analysis = analyze_market(market_id)
                if analysis:
                    tested += 1
                    print(
                        f"Market {market_id}: "
                        f"prob={analysis['probability']} "
                        f"conf={analysis['confidence']} "
                        f"action={analysis['action']} "
                        f"risk={analysis['risk']}"
                    )
            except Exception as e:
                errors += 1
                print(f"Error analyzing {market_id}: {e}")

        print("✅ AI Engine Finished")
        print(f"Tested: {tested}")
        print(f"Errors: {errors}")
        return {"tested": tested, "errors": errors}

    except Exception:
        print("❌ AI Engine Failed")
        traceback.print_exc()
        return {"errors": 1}


if __name__ == "__main__":
    run()
