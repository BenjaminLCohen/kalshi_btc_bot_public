#!/usr/bin/env python3
"""
Monte-Carlo bid/ask engine  (v2: uses live GARCH params)

• Reads ω, α₁, β₁ from ~/latest_garch.json
• Simulates 5-second GARCH(1,1) paths
• Quotes six strikes at ±250-USD ladder
"""

from __future__ import annotations
import json, math, time, pathlib
import numpy as np

# ── Config ────────────────────────────────────────────────────────────────
PARAM_FILE = pathlib.Path.home() / "latest_garch.json"
INTERVAL_USD = 250.0                      # strike spacing
MC_PATHS = 1_000                         # Monte-Carlo simulations
# -------------------------------------------------------------------------

def load_garch_params(path: pathlib.Path = PARAM_FILE):
    """Return (omega, alpha1, beta1) as floats, raise if file missing."""
    with path.open() as f:
        g = json.load(f)
    return g["omega"], g["alpha"], g["beta"]


# ───────────────────────────────────────────────────────────────────────────
def _simulate_garch_avg(initial_price: float,
                        T: int,
                        omega: float,
                        alpha1: float,
                        beta1: float,
                        num_simulations: int = MC_PATHS) -> np.ndarray:
    """Vectorised GARCH(1,1) simulation, returns 60-sec moving-average."""
    var0   = omega / (1 - alpha1 - beta1)

    prices    = np.empty((T + 1, num_simulations))
    variances = np.full(num_simulations, var0)
    sq_ret    = np.full(num_simulations, var0)

    prices[0] = initial_price
    z = np.random.default_rng().standard_normal((T, num_simulations))

    for t in range(T):
        variances = omega + alpha1 * sq_ret + beta1 * variances
        np.maximum(variances, 1e-10, out=variances)
        returns   = np.sqrt(variances) * z[t]
        prices[t + 1] = prices[t] * np.exp(returns)
        sq_ret = returns * returns

    window_start = max(0, T - 59)
    return prices[window_start:T + 1].mean(axis=0)


def _probs_above_strikes(avg_prices: np.ndarray,
                         strikes: np.ndarray) -> np.ndarray:
    hits = avg_prices >= strikes[:, None]
    return hits.mean(axis=1)


def _six_strikes_around_spot(spot: float,
                             interval: float = INTERVAL_USD) -> np.ndarray:
    anchor  = math.ceil(spot / interval) * interval
    offsets = np.array([-3, -2, -1, 0, 1, 2], dtype=np.float64)
    strikes = anchor + offsets * interval - 0.01
    return strikes


def garch_bid_ask_multi(initial_price: float,
                        base_T: int,
                        spot: float,
                        params: tuple[float, float, float],
                        interval: float = INTERVAL_USD,
                        num_simulations: int = MC_PATHS) -> list[dict]:
    """Return bid/ask quotes for six strikes."""
    omega, alpha1, beta1 = params
    strikes = _six_strikes_around_spot(spot, interval)
    horizons = [base_T - 5, base_T + 5]
    probs = []

    for T in horizons:
        avgs = _simulate_garch_avg(initial_price, T,
                                   omega, alpha1, beta1,
                                   num_simulations)
        probs.append(_probs_above_strikes(avgs, strikes))

    probs = np.vstack(probs)
    bids = np.floor(probs.min(axis=0) * 100) / 100
    asks = np.ceil( probs.max(axis=0) * 100) / 100

    return [{"strike": float(s), "bid": float(b), "ask": float(a)}
            for s, b, a in zip(strikes, bids, asks)]

# ────────────────────────────────────────────────────────────────────
#   Build bid/ask for a single Kalshi contract object
# ────────────────────────────────────────────────────────────────────
def quote_for_contract(contract,
                       spot: float,
                       params: tuple[float, float, float],
                       num_simulations: int = MC_PATHS) -> dict[str, float]:
    """
    Parameters
    ----------
    contract : kalshi_contracts.ContractId
    spot     : current BTC spot
    params   : (omega, alpha1, beta1)
    Returns
    -------
    {'market': <code>, 'bid': x.xx, 'ask': y.yy}
    """
    from datetime import datetime, timezone
    from kalshi_contracts import ET          # local import avoids cycle

    omega, alpha1, beta1 = params

    # --- horizon in seconds (ET → UTC) ----------------------------------
    now_utc = datetime.now(timezone.utc)
    now_et  = now_utc.astimezone(ET)
    T_sec   = int((contract.dt_et - now_et).total_seconds())
    if T_sec <= 10:
        raise ValueError("≤10 s to expiry; skip")

    # --- simulate -------------------------------------------------------
    avgs = _simulate_garch_avg(spot, T_sec,
                               omega, alpha1, beta1,
                               num_simulations)
    p = (avgs >= contract.strike).mean() if contract.above else \
        (avgs <= contract.strike).mean()

    bid = math.floor(p * 100) / 100
    ask = math.ceil (p * 100) / 100

    return {"market": contract.market_code(),
            "bid": bid, "ask": ask}
# ─── Example usage ─────────────────────────────────────────────────────────
if __name__ == "__main__":
    spot = 118_600.00
    secs_left_this_hour = 3600 - (int(time.time()) % 3600)

    try:
        omega, alpha1, beta1 = load_garch_params()
    except FileNotFoundError:
        raise SystemExit("latest_garch.json not found — "
                         "run fit_garch_from_db.py first.")

    quotes = garch_bid_ask_multi(
        initial_price = spot,
        base_T        = secs_left_this_hour,
        spot          = spot,
        params        = (omega, alpha1, beta1),
    )

    for q in quotes:
        print(f"Strike {q['strike']:>10.2f} | Bid {q['bid']:.2f}  Ask {q['ask']:.2f}")
