# /// script
# dependencies = ["pyTibber", "matplotlib", "aiohttp"]
# ///
"""Fetch today's Tibber prices (15-minute resolution) and plot them.

Usage:
    export TIBBER_TOKEN=...
    uv run tibber_sample.py
"""

import asyncio
import os
from datetime import datetime

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


async def fetch_today() -> list[dict]:
    token = os.environ["TIBBER_TOKEN"]
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
