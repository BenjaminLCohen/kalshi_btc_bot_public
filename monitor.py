#!/usr/bin/env python3
"""
monitor.py – shows BTC spot & 1-hour vol, then six ATM Kalshi BTC contracts
with bid/ask and three Black-Scholes estimates (low, expected, high).

Use:
    python monitor.py              # demo by default
    python monitor.py --env live   # live account
"""

import argparse
import time
from collections import deque
from datetime import datetime, timedelta, timezone
from statistics import mean

from kalshi_client import Kalshi
from contract_picker import pick_six_btc_hourlies
from btc24h_cache import BTC24hCache
from garch_quote_engine import load_garch_params, garch_bid_ask_multi

# ─── instantiate 24 h cache ───────────────────────────────────────────────
cache = BTC24hCache(refresh=1.0)
# ─── command-line flag ────────────────────────────────────────────────────
p = argparse.ArgumentParser()
p.add_argument("--env", choices=["demo", "live"], default="demo",
               help="which Kalshi environment to use")
args = p.parse_args()
k = Kalshi(env=args.env)
params = load_garch_params()

# round-trip times (milliseconds) for Kalshi market data requests
#
# These values update on every API call and offer a simple view into
# the latency between sending a request and receiving data back from
# the exchange. ``api_latencies`` keeps the most recent samples while
# ``last_latency_ms`` stores the latest measurement.
api_latencies: deque[float] = deque(maxlen=100)
last_latency_ms: float = 0.0

# ─── helpers just for pretty output ───────────────────────────────────────
def _print_header(env: str, spot: float, vol: float) -> None:
    avg_latency = mean(api_latencies) if api_latencies else 0.0
    print(
        f"\n[{env.upper()}]  BTC spot ${spot:,.2f}   24-hour vol {vol*100:.2f}%"
    )
    print(f"Avg latency {avg_latency:.2f} ms (last {len(api_latencies)} samples)")
    print("-" * 111)
    print(
        f"{'Contract':<24} | {'Bid/Ask':<11} | {'MC Bid':<8} | {'MC Mid':<8} | {'MC Ask':<8} | {'Lag ms':<7}"
    )
    print("-" * 111)

def _print_row(
    ticker: str,
    bid: float,
    ask: float,
    mc_bid: float,
    mc_mid: float,
    mc_ask: float,
    lag_ms: float,
) -> None:
    """Pretty-print a single market row with latency information."""
    ba = f"{bid:.2f}/{ask:.2f}"
    print(
        f"{ticker:<24} | {ba:<11} | {mc_bid:<8.2f} | {mc_mid:<8.2f} | {mc_ask:<8.2f} | {lag_ms:<7.2f}"
    )
# ─── main loop ────────────────────────────────────────────────────────────
def main():
    global last_latency_ms
    # wait until we have at least one spot price
    while cache.get_spot() is None:
        time.sleep(0.1)

    try:
        while True:
            ts, spot = cache.get_latest()
            if spot is None:
                continue
            data_latency_ms = (time.time() - ts) * 1000
            vol24h = 0.34

            contracts = pick_six_btc_hourlies(k, spot)
            strikes = [c["strike"] for c in contracts]

            now = datetime.now(timezone.utc)
            next_hour = (now + timedelta(hours=1)).replace(minute=0, second=0, microsecond=0)
            seconds_to_hour = int((next_hour - now).total_seconds())

            mc_start = time.perf_counter()
            quotes = garch_bid_ask_multi(
                initial_price=spot,
                base_T=seconds_to_hour,
                spot=spot,
                params=params,
                strikes=strikes,
            )
            mc_time_ms = (time.perf_counter() - mc_start) * 1000

            _print_header(args.env, spot, vol24h)

            quote_map = {q["strike"]: q for q in quotes}

            for c in contracts:
                ticker = c["ticker"]

                send_time = time.perf_counter()
                market = k.get(f"/markets/{ticker}")["market"]
                receive_time = time.perf_counter()
                last_latency_ms = (receive_time - send_time) * 1000
                api_latencies.append(last_latency_ms)

                bid, ask = market["yes_bid"], market["yes_ask"]
                q = quote_map[c["strike"]]
                mc_bid = q["bid"]
                mc_ask = q["ask"]
                mc_mid = (mc_bid + mc_ask) / 2

                _print_row(ticker, bid, ask, mc_bid, mc_mid, mc_ask, last_latency_ms)

            total_latency_ms = (time.time() - ts) * 1000
            print(
                f"Data {data_latency_ms:.2f} ms | MC {mc_time_ms:.2f} ms | "
                f"Last API {last_latency_ms:.2f} ms | Total {total_latency_ms:.2f} ms",
            )
            time.sleep(cache.refresh)

    except KeyboardInterrupt:
        print("\nStopped.")

if __name__ == "__main__":
    main()
