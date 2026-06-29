import psycopg2
from backend.utils.config import DB_CONFIG

TABLES_SQL = """
CREATE TABLE IF NOT EXISTS markets (
    id SERIAL PRIMARY KEY,
    market_id TEXT UNIQUE,
    question TEXT,
    slug TEXT,
    category TEXT,
    active BOOLEAN,
    closed BOOLEAN,
    volume NUMERIC,
    liquidity NUMERIC,
    raw JSONB,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS market_prices (
    id SERIAL PRIMARY KEY,
    market_id TEXT,
    outcome TEXT,
    price NUMERIC,
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS news_items (
    id SERIAL PRIMARY KEY,
    source TEXT,
    title TEXT,
    url TEXT UNIQUE,
    summary TEXT,
    published_at TIMESTAMP,
    raw JSONB,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS ai_analysis (
    id SERIAL PRIMARY KEY,
    market_id TEXT,
    model TEXT,
    analysis TEXT,
    probability NUMERIC,
    confidence NUMERIC,
    raw JSONB,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS signals (
    id SERIAL PRIMARY KEY,
    market_id TEXT,
    signal_type TEXT,
    side TEXT,
    probability NUMERIC,
    confidence NUMERIC,
    reason TEXT,
    status TEXT DEFAULT 'paper',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS paper_trades (
    id SERIAL PRIMARY KEY,
    market_id TEXT,
    side TEXT,
    price NUMERIC,
    size NUMERIC,
    reason TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS system_logs (
    id SERIAL PRIMARY KEY,
    component TEXT,
    level TEXT,
    message TEXT,
    raw JSONB,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
"""

def main():
    conn = psycopg2.connect(**DB_CONFIG)
    cur = conn.cursor()
    cur.execute(TABLES_SQL)
    conn.commit()
    cur.close()
    conn.close()

    print("✅ 数据库连接成功")
    print("✅ 专业数据表创建成功")

if __name__ == "__main__":
    main()
