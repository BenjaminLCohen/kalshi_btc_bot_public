#!/usr/bin/env python3
"""
Reusable Monte-Carlo engine:
• simulate once per horizon / param-set
• vectorised pricing of any Above / Below / Between contract
"""

import math, numpy as np
from functools import lru_cache
from kalshi_contracts import ContractId

# ---------- global tuning -------------------------------------------------
DEFAULT_PATHS = 1_000          # keep RAM tiny
DTYPE = np.float32             # lowers RAM by 4×
# -------------------------------------------------------------------------

def _simulate_sma(initial_price: float,
                  T: int,
                  omega: float, alpha: float, beta: float,
                  paths: int = DEFAULT_PATHS) -> np.ndarray:
    """Return vector of SMA(60 s)."""
    var0 = omega / (1 - alpha - beta)
    prices = np.empty((T + 1, paths), dtype=DTYPE)
    variances = np.full(paths, var0, dtype=DTYPE)
    sq_ret    = np.full(paths, var0, dtype=DTYPE)

    prices[0] = initial_price
    z = np.random.default_rng().standard_normal((T, paths), dtype=DTYPE)

    for t in range(T):
        variances = omega + alpha * sq_ret + beta * variances
        variances = np.maximum(variances, 1e-10, out=variances)
        ret = np.sqrt(variances, dtype=DTYPE) * z[t]
        prices[t + 1] = prices[t] * np.exp(ret, dtype=DTYPE)
        sq_ret = ret * ret
    win0 = max(0, T - 59)
    return prices[win0:T + 1].mean(axis=0)      # (paths,)

# ----- cache by (spot, horizon, ω,α,β,paths) so we reuse within 1-second loop
@lru_cache(maxsize=16)
def sma_sample(spot: float, horizon_s: int, omega: float, alpha: float,
               beta: float, paths: int = DEFAULT_PATHS) -> np.ndarray:
    return _simulate_sma(spot, horizon_s, omega, alpha, beta, paths)

# -------------------------------------------------------------------------
def price_above(sample: np.ndarray, strike: float) -> float:
    return float((sample >= strike).mean())

def price_below(sample: np.ndarray, strike: float) -> float:
    return float((sample <= strike).mean())

def price_between(sample: np.ndarray, low: float, high: float) -> float:
    hits = (sample >= low) & (sample <= high)
    return float(hits.mean())
# -------------------------------------------------------------------------
def bid_ask(p_low: float, p_high: float) -> tuple[float, float]:
    """Directional rounding to nearest cent."""
    bid = math.floor(min(p_low, p_high) * 100) / 100
    ask = math.ceil (max(p_low, p_high) * 100) / 100
    return bid, ask

# -------------------------------------------------------------------------
def quote_contracts(spot: float,
                    params: tuple[float, float, float],
                    contracts: list[ContractId],
                    base_T: int,
                    paths: int = DEFAULT_PATHS) -> list[dict]:
    """
    One call → returns bids/asks for an arbitrary list of contracts,
    both Above/Below and Between.
    """
    omega, alpha, beta = params
    horizons = (base_T - 5, base_T + 5)
    # simulate once per horizon
    samples = {T: sma_sample(spot, T, omega, alpha, beta, paths)
               for T in horizons}

    quotes = []
    for c in contracts:
        p_lo = price_above(samples[horizons[0]], c.strike) if c.above \
               else price_below(samples[horizons[0]], c.strike)
        p_hi = price_above(samples[horizons[1]], c.strike) if c.above \
               else price_below(samples[horizons[1]], c.strike)

        bid, ask = bid_ask(p_lo, p_hi)
        quotes.append({"market": c.market_code(), "bid": bid, "ask": ask})
    return quotes
