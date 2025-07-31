
#!/usr/bin/env python3
"""
btc_feed.py
-----------
Background thread that:

1. Polls Coinbase Pro every 0.5 seconds for BTC‐USD spot
2. Maintains in‐memory deques for 10 s, 1 min, and 5 min realized vols
3. Fetches 1 h and 24 h realized vols via Coinbase Pro candle API
4. get() → (spot, vol_10s, vol_1m, vol_5m, vol_web_1h, vol_web_24h)
"""

import threading
import requests
import time
import math
from collections import deque
from datetime import datetime, timezone, timedelta
from statistics import mean

class BTCVolFeed:
    def __init__(self, refresh: float = 1.0):
        self.refresh       = refresh
        self.spot          = None
        # deques for local windows (0.5 s ticks)
        self._dq_10s       = deque(maxlen=int(10/refresh))
        self._dq_1m        = deque(maxlen=int(60/refresh))
        self._dq_5m        = deque(maxlen=int(5*60/refresh))
        self._lock         = threading.Lock()
        # vol metrics
        self.vol_10s       = None
        self.vol_1m        = None
        self.vol_5m        = None
        self.vol_web_1h    = None
        self.vol_web_24h   = None
        threading.Thread(target=self._run, daemon=True).start()

    def _fetch_spot(self):
        try:
            r = requests.get(
                "https://api.exchange.coinbase.com/products/BTC-USD/ticker",
                timeout=3
            )
            r.raise_for_status()
            return float(r.json()['price'])
        except:
            return None

    def _fetch_historical_vol(self, granularity: int, periods: int):
        """
        granularity in seconds, periods = number of bars
        """
        now   = datetime.now(timezone.utc)
        start = (now - timedelta(seconds=granularity * periods)).isoformat()
        end   = now.isoformat()
        url   = "https://api.exchange.coinbase.com/products/BTC-USD/candles"
        params = {
            "start": start,
            "end":   end,
            "granularity": granularity
        }
        try:
            r = requests.get(url, params=params, timeout=5)
            r.raise_for_status()
            data = r.json()  # [[time, low, high, open, close, vol], ...]
            closes = [c[4] for c in data]
            if len(closes) < 2:
                return None
            rets = [math.log(closes[i] / closes[i-1]) for i in range(1, len(closes))]
            mu   = mean(rets)
            sigma = math.sqrt(mean((r - mu) ** 2 for r in rets))
            return sigma * math.sqrt(len(rets))
        except:
            return None

    def _compute_vol(self, dq: deque):
        if len(dq) < 2:
            return None
        rets = [math.log(dq[i] / dq[i-1]) for i in range(1, len(dq))]
        mu   = mean(rets)
        sigma = math.sqrt(mean((r - mu) ** 2 for r in rets))
        return sigma * math.sqrt(365*24*3600 / self.refresh)

    def _run(self):
        while True:
            spot = self._fetch_spot()
            if spot is not None:
                with self._lock:
                    self.spot = spot
                    # update local-price deques
                    self._dq_10s.append(spot)
                    self._dq_1m.append(spot)
                    self._dq_5m.append(spot)
                    # compute local vols
                    self.vol_10s    = self._compute_vol(self._dq_10s)
                    self.vol_1m     = self._compute_vol(self._dq_1m)
                    self.vol_5m     = self._compute_vol(self._dq_5m)
                    # fetch web vols
                    self.vol_web_1h  = self._fetch_historical_vol(60,   60) * math.sqrt(12*365)
                    self.vol_web_24h = self._fetch_historical_vol(3600, 24) * math.sqrt(365)
            time.sleep(self.refresh)

    def get(self):
        """
        Returns:
          (spot,
           vol_10s, vol_1m, vol_5m,
           vol_web_1h, vol_web_24h)
        """
        with self._lock:
            return (
                self.spot,
                (self.vol_10s,
                self.vol_1m,
                self.vol_5m,
                self.vol_web_1h,
                self.vol_web_24h)
            )

if __name__ == "__main__":
    feed = BTCVolFeed()
    # wait until we have a spot
    while feed.get()[0] is None:
        time.sleep(0.1)

    try:
        while True:
            spot, vols = feed.get()
            (v10, v1, v5, v1h, v24h) =  vols
            ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
            parts = [f"{ts} Spot: {spot:,.2f}"]
            if v10  is not None: parts.append(f"10s-Vol:  {v10*100:.5f}%")
            if v1   is not None: parts.append(f"1m-Vol:   {v1*100:.4f}%")
            if v5   is not None: parts.append(f"5m-Vol:   {v5*100:.4f}%")
            if v1h  is not None: parts.append(f"1h-Vol:   {v1h*100:.3f}%")
            if v24h is not None: parts.append(f"24h-Vol:  {v24h*100:.2f}%")
            print("  ".join(parts))
            time.sleep(feed.refresh)
    except KeyboardInterrupt:
        print("\nStopped.")
