"""AI Engine V2 — local rule-based scoring using Candidate Ranking V1 output."""

import traceback
import psycopg2
from psycopg2.extras import Json

from backend.utils.config import DB_CONFIG
from backend.ranking.candidate_ranker import run as rank_candidates


def decide_risk(candidate: dict) -> str:
    """Determine risk level from feature data.

    HIGH  — volatility is high, spread is wide, or liquidity is low.
    LOW   — strong liquidity and stable spread/volatility.
    MEDIUM — everything else.
    """
    vol = candidate.get("volatility_30_snapshots", 0)
    liq = candidate.get("liquidity", 0)
    spread = candidate.get("spread", candidate.get("orderbook_imbalance", 0))

    high_flags = 0
    if vol > 0.002:
        high_flags += 1
    if liq < 10000:
        high_flags += 1
    if abs(spread) > 0.05:
        high_flags += 1

    low_flags = 0
    if liq > 50000:
        low_flags += 1
    if vol < 0.0005:
        low_flags += 1
    if abs(spread) < 0.01:
        low_flags += 1

    if high_flags >= 2:
        return "HIGH"
    if low_flags >= 2:
        return "LOW"
    return "MEDIUM"


def analyze_candidate(candidate: dict) -> dict:
    """Run local decision logic on a single ranked candidate.

    Returns analysis dict with action, probability, confidence, risk, reason.
    """
    final_score = candidate.get("final_score", 0)
    yes_price = candidate.get("latest_yes_price", 0.5)
    risk = decide_risk(candidate)

    # ── Decision tree ────────────────────────────────────────────────
    buy_eligible = (
        final_score >= 35
        and 0.05 <= yes_price <= 0.85
        and candidate.get("has_signal", False)
        and risk != "HIGH"
    )

    if buy_eligible:
        action = "BUY"
        # Map score range 35-100+ to probability 55-90
        probability = min(55 + (final_score - 35) * 0.5, 90)
        confidence = min(60 + (final_score - 35) * 0.4, 95)
    elif final_score >= 20:
        action = "WATCH"
        probability = 50
        confidence = 50
    else:
        action = "SKIP"
        probability = 0
        confidence = 0

    # ── Build readable reason ────────────────────────────────────────
    parts = [f"final_score={final_score:.1f}"]
    parts.append(f"price={yes_price:.4f}")
    parts.append(f"risk={risk}")
    parts.append(candidate.get("rank_reason", ""))
    reason = " | ".join(p for p in parts if p)

    # ── Feature summary ──────────────────────────────────────────────
    feature_summary = {
        "final_score": final_score,
        "latest_signal_score": candidate.get("latest_signal_score", 0),
        "total_signal_score_20": candidate.get("total_signal_score_20", 0),
        "news_score": candidate.get("news_score", 0),
        "news_count": candidate.get("news_count", 0),
        "orderbook_imbalance": candidate.get("orderbook_imbalance", 0),
        "volatility_30_snapshots": candidate.get("volatility_30_snapshots", 0),
        "liquidity": candidate.get("liquidity", 0),
        "volume": candidate.get("volume", 0),
    }

    return {
        "model": "local-rule-v2",
        "probability": round(probability, 2),
        "confidence": round(confidence, 2),
        "action": action,
        "risk_level": risk,
        "reason": reason,
        "feature_summary": feature_summary,
    }


def save_ai_analysis(market_id: str, analysis: dict, candidate: dict):
    """Save analysis to ai_analysis table."""
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
            "candidate": candidate,
        })
    ))

    conn.commit()
    cur.close()
    conn.close()


def run(limit=20):
    """Run AI Engine V2 over Top N ranked candidates."""
    try:
        print("▶️ Running AI Engine V2 (Ranking-based)...")

        # ── 1. Get ranked candidates ─────────────────────────────────
        ranked = rank_candidates(limit=limit)

        if not ranked:
            print("⚠️  No ranked candidates available.")
            return {"tested": 0, "buy": 0, "watch": 0, "skip": 0, "errors": 0}

        # ── 2. Analyze each candidate ─────────────────────────────────
        tested = 0
        buy_count = 0
        watch_count = 0
        skip_count = 0
        errors = 0

        for candidate in ranked:
            try:
                market_id = candidate["market_id"]
                analysis = analyze_candidate(candidate)
                save_ai_analysis(market_id, analysis, candidate)
                tested += 1

                if analysis["action"] == "BUY":
                    buy_count += 1
                elif analysis["action"] == "WATCH":
                    watch_count += 1
                else:
                    skip_count += 1

                print(
                    f"{market_id:>10} | "
                    f"action={analysis['action']:<4} "
                    f"risk={analysis['risk_level']:<5} "
                    f"prob={analysis['probability']:.0f} "
                    f"conf={analysis['confidence']:.0f} "
                    f"score={candidate.get('final_score', 0):.1f} "
                    f"| {candidate.get('question', '')[:60]}"
                )

            except Exception as e:
                errors += 1
                print(f"Error analyzing {candidate.get('market_id', '?')}: {e}")

        print("✅ AI Engine V2 Finished")
        print(f"Tested: {tested}  BUY: {buy_count}  WATCH: {watch_count}  SKIP: {skip_count}  Errors: {errors}")
        return {"tested": tested, "buy": buy_count, "watch": watch_count, "skip": skip_count, "errors": errors}

    except Exception:
        print("❌ AI Engine V2 Failed")
        traceback.print_exc()
        return {"errors": 1}


if __name__ == "__main__":
    run()
