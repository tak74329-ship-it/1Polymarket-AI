-- Create order_books table for storing order book depth data
CREATE TABLE IF NOT EXISTS order_books (
    id SERIAL PRIMARY KEY,
    market_id VARCHAR(255) NOT NULL,
    token_id VARCHAR(255) NOT NULL,
    side VARCHAR(10) NOT NULL, -- 'bid' or 'ask'
    price DECIMAL(20, 8) NOT NULL,
    size DECIMAL(20, 8) NOT NULL,
    raw JSONB,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_order_books_market_id ON order_books(market_id);
CREATE INDEX IF NOT EXISTS idx_order_books_token_id ON order_books(token_id);
CREATE INDEX IF NOT EXISTS idx_order_books_side ON order_books(side);
CREATE INDEX IF NOT EXISTS idx_order_books_created_at ON order_books(created_at);

COMMENT ON TABLE order_books IS 'Order book depth data from Polymarket CLOB API';
COMMENT ON COLUMN order_books.market_id IS 'Market condition ID';
COMMENT ON COLUMN order_books.token_id IS 'Token/asset ID for the order';
COMMENT ON COLUMN order_books.side IS 'Order side: bid or ask';
COMMENT ON COLUMN order_books.price IS 'Order price';
COMMENT ON COLUMN order_books.size IS 'Order size';
COMMENT ON COLUMN order_books.raw IS 'Raw order book data from API';
