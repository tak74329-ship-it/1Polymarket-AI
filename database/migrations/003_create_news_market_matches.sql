CREATE TABLE IF NOT EXISTS news_market_matches (
    id SERIAL PRIMARY KEY,
    news_id INTEGER,
    market_id TEXT,
    score NUMERIC,
    keywords TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(news_id, market_id)
);

CREATE INDEX IF NOT EXISTS idx_news_market_matches_news_id ON news_market_matches(news_id);
CREATE INDEX IF NOT EXISTS idx_news_market_matches_market_id ON news_market_matches(market_id);
