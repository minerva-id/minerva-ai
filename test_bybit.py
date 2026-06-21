import asyncio
import ccxt.async_support as ccxt
import os
from dotenv import load_dotenv

load_dotenv()

async def main():
    exchange = ccxt.bybit({
        'apiKey': os.getenv('BYBIT_API_KEY'),
        'secret': os.getenv('BYBIT_API_SECRET'),
        'enableRateLimit': True,
    })
    exchange.set_sandbox_mode(True)
    try:
        await exchange.load_markets()
        print("Markets loaded successfully.")
        balance = await exchange.fetch_balance()
        print("Balance fetched.")
    except Exception as e:
        print(f"Error: {str(e)}")
    finally:
        await exchange.close()

asyncio.run(main())
