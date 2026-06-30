"""Live Readiness Check — verify the system is safe before any live trading."""

import os
import json
import psycopg2
from backend.utils.config import DB_CONFIG, load_trading_config


def check(condition: bool, name: str, detail: str = "") -> tuple:
    status = "✅ PASS" if condition else "❌ FAIL"
    print(f"  {status:<12} {name:<45} {detail}")
    return condition


def run():
    print("=" * 80)
    print("  LIVE READINESS CHECK")
    print("  Polymarket-AI — Pre-flight verification")
    print("=" * 80)

    checks_passed = 0
    checks_total = 0

    def c(condition, name, detail=""):
        nonlocal checks_passed, checks_total
        checks_total += 1
        ok = check(condition, name, detail)
        if ok:
            checks_passed += 1
        return ok

    # ── 1. Config safety ─────────────────────────────────────────────
    print(f"\n{'─' * 80}")
    print("  1. CONFIG SAFETY")
    print(f"{'─' * 80}")

    cfg = load_trading_config()

    c(cfg.get("paper_mode") is True,
      "paper_mode is true by default")

    c(cfg.get("live_trading_enabled") is False,
      "live_trading_enabled is false by default")

    c("live_trading_enabled" in cfg,
      "live_trading_enabled key exists")

    c("paper_mode" in cfg,
      "paper_mode key exists")

    c(cfg.get("max_open_positions", 0) > 0,
      "max_open_positions is set", str(cfg.get("max_open_positions")))

    c(cfg.get("max_exposure_pct", 0) > 0,
      "max_exposure_pct is set", f"{cfg.get('max_exposure_pct')}%")

    c(cfg.get("min_liquidity", 0) > 0,
      "min_liquidity is set", str(cfg.get("min_liquidity")))

    c(cfg.get("max_spread", 0) > 0,
      "max_spread is set", str(cfg.get("max_spread")))

    # ── 2. No private keys in repo ─────────────────────────────────────
    print(f"\n{'─' * 80}")
    print("  2. PRIVATE KEY SAFETY")
    print(f"{'─' * 80}")

    project_root = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))

    # Check .env for PRIVATE_KEY
    env_path = os.path.join(project_root, ".env")
    has_private_key_in_env = False
    if os.path.exists(env_path):
        with open(env_path) as f:
            for line in f:
                if line.strip().startswith("#"):
                    continue
                if "PRIVATE_KEY" in line.upper() or "SECRET" in line.upper():
                    has_private_key_in_env = True
                    break

    c(not has_private_key_in_env,
      "No PRIVATE_KEY in .env file")

    # Check for .pem / .key files
    key_files = []
    for root, dirs, files in os.walk(project_root):
        dirs[:] = [d for d in dirs if d not in (".venv", "node_modules", ".git", "__pycache__")]
        for fname in files:
            if fname.endswith((".pem", ".key", ".p12", ".keystore")):
                key_files.append(os.path.join(root, fname))

    c(len(key_files) == 0,
      "No .pem/.key/.p12 files in repository",
      f"found {len(key_files)}" if key_files else "")

    # ── 3. Risk Manager ──────────────────────────────────────────────
    print(f"\n{'─' * 80}")
    print("  3. RISK MANAGER")
    print(f"{'─' * 80}")

    try:
        from backend.risk.risk_manager import RiskManager
        rm = RiskManager()
        c(True, "RiskManager imports successfully")
        c(hasattr(rm, "check_paper_mode"),
          "RiskManager.check_paper_mode exists")
        c(hasattr(rm, "check_exposure"),
          "RiskManager.check_exposure exists")
        c(hasattr(rm, "check_max_positions"),
          "RiskManager.check_max_positions exists")
        c(hasattr(rm, "check_duplicate_theme"),
          "RiskManager.check_duplicate_theme exists")
    except Exception as e:
        c(False, "RiskManager import failed", str(e))

    # ── 4. Execution Adapters ────────────────────────────────────────
    print(f"\n{'─' * 80}")
    print("  4. EXECUTION ADAPTERS")
    print(f"{'─' * 80}")

    try:
        from backend.execution.base import BaseExecutionAdapter, Order
        c(True, "BaseExecutionAdapter imports")
        o = Order(market_id="test", amount_usd=100)
        valid, reason = BaseExecutionAdapter().validate(o)
        c(valid, "Order validation works", f"valid={valid}")
    except Exception as e:
        c(False, "BaseExecutionAdapter import failed", str(e))

    try:
        from backend.execution.paper_adapter import PaperExecutionAdapter
        pa = PaperExecutionAdapter()
        c(True, "PaperExecutionAdapter imports")
        c(pa.name() == "paper", "PaperAdapter name is 'paper'")
    except Exception as e:
        c(False, "PaperExecutionAdapter import failed", str(e))

    try:
        from backend.execution.polymarket_adapter import PolymarketExecutionAdapter
        pla = PolymarketExecutionAdapter()
        c(True, "PolymarketExecutionAdapter imports")

        # Verify live trading is blocked
        try:
            pla.execute(Order(market_id="test", amount_usd=100))
            c(False, "PolymarketAdapter.execute raises RuntimeError when disabled")
        except RuntimeError:
            c(True, "PolymarketAdapter.execute safely blocked", "raises RuntimeError")
        except Exception:
            c(False, "PolymarketAdapter.execute raises wrong exception type")
    except Exception as e:
        c(False, "PolymarketExecutionAdapter import failed", str(e))

    # ── 5. Portfolio Manager ─────────────────────────────────────────
    print(f"\n{'─' * 80}")
    print("  5. PORTFOLIO MANAGER")
    print(f"{'─' * 80}")

    try:
        from backend.portfolio.portfolio_manager import PortfolioManager
        pm = PortfolioManager()
        c(True, "PortfolioManager imports successfully")
        checks = [
            "check_market_open", "check_min_liquidity", "check_max_spread",
            "check_max_exposure", "check_max_positions", "check_theme_limit",
            "check_amount", "check_all",
        ]
        for chk in checks:
            c(hasattr(pm, chk), f"PortfolioManager.{chk} exists")
    except Exception as e:
        c(False, "PortfolioManager import failed", str(e))

    # ── 6. Database connectivity ─────────────────────────────────────
    print(f"\n{'─' * 80}")
    print("  6. DATABASE & PIPELINE")
    print(f"{'─' * 80}")

    try:
        conn = psycopg2.connect(**DB_CONFIG)
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM markets")
        market_count = cur.fetchone()[0]
        c(market_count > 0, "Markets table has data", f"{market_count} markets")

        cur.execute("SELECT COUNT(*) FROM market_features")
        feat_count = cur.fetchone()[0]
        c(feat_count > 0, "market_features has data", f"{feat_count} features")

        cur.execute("SELECT COUNT(*) FROM ai_analysis")
        ai_count = cur.fetchone()[0]
        c(ai_count > 0, "ai_analysis has data", f"{ai_count} analyses")

        cur.execute("SELECT COUNT(*) FROM market_prices")
        price_count = cur.fetchone()[0]
        c(price_count > 0, "market_prices has data", f"{price_count} snapshots")

        cur.close()
        conn.close()
    except Exception as e:
        c(False, "Database connectivity", str(e))

    # ── 7. Backup script ─────────────────────────────────────────────
    print(f"\n{'─' * 80}")
    print("  7. BACKUP")
    print(f"{'─' * 80}")

    backup_script = os.path.join(project_root, "scripts", "backup_db.sh")
    c(os.path.exists(backup_script),
      "backup_db.sh exists")

    backup_dir = os.path.join(project_root, "backups")
    c(os.path.isdir(backup_dir),
      "backups directory exists")

    if os.path.isdir(backup_dir):
        backups = [f for f in os.listdir(backup_dir) if f.endswith(".sql.gz")]
        c(len(backups) > 0, "Backup files exist", f"{len(backups)} backup(s)")

    # ── 8. Dashboard ──────────────────────────────────────────────
    print(f"\n{'─' * 80}")
    print("  8. DASHBOARD")
    print(f"{'─' * 80}")

    dashboard_path = os.path.join(project_root, "backend", "dashboard", "dashboard.py")
    c(os.path.exists(dashboard_path), "dashboard.py exists")

    # ── 9. Scheduler ─────────────────────────────────────────────────
    print(f"\n{'─' * 80}")
    print("  9. SCHEDULER")
    print(f"{'─' * 80}")

    scheduler_path = os.path.join(project_root, "backend", "scheduler_v2.py")
    c(os.path.exists(scheduler_path), "scheduler_v2.py exists")

    # ── 10. Paper trading has run ────────────────────────────────────
    print(f"\n{'─' * 80}")
    print("  10. PAPER TRADING HISTORY")
    print(f"{'─' * 80}")

    try:
        conn = psycopg2.connect(**DB_CONFIG)
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM paper_orders")
        order_count = cur.fetchone()[0]
        c(order_count > 0, "Paper orders exist", f"{order_count} orders")

        cur.execute("SELECT COUNT(*) FROM paper_positions")
        pos_count = cur.fetchone()[0]
        c(pos_count > 0, "Paper positions exist", f"{pos_count} positions")
        cur.close()
        conn.close()
    except Exception as e:
        c(False, "Paper trading data", str(e))

    # ══════════════════════════════════════════════════════════════════
    #  SUMMARY
    # ══════════════════════════════════════════════════════════════════
    print(f"\n{'=' * 80}")
    print(f"  READINESS CHECK COMPLETE")
    print(f"  {checks_passed}/{checks_total} checks passed")
    print(f"{'=' * 80}")

    if checks_passed == checks_total:
        print(f"\n  ✅ SYSTEM IS READY FOR LIVE TRADING (but still disabled)")
        print(f"  🔒 To enable: set paper_mode=false AND live_trading_enabled=true")
        print(f"\n  ⚠️  Remember: no private keys in repo, no wallet connected yet.")
    else:
        print(f"\n  ❌ {checks_total - checks_passed} check(s) failed — review above")

    return checks_passed == checks_total


if __name__ == "__main__":
    run()
