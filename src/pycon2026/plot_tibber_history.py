# /// script
# dependencies = ["pyTibber", "matplotlib", "aiohttp"]
# ///
"""Plot hourly consumption and price from Tibber in one chart.

Usage:
    uv run plot_tibber_history.py              # last 30 days
    uv run plot_tibber_history.py --days 7
    uv run plot_tibber_history.py --save history.png

The API token is read from TIBBER_TOKEN, or from the .env file in the
repository root (see tibber_token below).
"""

import argparse
import asyncio
import configparser
import os
import sys
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path

import aiohttp
import matplotlib.pyplot as plt
import tibber


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


@dataclass
class Hour:
    """One hour of history: when it started, how much we used, what it cost."""

    start: datetime
    kwh: float
    price: float  # SEK per kWh, incl. VAT
    cost: float  # SEK

    @classmethod
    def from_node(cls, node: dict) -> "Hour":
        return cls(
            start=datetime.fromisoformat(node["from"]),
            kwh=node["consumption"],
            price=node["unitPrice"],
            cost=node["cost"],
        )


def consumption_query(hours: int) -> str:
    # The value goes straight into the query text: pyTibber's execute()
    # posts as a form, so GraphQL variables do not work.
    return f"""
    {{ viewer {{ homes {{
      consumption(resolution: HOURLY, last: {hours}) {{
        nodes {{ from consumption unitPrice cost }}
      }}
    }} }} }}
    """


async def fetch_hours(days: int) -> list[Hour]:
    token = tibber_token()

    async with aiohttp.ClientSession() as session:
        connection = tibber.Tibber(token, websession=session, user_agent="plot_tibber_history")
        await connection.update_info()
        data = await connection.execute(consumption_query(hours=days * 24))

    nodes = data["viewer"]["homes"][0]["consumption"]["nodes"]
    # Hours not yet reported by the grid meter come back with consumption = null.
    return [Hour.from_node(n) for n in nodes if n["consumption"] is not None]


def print_summary(hours: list[Hour]) -> None:
    total_kwh = sum(h.kwh for h in hours)
    total_cost = sum(h.cost for h in hours)
    paid_price = total_cost / total_kwh if total_kwh else 0.0
    flat_price = sum(h.price for h in hours) / len(hours)

    print(f"Period:        {hours[0].start:%Y-%m-%d} to {hours[-1].start:%Y-%m-%d}  ({len(hours)} hours)")
    print(f"Consumption:   {total_kwh:8.1f} kWh")
    print(f"Cost:          {total_cost:8.1f} SEK")
    print(f"Price paid:    {paid_price:8.3f} SEK/kWh  (what you actually paid per kWh)")
    print(f"Average price: {flat_price:8.3f} SEK/kWh  (if you had used the same every hour)")


def plot(hours: list[Hour], save_to: str | None) -> None:
    times = [h.start for h in hours]

    fig, kwh_axis = plt.subplots(figsize=(14, 6))
    kwh_axis.bar(times, [h.kwh for h in hours], width=timedelta(hours=1), align="edge", color="tab:blue", alpha=0.6)
    kwh_axis.set_ylabel("Consumption (kWh per hour)", color="tab:blue")

    price_axis = kwh_axis.twinx()
    price_axis.step(times, [h.price for h in hours], where="post", color="tab:red", linewidth=1)
    price_axis.set_ylabel("Price (SEK/kWh, incl. VAT)", color="tab:red")

    kwh_axis.set_title(f"Tibber consumption and price, {times[0]:%Y-%m-%d} to {times[-1]:%Y-%m-%d}")
    kwh_axis.grid(True, alpha=0.3)
    fig.autofmt_xdate()
    fig.tight_layout()

    if save_to:
        fig.savefig(save_to, dpi=150)
        print(f"Saved plot to {save_to}")
    else:
        plt.show()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--days", type=int, default=30, help="number of days back from now (default 30)")
    parser.add_argument("--save", metavar="FILE", help="save the plot to a file instead of showing it")
    args = parser.parse_args()

    hours = asyncio.run(fetch_hours(args.days))
    if not hours:
        sys.exit("Tibber returned no consumption data.")

    print_summary(hours)
    plot(hours, args.save)


if __name__ == "__main__":
    main()
