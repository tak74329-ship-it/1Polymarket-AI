import psycopg2
from backend.utils.config import DB_CONFIG

SQL = """
DROP TABLE IF EXISTS paper_trades;
DROP TABLE IF EXISTS signals;
DROP TABLE IF EXISTS ai_analysis;
DROP TABLE IF EXISTS news_items;
DROP TABLE IF EXISTS market_prices;
DROP TABLE IF EXISTS markets;
DROP TABLE IF EXISTS system_logs;

CREATE TABLE markets (
    id SERIAL PRIMARY KEY,
    market_id TEXT UNIQUE NOT NULL,
    question TEXT,
    slug TEXT,
    category TEXT,
    active BOOLEAN,
    closed BOOLEAN,
    volume NUMERIC,
    liquidity NUMERIC,
    outcomes JSONB,
    raw JSONB,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE market_prices (
    id SERIAL PRIMARY KEY,
    market_id TEXT NOT NULL,
    yes_price NUMERIC,
    no_price NUMERIC,
    spread NUMERIC,
    raw JSONB,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE news_items (
    id SERIAL PRIMARY KEY,
    source TEXT,
    title TEXT,
    url TEXT UNIQUE,
    summary TEXT,
    published_at TIMESTAMP,
    raw JSONB,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE ai_analysis (
    id SERIAL PRIMARY KEY,
    market_id TEXT,
    model TEXT,
    ai_probability NUMERIC,
    market_probability NUMERIC,
    edge NUMERIC,
    confidence NUMERIC,
    reason TEXT,
    raw JSONB,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE signals (
    id SERIAL PRIMARY KEY,
    market_id TEXT,
    signal TEXT,
    side TEXT,
    score NUMERIC,
    reason TEXT,
    status TEXT DEFAULT 'paper',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE paper_trades (
    id SERIAL PRIMARY KEY,
    market_id TEXT,
    action TEXT,
    side TEXT,
    price NUMERIC,
    size NUMERIC,
    pnl NUMERIC DEFAULT 0,
    reason TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE system_logs (
    id SERIAL PRIMARY KEY,
    component TEXT,
    level TEXT,
    message TEXT,
    raw JSONB,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_markets_market_id ON markets(market_id);
CREATE INDEX idx_market_prices_market_id ON market_prices(market_id);
CREATE INDEX idx_ai_analysis_market_id ON ai_analysis(market_id);
CREATE INDEX idx_signals_market_id ON signals(market_id);
CREATE INDEX idx_paper_trades_market_id ON paper_trades(market_id);
"""

def main():
    conn = psycopg2.connect(**DB_CONFIG)
    cur = conn.cursor()
    cur.execute(SQL)
    conn.commit()
    cur.close()
    conn.close()

    print("✅ V2 数据库重建成功")
    print("✅ 表和索引创建成功")

if __name__ == "__main__":
    main()
