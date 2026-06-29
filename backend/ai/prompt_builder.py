def build_prompt(context: dict) -> str:
    market = context["market"]
    prices = context["prices"]
    signals = context["signals"]
    news = context["news"]

    return f"""
You are analyzing a Polymarket prediction market.

Market:
- ID: {market['market_id']}
- Question: {market['question']}
- Volume: {market['volume']}
- Liquidity: {market['liquidity']}

Recent Prices:
{prices}

Signals:
{signals}

Related News:
{news}

Return:
- probability
- confidence
- action
- risk
- reason
"""
