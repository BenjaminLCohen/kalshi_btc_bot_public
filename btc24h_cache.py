#!/usr/bin/env python3
import threading, requests, time, math
from collections import deque
from datetime import datetime, timezone
from statistics import mean

SECS_PER_YEAR = 365 * 24 * 3600

class BTC24hCache:
    def __init__(self, refresh: float = 1.0):
        self.refresh = refresh
        self._buffer = deque(maxlen=86400)
        self._lock   = threading.Lock()
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

    def _run(self):
        while True:
            spot = self._fetch_spot()
            if spot is not None:
                with self._lock:
                    self._buffer.append((time.time(), spot))
            time.sleep(self.refresh)

    def get_spot(self):
        with self._lock:
            return self._buffer[-1][1] if self._buffer else None

    def get_latest(self):
        """Return tuple ``(timestamp, spot)`` of the most recent sample."""
        with self._lock:
            return self._buffer[-1] if self._buffer else (None, None)

    def get_vol(self, window_sec: float):
        cutoff = time.time() - window_sec
        with self._lock:
            pts = [p for (t,p) in self._buffer if t >= cutoff]
        if len(pts) < 2:
            return None
        rets  = [math.log(pts[i]/pts[i-1]) for i in range(1, len(pts))]
        mu    = mean(rets)
        sigma = math.sqrt(mean((r-mu)**2 for r in rets))
        return sigma * math.sqrt(SECS_PER_YEAR / self.refresh)

if __name__ == "__main__":
    cache = BTC24hCache()
    time.sleep(5)
    try:
        while True:
            spot = cache.get_spot()
            v1m  = cache.get_vol(60)
            v1h  = cache.get_vol(3600)
            v24h = cache.get_vol(86400)
            ts   = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
            print(f"{ts}  spot={spot:.2f}  1m={v1m:.2%}  1h={v1h:.2%} 24h={v24h:.2%}")
            time.sleep(1)
    except KeyboardInterrupt:
        print("Stopped.")
