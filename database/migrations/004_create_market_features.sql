CREATE TABLE IF NOT EXISTS market_features (
    id SERIAL PRIMARY KEY,
    market_id TEXT NOT NULL,
    feature_json JSONB NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_market_features_market_id ON market_features(market_id);
CREATE INDEX IF NOT EXISTS idx_market_features_created_at ON market_features(created_at);
