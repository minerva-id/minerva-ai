#!/usr/bin/env python3
"""
Minerva Bridge — /portfolio Slash Command Handler.

Fetches portfolio status from Minerva MCP Server and formats
it for Hermes Agent.
"""

import sys
import json
import urllib.request

MCP_CALL_URL = "http://127.0.0.1:9100/mcp/tools/call"

def get_portfolio_status():
    payload = {
        "name": "minerva_get_portfolio_status",
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
            return json.loads(data['content'][0]['text'])
    except Exception as e:
        print(f"Error fetching portfolio status from Minerva: {e}")
        sys.exit(1)

def get_positions():
    payload = {
        "name": "minerva_get_positions",
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
            return json.loads(data['content'][0]['text'])
    except Exception as e:
        return {"positions": {}}

def format_portfolio(status, positions_data):
    output = ["💼 **Minerva Portfolio Status**\n"]
    
    output.append(f"**Mode:** {status.get('agent_mode', 'N/A').upper()}")
    output.append(f"**Primary Exchange:** {status.get('primary_exchange', 'N/A')}")
    output.append(f"**Available Balance:** ${status.get('available_balance_usd', 0):,.2f}")
    output.append(f"**Total Exposure:** ${status.get('total_exposure_usd', 0):,.2f}")
    
    risk = status.get('risk', {})
    if risk:
        output.append(f"\n🛡️ **Risk Status:**")
        output.append(f"- Circuit Breaker Open: {risk.get('circuit_breaker_open', False)}")
        output.append(f"- Daily PnL: ${risk.get('daily_pnl', 0):,.2f}")
        output.append(f"- Drawdown: {risk.get('drawdown_pct', 0):.2f}%")
        
    positions = positions_data.get('positions', {})
    if positions:
        output.append("\n📈 **Open Positions:**")
        for sym, pos in positions.items():
            side = pos.get('side', '').upper()
            amt = pos.get('amount', 0)
            entry = pos.get('entry_price', 0)
            current = pos.get('current_price', 0)
            pnl = pos.get('unrealized_pnl', 0)
            pnl_pct = pos.get('unrealized_pnl_pct', 0)
            
            emoji = "🟢" if pnl >= 0 else "🔴"
            output.append(f"- {sym} ({side}): {amt} @ ${entry:,.2f} | Current: ${current:,.2f} | PnL: {emoji} ${pnl:,.2f} ({pnl_pct:.2f}%)")
    else:
        output.append("\n📈 **Open Positions:** None")
        
    return "\n".join(output)

if __name__ == "__main__":
    status = get_portfolio_status()
    positions = get_positions()
    print(format_portfolio(status, positions))
