#!/usr/bin/env python3
"""
contract_picker.py
Utility functions to pick the six BTC hourly contracts (3 below, 3 above spot)
for the NEXT full hour in America/New_York.

Usage
-----
    from contract_picker import pick_six_btc_hourlies, SERIES

    contracts = pick_six_btc_hourlies(kalshi_client, spot_price)
    for c in contracts:
        print(c["ticker"], c["bid"], c["ask"])
"""
from datetime import datetime, timezone, timedelta
from zoneinfo import ZoneInfo
import math

SERIES = "KXBTCD"                        # Kalshi BTC hourly series
STRIKE_INTERVAL = 250                    # $250 strike spacing

# -------------------------------------------------------------------------
def _next_hour_et() -> datetime:
    """Return the next full hour in Eastern Time (aware datetime)."""
    now_et = datetime.now(timezone.utc).astimezone(ZoneInfo("America/New_York"))
    return (now_et.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1))

def _series_code(series: str = SERIES) -> str:
    """e.g. 'KXBTCD-29JUL2518' """
    return _next_hour_et().strftime(f"{series}-%y%b%d%H").upper()

def _six_tickers(series_code: str, spot: float, interval: int = STRIKE_INTERVAL) -> list[str]:
    """3 strikes below & 3 above the nearest interval around spot."""
    base = math.ceil(spot / interval) * interval
    return [f"{series_code}-T{base+d*interval-0.01:.2f}" for d in (-3,-2,-1,0,1,2)]

def _fetch_market(kalshi, ticker: str) -> dict:
    """GET /markets/{ticker} via the shared Kalshi client."""
    return kalshi.get(f"/markets/{ticker}")["market"]

# -------------------------------------------------------------------------
def pick_six_btc_hourlies(kalshi, spot: float, interval: int = STRIKE_INTERVAL) -> list[dict]:
    """
    Returns a list of six dicts:
        {ticker, strike, bid, ask, expiry}
    """
    tickers = _six_tickers(_series_code(), spot, interval)
    contracts = []
    for t in tickers:
        try:
            m = _fetch_market(kalshi, t)
            contracts.append({
                "ticker": t,
                "strike": float(t.split('-T')[-1]) + 0.01,
                "bid":    m["yes_bid"] / 100,
                "ask":    m["yes_ask"] / 100,
                "expiry": m["expiration_time"],
            })
        except Exception:
            # silently skip if market not listed yet
            continue
    return contracts
