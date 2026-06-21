#!/usr/bin/env python3
"""
Minerva Bridge — /market Slash Command Handler.

Fetches market overview from Minerva MCP Server and formats
it into a readable table for Hermes Agent.
"""

import sys
import json
import urllib.request

MCP_CALL_URL = "http://127.0.0.1:9100/mcp/tools/call"

def get_market_data():
    payload = {
        "name": "minerva_get_all_markets",
        "arguments": {}
    }
    
    req = urllib.request.Request(
        MCP_CALL_URL,
        data=json.dumps(payload).encode('utf-8'),
        headers={'Content-Type': 'application/json'}
    )
    
    try:
        with urllib.request.urlopen(req) as resp:
            data = json.loads(resp.read().decode())
            # Extract content from MCP response format
            content = json.loads(data['content'][0]['text'])
            return content
    except Exception as e:
        print(f"Error fetching market data from Minerva: {e}")
        sys.exit(1)

def format_market_data(data):
    summaries = data.get("summaries", {})
    if not summaries:
        return "No market data available currently."
        
    output = ["📊 **Minerva Market Overview**\n"]
    output.append("| Symbol | Price | 24h Vol | RSI | MACD | Imbalance |")
    output.append("|---|---|---|---|---|---|")
    
    for symbol, details in summaries.items():
        price = details.get('price', 0)
        vol = details.get('volume_24h', 0)
        rsi = details.get('rsi', 'N/A')
        macd = details.get('macd', 'N/A')
        imb = details.get('order_book_imbalance', 'N/A')
        
        output.append(f"| {symbol} | ${price:,.2f} | ${vol:,.0f} | {rsi} | {macd} | {imb} |")
        
    return "\n".join(output)

if __name__ == "__main__":
    market_data = get_market_data()
    print(format_market_data(market_data))
