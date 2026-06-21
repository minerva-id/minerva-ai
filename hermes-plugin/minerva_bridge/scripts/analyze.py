#!/usr/bin/env python3
"""
Minerva Bridge — /analyze Slash Command Handler.

Instructs Hermes Agent to perform a deep analysis on a specific
trading pair by querying Minerva for market data, signals, and news.
"""

import sys

def print_usage():
    print("Usage: /analyze <SYMBOL>")
    print("Example: /analyze BTC/USDT")
    sys.exit(1)

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print_usage()
        
    symbol = sys.argv[1].upper()
    
    # We don't do the analysis here; we instruct the LLM to do it
    # using the tools available to it.
    prompt = f"""
Please perform a comprehensive analysis for {symbol}. 
Use your available tools to gather the following data from Minerva:
1. Current market summary (`minerva_get_market_summary` for {symbol})
2. Latest trading signals (`minerva_get_signals` for {symbol})
3. Recent news (`minerva_get_news`)
4. On-chain alerts (`minerva_get_onchain_alerts`)

After gathering the data, synthesize it into a trading recommendation (Buy, Sell, or Hold) with a concise justification.
"""
    print(prompt)
