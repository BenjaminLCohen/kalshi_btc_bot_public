#!/usr/bin/env python3
"""
List your filled Kalshi positions.

• Uses the shared helper `Kalshi` for auth + signing.
• Swap between demo and live with --env flag (default: demo).
"""

import argparse
from kalshi_client import Kalshi          # <- single import

# ─── parse CLI flag ───────────────────────────────────────────────────────
parser = argparse.ArgumentParser()
parser.add_argument("--env", choices=["demo", "live"], default="demo",
                    help="demo (paper) or live account")
args = parser.parse_args()

# ─── create client & request positions ───────────────────────────────────
k   = Kalshi(env=args.env)
res = k.get("/portfolio/positions")

# combine both arrays the API returns
pos = res.get("event_positions", []) + res.get("market_positions", [])

# ─── pretty-print ─────────────────────────────────────────────────────────
print(f"\n=== {len(pos)} filled position(s) in {args.env} ===\n")
for p in pos:
    ticker = p.get("event_ticker") or p.get("ticker") or "<unknown>"
    qty    = p.get("position", p.get("event_exposure", 0))
    pnl    = (p.get("realized_pnl", 0) or 0) / 100          # cents→dollars
    print(f"{ticker:<22}  qty:{qty:>6}  P&L:${pnl:>7.2f}")
