"""Candidate Ranking V1 — score and rank markets using feature_json."""

import psycopg2
from backend.utils.config import DB_CONFIG


def f(v):
    return float(v or 0)


def run(limit=20):
    """Fetch latest features, compute final_score, return Top N ranked candidates."""
    conn = psycopg2.connect(**DB_CONFIG)
    cur = conn.cursor()

    # ── 1. Load latest feature per market ─────────────────────────────
    cur.execute("""
        SELECT DISTINCT ON (mf.market_id)
            mf.market_id,
            m.question,
            mf.feature_json
        FROM market_features mf
        JOIN markets m ON m.market_id = mf.market_id
        ORDER BY mf.market_id, mf.created_at DESC
    """)
    rows = cur.fetchall()
    cur.close()
    conn.close()

    # ── 2. Parse & filter ─────────────────────────────────────────────
    raw = []
    for market_id, question, fj in rows:
        latest_yes_price = f(fj.get("latest_yes_price"))
        is_active = fj.get("is_active", False)
        is_closed = fj.get("is_closed", True)
        has_signal = fj.get("has_signal", False)

        # Basic eligibility
        if not is_active or is_closed:
            continue
        if latest_yes_price <= 0.05 or latest_yes_price >= 0.95:
            continue
        if not has_signal:
            continue

        latest_signal_score = f(fj.get("latest_signal_score"))
        total_signal_score_20 = f(fj.get("total_signal_score_20"))
        news_score = f(fj.get("news_score"))
        news_count = int(fj.get("news_count", 0))
        orderbook_imbalance = f(fj.get("orderbook_imbalance"))
        volatility_30 = f(fj.get("volatility_30_snapshots"))
        liquidity = f(fj.get("liquidity"))
        volume = f(fj.get("volume"))

        raw.append({
            "market_id": market_id,
            "question": question,
            "latest_yes_price": latest_yes_price,
            "latest_signal_score": latest_signal_score,
            "total_signal_score_20": total_signal_score_20,
            "news_score": news_score,
            "news_count": news_count,
            "orderbook_imbalance": orderbook_imbalance,
            "volatility_30_snapshots": volatility_30,
            "liquidity": liquidity,
            "volume": volume,
        })

    if not raw:
        print("⚠️  No candidates after basic filter.")
        return []

    # ── 3. Normalise liquidity & volume to 0-100 ──────────────────────
    max_liq = max(r["liquidity"] for r in raw)
    max_vol = max(r["volume"] for r in raw)

    for r in raw:
        r["liquidity_score"] = (r["liquidity"] / max_liq * 100) if max_liq > 0 else 0
        r["volume_score"] = (r["volume"] / max_vol * 100) if max_vol > 0 else 0

    # ── 4. Weighted scoring ───────────────────────────────────────────
    for r in raw:
        imbalance_score = abs(r["orderbook_imbalance"]) * 100  # 0-100

        final = (
            0.35 * r["latest_signal_score"]
            + 0.20 * r["total_signal_score_20"]
            + 0.20 * r["news_score"]
            + 0.10 * imbalance_score
            + 0.10 * r["liquidity_score"]
            + 0.05 * r["volume_score"]
        )

        r["final_score"] = round(final, 2)

        # Build rank_reason
        parts = []
        if r["latest_signal_score"] > 0:
            parts.append(f"sig={r['latest_signal_score']:.0f}")
        if r["total_signal_score_20"] > 0:
            parts.append(f"sig20={r['total_signal_score_20']:.0f}")
        if r["news_score"] > 0:
            parts.append(f"news={r['news_score']:.0f}")
        if imbalance_score > 5:
            parts.append(f"imbal={r['orderbook_imbalance']:.2f}")
        if r["liquidity_score"] > 10:
            parts.append(f"liq={r['liquidity_score']:.0f}")
        if r["volume_score"] > 10:
            parts.append(f"vol={r['volume_score']:.0f}")
        r["rank_reason"] = " | ".join(parts) if parts else "base score"

    # ── 5. final_score filter & sort ──────────────────────────────────
    ranked = [r for r in raw if r["final_score"] > 20]
    ranked.sort(key=lambda x: x["final_score"], reverse=True)
    ranked = ranked[:limit]

    # ── 6. Print ──────────────────────────────────────────────────────
    print(f"\n===== CANDIDATE RANKING V1 (Top {len(ranked)}) =====")
    print(f"{'Rank':>4} {'market_id':>10} {'yes_price':>9} {'signal':>6} "
          f"{'sig20':>6} {'news':>5} {'imbal':>7} {'liq':>6} {'vol':>6} "
          f"{'score':>7}  reason")
    print("-" * 120)
    for i, r in enumerate(ranked, 1):
        print(
            f"{i:>4} {r['market_id']:>10} {r['latest_yes_price']:>9.4f} "
            f"{r['latest_signal_score']:>6.0f} {r['total_signal_score_20']:>6.0f} "
            f"{r['news_score']:>5.0f} {r['orderbook_imbalance']:>7.4f} "
            f"{r['liquidity_score']:>6.1f} {r['volume_score']:>6.1f} "
            f"{r['final_score']:>7.2f}  {r['rank_reason']}"
        )

    return ranked


if __name__ == "__main__":
    run()
