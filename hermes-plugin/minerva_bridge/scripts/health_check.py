#!/usr/bin/env python3
"""
Minerva Bridge — Startup Health Check.

Verifies that the Minerva MCP Server is running and reachable
when Hermes Agent starts. Prints status to Hermes log.
"""

import sys
import urllib.request
import json

MCP_HEALTH_URL = "http://127.0.0.1:9100/mcp/health"
TIMEOUT_SECONDS = 5


def check_minerva_health() -> bool:
    """Check if Minerva MCP Server is reachable."""
    try:
        req = urllib.request.Request(MCP_HEALTH_URL)
        with urllib.request.urlopen(req, timeout=TIMEOUT_SECONDS) as resp:
            if resp.status == 200:
                data = json.loads(resp.read().decode())
                tools_count = data.get("tools_available", 0)
                print(
                    f"✅ Minerva MCP Bridge is online. "
                    f"{tools_count} tools available."
                )
                return True
            else:
                print(
                    f"⚠️  Minerva MCP Bridge returned status {resp.status}"
                )
                return False
    except urllib.error.URLError as e:
        print(
            f"❌ Cannot reach Minerva MCP Bridge at {MCP_HEALTH_URL}: {e.reason}"
        )
        print(
            "   Make sure Minerva AI is running with MCP_SERVER_ENABLED=true"
        )
        return False
    except Exception as e:
        print(f"❌ Minerva health check failed: {e}")
        return False


if __name__ == "__main__":
    is_healthy = check_minerva_health()
    # Don't exit with error — Hermes should still start even if Minerva is down
    sys.exit(0)
