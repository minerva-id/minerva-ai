"""
Minerva AI — Conversational Assistant (Jarvis-like).

Provides an interactive chat agent that supports function calling
to analyze markets, read portfolios, and execute orders manually.
"""

import json
import os
from typing import Any

from openai import AsyncOpenAI
from minerva.logger import get_logger

log = get_logger(__name__)

SYSTEM_PROMPT = """You are Minerva, an advanced AI trading assistant (similar to Jarvis from Iron Man).
You speak in a concise, highly analytical, and professional manner. You can use tools to fetch real-time market data, check the portfolio, and execute trades if the user commands it.

Always respond in Markdown format. When returning tabular data (like portfolios or journals), use Markdown tables.
If the user asks for a chart, you can use the `render_chart` tool to send data points to the frontend UI.
Your primary objective is to assist the user in making informed trading decisions.
"""

class MinervaAgent:
    def __init__(self, redis_store=None, supabase_store=None):
        self._redis = redis_store
        self._supabase = supabase_store
        self._api_key = os.getenv("OPENAI_API_KEY")
        self._model = "gpt-4o"  # Defaulting to gpt-4o for robust tool calling
        self._client = AsyncOpenAI(api_key=self._api_key) if self._api_key else None

    async def chat(self, user_message: str, history: list[dict] = None) -> dict:
        """Process a chat message using OpenAI tool calling."""
        if not self._client:
            return {"role": "assistant", "content": "Error: OPENAI_API_KEY is not configured in .env"}

        messages = [{"role": "system", "content": SYSTEM_PROMPT}]
        if history:
            messages.extend(history)
        messages.append({"role": "user", "content": user_message})

        tools = [
            {
                "type": "function",
                "function": {
                    "name": "get_market_summary",
                    "description": "Get current market summary for a specific trading pair (e.g. BTC/USDT).",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "symbol": {"type": "string", "description": "Trading pair symbol, e.g., BTC/USDT"}
                        },
                        "required": ["symbol"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "get_open_positions",
                    "description": "Get a list of currently open trading positions and their PnL.",
                    "parameters": {
                        "type": "object",
                        "properties": {}
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "render_chart",
                    "description": "Send time-series chart data to the UI to be rendered visually.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "title": {"type": "string", "description": "Chart title"},
                            "data": {
                                "type": "array",
                                "description": "Array of objects containing 'time' and 'price' or 'value'",
                                "items": {"type": "object"}
                            }
                        },
                        "required": ["title", "data"]
                    }
                }
            }
        ]

        try:
            # Step 1: Call LLM
            response = await self._client.chat.completions.create(
                model=self._model,
                messages=messages,
                tools=tools,
                tool_choice="auto"
            )

            message = response.choices[0].message

            # If no tool calls, just return the text
            if not message.tool_calls:
                return {
                    "role": "assistant",
                    "content": message.content,
                    "type": "text"
                }

            # Step 2: Handle Tool Calls
            tool_results = []
            chart_data = None
            
            # We append the assistant's tool call message to conversation
            messages.append(message)

            for tool_call in message.tool_calls:
                fn_name = tool_call.function.name
                args = json.loads(tool_call.function.arguments)
                result_str = ""

                if fn_name == "get_market_summary":
                    symbol = args.get("symbol", "BTC/USDT")
                    if self._redis:
                        data = await self._redis.get_json("market_summary", symbol.replace("/", "_"))
                        result_str = json.dumps(data) if data else f"No data found for {symbol}"
                    else:
                        result_str = "Redis not connected."

                elif fn_name == "get_open_positions":
                    if self._redis:
                        positions = await self._redis.get_all_positions()
                        result_str = json.dumps(positions) if positions else "No open positions."
                    else:
                        result_str = "Redis not connected."

                elif fn_name == "render_chart":
                    # We capture this to send back as a special UI component
                    chart_data = args
                    result_str = "Chart rendered successfully on user's screen."

                else:
                    result_str = f"Unknown tool: {fn_name}"

                # Append tool result
                messages.append({
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "name": fn_name,
                    "content": result_str
                })

            # Step 3: Call LLM again to synthesize the final response based on tool results
            final_response = await self._client.chat.completions.create(
                model=self._model,
                messages=messages
            )
            
            final_text = final_response.choices[0].message.content

            return {
                "role": "assistant",
                "content": final_text,
                "type": "chart" if chart_data else "text",
                "chart_data": chart_data
            }

        except Exception as e:
            log.error("agent_chat_error", error=str(e))
            return {"role": "assistant", "content": f"System Error: {str(e)}"}
