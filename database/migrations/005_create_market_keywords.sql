CREATE TABLE IF NOT EXISTS market_keywords (
    id SERIAL PRIMARY KEY,
    market_id TEXT NOT NULL,
    keyword TEXT NOT NULL,
    weight NUMERIC DEFAULT 1,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(market_id, keyword)
);

CREATE INDEX IF NOT EXISTS idx_market_keywords_market_id ON market_keywords(market_id);
CREATE INDEX IF NOT EXISTS idx_market_keywords_keyword ON market_keywords(keyword);
