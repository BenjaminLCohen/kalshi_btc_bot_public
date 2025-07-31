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
from datetime import datetime, timedelta, timezone
from statistics import mean

from kalshi_client import Kalshi
from contract_picker import pick_six_btc_hourlies
from black_scholes import bs_digital_24h   # signature: (S0, K, T, sigma_24h, sigma_err)
from btc24h_cache import BTC24hCache
from volatility import VolatilityMetrics

# ─── instantiate 24 h cache ───────────────────────────────────────────────
cache = BTC24hCache(refresh=1.0)
vols  = VolatilityMetrics.from_cache(cache)
# ─── command-line flag ────────────────────────────────────────────────────
p = argparse.ArgumentParser()
p.add_argument("--env", choices=["demo", "live"], default="demo",
               help="which Kalshi environment to use")
args = p.parse_args()
k = Kalshi(env=args.env)

# ─── helpers just for pretty output ───────────────────────────────────────
def _print_header(env: str, spot: float, vol: float) -> None:
    print(f"\n[{env.upper()}]  BTC spot ${spot:,.2f}   24-hour vol {vol*100:.2f}%")
    print("-"*100)
    print(f"{'Contract':<24} | {'Bid/Ask':<11} | {'BS Low':<8} | {'BS Mid':<8} | {'BS High':<8}")
    print("-"*100)

def _print_row(ticker: str, bid: float, ask: float,
               low: float, mid: float, high: float) -> None:
    ba = f"{bid:.2f}/{ask:.2f}"
    print(f"{ticker:<24} | {ba:<11} | {low:<8.2f} | {mid:<8.2f} | {high:<8.2f}")

from datetime import datetime, timezone

def _to_dt(expiry):
    # Accept either ISO-8601 string or datetime already
    if isinstance(expiry, str):
        # handle the trailing “Z” (UTC) → “+00:00”
        return datetime.fromisoformat(expiry.replace("Z", "+00:00"))
    return expiry

# ─── main loop ────────────────────────────────────────────────────────────
def main():
    # wait until we have at least one spot price
    while cache.get_spot() is None:
        time.sleep(0.1)

    try:
        while True:
            spot = cache.get_spot()
            sigma_err  = 0.34       # 1-minute if available, else fallback
            vol24h = 0.34
            _print_header(args.env, spot, vol24h)

            contracts = pick_six_btc_hourlies(k, spot)
            # --- inside main() loop ---
            for c in contracts:
                 ticker = c["ticker"]        # was: c.ticker
                 market = k.get(f"/markets/{ticker}")["market"]
                 bid, ask = market["yes_bid"], market["yes_ask"]
                 # now = datetime.now(timezone.utc)
                 # expiry_dt = _to_dt(c["expiry"])
                 # T_years = max((expiry_dt - now).total_seconds(), 0) / (365*24*3600)

                 now = datetime.now(timezone.utc)

                 # ── NEW: seconds until the next top-of-hour ──────────────────────
                 next_hour = (now + timedelta(hours=1)).replace(minute=0, second=0, microsecond=0)
                 seconds_to_hour = (next_hour - now).total_seconds()
                 T_years = seconds_to_hour / (365 * 24 * 3600)

                 # --- Black-Scholes mid / band ---------------------------
                 mid, low, high = bs_digital_24h(
                    S0       = spot,
                    K        = c["strike"],
                    T        = T_years,
                    sigma_24h= vol24h,
                )

                 _print_row(ticker, bid, ask, low, mid, high)
            time.sleep(cache.refresh)

    except KeyboardInterrupt:
        print("\nStopped.")

if __name__ == "__main__":
    main()
