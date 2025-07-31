#!/usr/bin/env python3
"""Simplified Black‑Scholes digital option pricer.

This version uses **only the 24‑hour realised volatility** (annualised σ) and
computes ±3 σ error bounds by first scaling that daily σ down to the short‑term
standard error:

    σ_error = σ_24h / sqrt(24 * 60 * 20)

The magic factor `24 × 60 × 20 = 28 800` comes from treating the 24‑hour window
as 28 800 non‑overlapping 2‑second slices (feel free to tweak the 20 if you want
a different granularity).  We then add/subtract **three** of those σ_error values
to build conservative lower/upper volatility scenarios.

Returns a tuple → (mid, lower_bound, upper_bound).
"""

import math

__all__ = [
    "bs_digital_24h",
]

SQRT2 = math.sqrt(2.0)
SQRT_ERR_DENOM = math.sqrt(24 * 60 * 20)  # ≈ 169.7
EPS = 1e-10  # fallback for zero‑vol edge cases


def _erf01(x: float) -> float:
    """Map x → Φ(x) for a standard Normal (0–1 CDF)."""
    return 0.5 * (1.0 + math.erf(x / SQRT2))


def bs_digital_24h(S0: float, K: float, T: float, sigma_24h: float):
    """Black‑Scholes digital (cash‑or‑nothing) call.

    Parameters
    ----------
    S0        : spot price (USD)
    K         : strike (USD)
    T         : time to expiry **in years**
    sigma_24h : annualised volatility based on the last 24 hours (σ)

    Returns
    -------
    mid, lower, upper : tuple[float, float, float]
        Fair price and a 3‑σ error band around volatility.
    """

    # Immediate payoff if expired
    if T <= 0:
        payout = 1.0 if S0 > K else 0.0
        return payout, payout, payout

    sigma_eff = max(sigma_24h, EPS)

    sqrtT = math.sqrt(T)
    d2 = (math.log(S0 / K) - 0.5 * sigma_eff ** 2 * T) / (sigma_eff * sqrtT)
    mid_price = _erf01(d2)

    # -----------------------------------------------------
    # Build ±3 σ bounds around the *volatility* (not price)
    # -----------------------------------------------------
    sigma_err = sigma_eff / SQRT_ERR_DENOM  # short‑term σ error

    low_sig = max(sigma_eff - 3.0 * sigma_err, EPS)
    hi_sig  = sigma_eff + 3.0 * sigma_err

    d2_low  = (math.log(S0 / K) - 0.5 * low_sig ** 2 * T) / (low_sig * sqrtT)
    d2_high = (math.log(S0 / K) - 0.5 * hi_sig  ** 2 * T) / (hi_sig  * sqrtT)

    lower = _erf01(d2_low)
    upper = _erf01(d2_high)

    return mid_price, lower, upper


# ---- quick CLI test --------------------------------------------------------
if __name__ == "__main__":
    import argparse, sys

    ap = argparse.ArgumentParser(description="Digital BS with 24‑h σ only")
    ap.add_argument("S0", type=float, help="Spot price")
    ap.add_argument("K",  type=float, help="Strike price")
    ap.add_argument("T",  type=float, help="Time to expiry in YEARS")
    ap.add_argument("sigma24h", type=float, help="Annualised σ from last 24 h")
    ns = ap.parse_args()

    mid, lo, hi = bs_digital_24h(ns.S0, ns.K, ns.T, ns.sigma24h)
    print(f"Mid   : {mid:.5f}\nLower : {lo:.5f}\nUpper : {hi:.5f}")
