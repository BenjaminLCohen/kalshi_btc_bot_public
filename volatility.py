"""
volatility.py
-------------
Unified access to Bitcoin volatility metrics for pricing models.

Design goals
------------
* Provide 1‑minute, 1‑hour, and 24‑hour volatilities from either:
    1. an in‑memory BTC24hCache (preferred for sub‑second latency); or
    2. an online REST source (fallback when cache is cold).
* Surface a weighted effective σ to feed into bs_digital_weighted().
    - By default: 80 % weight on 24 h σ, 20 % weight on 1 h σ.
* Be robust to missing data: re‑normalise weights and warn once.
"""

from __future__ import annotations

import logging
from typing import Optional, Callable

import requests   # only used for optional online fallback


_log = logging.getLogger(__name__)


class VolatilitySource:
    """
    Strategy object that returns a volatility for a given look‑back window.

    A source can be backed by an in‑memory cache, a database, or a REST call.
    """

    def __init__(self, supplier: Callable[[], Optional[float]], label: str):
        self._supplier = supplier
        self.label = label

    def get(self) -> Optional[float]:
        """Return σ as a float (e.g. 0.03 → 3 %) or None if unavailable."""
        try:
            return self._supplier()
        except Exception as exc:           # noqa: BLE001
            _log.warning("vol supplier '%s' failed: %s", self.label, exc)
            return None


# ---------------------------------------------------------------------------


class VolatilityMetrics:
    """
    Unified facade around multiple volatility sources.

    Example
    -------
    >>> cache       = BTC24hCache()   # existing object in your code base
    >>> vol_metrics = VolatilityMetrics.from_cache(cache)
    >>> eff = vol_metrics.effective_sigma()
    """

    def __init__(
        self,
        sigma_1m: VolatilitySource,
        sigma_1h: VolatilitySource,
        sigma_24h: VolatilitySource,
        *,
        w24h: float = 0.8,
        w1h: float = 0.2,
    ):
        self.sigma_1m = sigma_1m
        self.sigma_1h = sigma_1h
        self.sigma_24h = sigma_24h

        if w24h + w1h <= 0:
            raise ValueError("weights must sum to a positive number")
        self.weights = {"24h": w24h, "1h": w1h}

    # ---- factory helpers -------------------------------------------------

    @classmethod
    def from_cache(cls, cache, **kw):
        """Create VolatilityMetrics that prioritises the existing BTC24hCache."""

        def _cache_get(sec):
            return lambda: cache.get_vol(sec)

        return cls(
            sigma_1m=VolatilitySource(_cache_get(60), "cache‑1m"),
            sigma_1h=VolatilitySource(_cache_get(3600), "cache‑1h"),
            sigma_24h=VolatilitySource(_cache_get(86400), "cache‑24h"),
            **kw,
        )

    @classmethod
    def demo_stub(cls, **kw):
        """For unit tests / demos with constant vols."""

        const = lambda v: lambda: v

        return cls(
            sigma_1m=VolatilitySource(const(0.002), "stub‑1m"),
            sigma_1h=VolatilitySource(const(0.02), "stub‑1h"),
            sigma_24h=VolatilitySource(const(0.04), "stub‑24h"),
            **kw,
        )

    # ---- public API ------------------------------------------------------

    def get_1m(self) -> Optional[float]:   # noqa: D401
        """Return 1‑minute σ or None."""
        return self.sigma_1m.get()

    def get_1h(self) -> Optional[float]:
        return self.sigma_1h.get()

    def get_24h(self) -> Optional[float]:
        return self.sigma_24h.get()

    # main consumer utility -----------------------------------------------

    def effective_sigma(self) -> float:
        """
        Weighted average of available volatilities.

        Currently: σ_eff = 0.8·σ_24h + 0.2·σ_1h  (normalised if missing)
        Returns 0.0 when everything is missing.
        """

        sig_24h = self.get_24h()
        sig_1h = self.get_1h()

        # Rescale weights so that missing components are ignored.
        avail = {}
        if sig_24h is not None:
            avail["24h"] = sig_24h
        if sig_1h is not None:
            avail["1h"] = sig_1h

        if not avail:
            return 0.0

        total_w = sum(self.weights[k] for k in avail)
        eff = sum(self.weights[k] * avail[k] for k in avail) / total_w
        return eff

    def error_sigma(self) -> float:
        """
        Sigma used for ±3 σ error bounds.

        We follow the spec: use 1‑minute vol if available, else fall back to 1‑h,
        then 24‑h, then 0.0.
        """
        for getter in (self.get_1m, self.get_1h, self.get_24h):
            val = getter()
            if val is not None:
                return val
        return 0.0


# ---------------------------------------------------------------------------


# ---- online‑fetch helpers -------------------------------------------------
# These are optional examples; swap with your own endpoints as needed.

def _binance_url(symbol: str, window: str) -> str:
    return f"https://api.binance.com/api/v3/avgPrice?symbol={symbol}&window={window}"


def fetch_hour_vol_from_binance(symbol="BTCUSDT") -> Optional[float]:
    """
    Simple illustrative fetch – replace with production feed or CF BRTI.
    """
    try:
        resp = requests.get(_binance_url(symbol, "1h"), timeout=5)
        resp.raise_for_status()
        # you would parse resp.json() and compute σ here
        return None   # placeholder
    except Exception as exc:            # noqa: BLE001
        _log.warning("binance hour vol failed: %s", exc)
        return None
