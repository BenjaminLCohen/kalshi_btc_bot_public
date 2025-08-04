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
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from zoneinfo import ZoneInfo
from typing import List

from kalshi_contracts import ContractId

SERIES = "KXBTCD"                        # Kalshi BTC hourly series


@dataclass
class LiveContract:
    """Simplified view of a Kalshi market used by the bot."""
    ticker: str
    lower: float
    upper: float
    type: str           # "above", "below", "between"
    bid: float
    ask: float
    expiry: int


# -------------------------------------------------------------------------
def _next_hour_et() -> datetime:
    """Return the next full hour in Eastern Time (aware datetime)."""
    now_et = datetime.now(timezone.utc).astimezone(ZoneInfo("America/New_York"))
    return (now_et.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1))


def _series_code(series: str = SERIES) -> str:
    """e.g. 'KXBTCD-29JUL2518' """
    return _next_hour_et().strftime(f"{series}-%y%b%d%H").upper()


def _fetch_event_markets(kalshi, series: str = SERIES) -> List[LiveContract]:
    """Pull all markets for the next event from Kalshi."""
    event = _series_code(series)
    resp = kalshi.get("/markets", params={"event_ticker": event})
    markets = []
    for m in resp.get("markets", []):
        cid = ContractId.parse(m["ticker"])
        if cid.above:
            lower, upper, ctype = cid.strike, float("inf"), "above"
        else:
            lower, upper, ctype = float("-inf"), cid.strike, "below"
        markets.append(
            LiveContract(
                ticker=m["ticker"],
                lower=lower,
                upper=upper,
                type=ctype,
                bid=m["yes_bid"] / 100,
                ask=m["yes_ask"] / 100,
                expiry=m["expiration_time"],
            )
        )
    markets.sort(key=lambda c: c.lower)
    # reconstruct between bins
    strikes = sorted({c.lower for c in markets if c.type == "above"} |
                     {c.upper for c in markets if c.type == "below"})
    for lo, hi in zip(strikes, strikes[1:]):
        markets.append(
            LiveContract(
                ticker=f"BETWEEN_{lo}_{hi}",
                lower=lo,
                upper=hi,
                type="between",
                bid=0.0,
                ask=0.0,
                expiry=markets[0].expiry if markets else 0,
            )
        )
    markets.sort(key=lambda c: c.lower)
    return markets


def pick_six_btc_hourlies(kalshi, spot: float) -> list[dict]:
    """Return three contracts below and above the spot using live strikes."""
    contracts = _fetch_event_markets(kalshi)
    below = [c for c in contracts if c.type == "below" and c.upper <= spot]
    above = [c for c in contracts if c.type == "above" and c.lower >= spot]
    below = sorted(below, key=lambda c: c.upper, reverse=True)[:3]
    above = sorted(above, key=lambda c: c.lower)[:3]
    sel = list(reversed(below)) + above
    return [
        {
            "ticker": c.ticker,
            "strike": c.upper if c.type == "below" else c.lower,
            "bid": c.bid,
            "ask": c.ask,
            "expiry": c.expiry,
        }
        for c in sel
    ]
