# /// script
# dependencies = ["pyTibber", "matplotlib", "aiohttp"]
# ///
"""Fetch today's Tibber prices (15-minute resolution) and plot them.

Usage:
    uv run plot_tibber_today.py

The API token is read from TIBBER_TOKEN, or from the .env file in the
repository root (see tibber_token below).
"""

import asyncio
import configparser
import os
import sys
from datetime import datetime
from pathlib import Path

import aiohttp
import matplotlib.pyplot as plt
import tibber

# Values are written straight into the query text: pyTibber's execute()
# posts as a form, so GraphQL variables do not work.
QUERY = """
{
  viewer {
    homes {
      currentSubscription {
        priceInfo(resolution: QUARTER_HOURLY) {
          today { startsAt total }
        }
      }
    }
  }
}
"""


def tibber_token() -> str:
    """Return the Tibber API token: TIBBER_TOKEN if set, else api_key from .env.

    The .env file lives in the repository root and looks like:

        [Tibber]
        api_key = <token>

    It is listed in .gitignore, so the token never ends up in the code.
    """
    token = os.environ.get("TIBBER_TOKEN")
    if token:
        return token

    env_file = Path(__file__).resolve().parents[2] / ".env"
    if env_file.is_file():
        config = configparser.ConfigParser()
        config.read(env_file)
        token = config.get("Tibber", "api_key", fallback="").strip()
        if token:
            return token

    sys.exit("No Tibber token found: set TIBBER_TOKEN or put api_key under [Tibber] in .env")


async def fetch_today() -> list[dict]:
    token = tibber_token()
    async with aiohttp.ClientSession() as session:
        connection = tibber.Tibber(token, websession=session, user_agent="plot_tibber_today")
        await connection.update_info()
        data = await connection.execute(QUERY)
    return data["viewer"]["homes"][0]["currentSubscription"]["priceInfo"]["today"]


def plot(prices: list[dict]) -> None:
    times = [datetime.fromisoformat(p["startsAt"]) for p in prices]
    totals = [p["total"] for p in prices]

    plt.figure(figsize=(12, 5))
    plt.step(times, totals, where="post")
    plt.title(f"Tibber price {times[0]:%Y-%m-%d} ({len(prices)} periods)")
    plt.ylabel("SEK/kWh (incl. tax)")
    plt.grid(True, alpha=0.3)
    plt.gcf().autofmt_xdate()
    plt.tight_layout()
    plt.show()


if __name__ == "__main__":
    plot(asyncio.run(fetch_today()))
