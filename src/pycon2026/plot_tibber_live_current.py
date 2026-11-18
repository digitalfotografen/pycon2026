# /// script
# dependencies = ["pyTibber", "matplotlib", "aiohttp"]
# ///
"""Live plot of current (A) and voltage (V) on each phase, from a Tibber Pulse.

Current is drawn solid on the left axis, voltage dashed on the right axis.

Usage:
    uv run plot_tibber_live_current.py              # keep the last 10 minutes
    uv run plot_tibber_live_current.py --minutes 30
    uv run plot_tibber_live_current.py --verbose    # print every measurement

Close the plot window to stop.

The API token is read from TIBBER_TOKEN, or from the .env file in the
repository root (see tibber_token below).
"""

import argparse
import asyncio
import configparser
import logging
import os
import sys
import threading
from collections import deque
from datetime import datetime, timedelta
from pathlib import Path

import aiohttp
import matplotlib.pyplot as plt
import tibber
from matplotlib.animation import FuncAnimation

PHASES = ("1", "2", "3")
COLORS = {"1": "tab:brown", "2": "black", "3": "tab:gray"}  # Swedish phase colours
CURRENT = {phase: f"currentL{phase}" for phase in PHASES}  # Tibber field names
VOLTAGE = {phase: f"voltagePhase{phase}" for phase in PHASES}


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


class Readings:
    """Thread-safe rolling buffer of the latest measurements, one deque per phase and quantity."""

    def __init__(self, keep: timedelta) -> None:
        self.keep = keep
        self.times: deque[datetime] = deque()
        self.amps: dict[str, deque[float]] = {phase: deque() for phase in PHASES}
        self.volts: dict[str, deque[float]] = {phase: deque() for phase in PHASES}
        self.lock = threading.Lock()

    def add(self, measurement: dict) -> None:
        now = datetime.fromisoformat(measurement["timestamp"])
        with self.lock:
            self.times.append(now)
            for phase in PHASES:
                self.amps[phase].append(measurement.get(CURRENT[phase]) or 0.0)
                self.volts[phase].append(measurement.get(VOLTAGE[phase]) or 0.0)
            while self.times and now - self.times[0] > self.keep:
                self.times.popleft()
                for phase in PHASES:
                    self.amps[phase].popleft()
                    self.volts[phase].popleft()

    def snapshot(self) -> tuple[list[datetime], dict[str, list[float]], dict[str, list[float]]]:
        with self.lock:
            return (
                list(self.times),
                {phase: list(values) for phase, values in self.amps.items()},
                {phase: list(values) for phase, values in self.volts.items()},
            )


async def subscribe(readings: Readings, verbose: bool) -> None:
    """Connect to Tibber and feed every live measurement into `readings`."""
    async with aiohttp.ClientSession() as session:
        connection = tibber.Tibber(tibber_token(), websession=session, user_agent="plot_tibber_live_current")
        await connection.update_info()
        home = connection.get_homes()[0]
        print(f"Connected to home {home.address1 or home.home_id}")

        def on_measurement(package: dict) -> None:
            data = package.get("data")
            if not data or "liveMeasurement" not in data:
                return
            measurement = data["liveMeasurement"]
            readings.add(measurement)
            if verbose:
                phases = "  ".join(
                    f"L{p} {measurement.get(CURRENT[p]) or 0:5.1f} A {measurement.get(VOLTAGE[p]) or 0:5.1f} V"
                    for p in PHASES
                )
                print(f"{measurement['timestamp']}  {phases}  {measurement.get('power', 0):5.0f} W")

        def on_error(error: Exception) -> None:
            print(f"Subscription problem: {error.__class__.__name__}: {error}", file=sys.stderr)

        # pyTibber checks itself whether the home has a Pulse and reports via on_error.
        await home.rt_subscribe(on_measurement, on_error=on_error)
        print("Subscribed to live measurements, waiting for data. Close the plot window to stop.")
        while True:  # keep the websocket alive until the program exits
            await asyncio.sleep(1)


def start_background_subscription(readings: Readings, verbose: bool) -> None:
    """Run the asyncio subscription in a daemon thread so matplotlib owns the main thread."""

    def run() -> None:
        try:
            asyncio.run(subscribe(readings, verbose))
        except SystemExit as exit_request:  # e.g. missing token: show it instead of dying silently
            print(exit_request, file=sys.stderr)
        except Exception:
            logging.exception("Live subscription stopped")

    threading.Thread(target=run, daemon=True).start()


def live_plot(readings: Readings, minutes: int) -> None:
    fig, amp_axis = plt.subplots(figsize=(12, 5))
    volt_axis = amp_axis.twinx()

    amp_lines = {
        phase: amp_axis.plot([], [], color=COLORS[phase], linewidth=1.5, label=f"L{phase} current")[0]
        for phase in PHASES
    }
    volt_lines = {
        phase: volt_axis.plot([], [], color=COLORS[phase], linewidth=1, linestyle="--", label=f"L{phase} voltage")[0]
        for phase in PHASES
    }
    amp_axis.set_ylabel("Current (A, solid)")
    volt_axis.set_ylabel("Voltage (V, dashed)")
    amp_axis.legend(handles=[*amp_lines.values(), *volt_lines.values()], loc="upper left", ncol=2, fontsize="small")
    amp_axis.grid(True, alpha=0.3)
    fig.autofmt_xdate()

    def update(_frame: int):
        times, amps, volts = readings.snapshot()
        if len(times) < 2:
            return [*amp_lines.values(), *volt_lines.values()]
        for phase in PHASES:
            amp_lines[phase].set_data(times, amps[phase])
            volt_lines[phase].set_data(times, volts[phase])

        latest = times[-1]
        amp_axis.set_xlim(latest - timedelta(minutes=minutes), latest + timedelta(seconds=5))
        peak_amps = max(max(values) for values in amps.values())
        amp_axis.set_ylim(0, max(peak_amps * 1.1, 1.0))
        all_volts = [v for values in volts.values() for v in values if v > 0]
        if all_volts:
            volt_axis.set_ylim(min(all_volts) - 5, max(all_volts) + 5)

        amp_axis.set_title(
            "Live per phase (Tibber Pulse)   "
            + "   ".join(f"L{p}: {amps[p][-1]:4.1f} A / {volts[p][-1]:5.1f} V" for p in PHASES)
            + f"   @ {latest:%H:%M:%S}"
        )
        return [*amp_lines.values(), *volt_lines.values()]

    animation = FuncAnimation(fig, update, interval=1000, cache_frame_data=False)  # noqa: F841 (must stay referenced)
    plt.tight_layout()
    plt.show()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--minutes", type=int, default=10, help="length of the time window to show (default 10)")
    parser.add_argument("--verbose", action="store_true", help="print every measurement to the terminal")
    args = parser.parse_args()

    # pyTibber only reports connection trouble through logging, so make it visible.
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    logging.getLogger("tibber").setLevel(logging.DEBUG if args.verbose else logging.INFO)

    readings = Readings(keep=timedelta(minutes=args.minutes))
    start_background_subscription(readings, args.verbose)
    live_plot(readings, args.minutes)


if __name__ == "__main__":
    main()
