#!/usr/bin/env python3
"""
btc_feed_US_EXC.py
-----------
Background thread that:

1. Every 0.5 seconds pulls BTC/USD spot prices from multiple public US exchanges
2. Stores the last close of each minute of the *average* in a 60-value deque
3. get() -> (avg_spot, vol1h) in O(1)
4. latest prices from each exchange always available in `.latest_prices`
"""

import threading
import requests
import time
import math
from collections import deque
from datetime import datetime, timezone
from statistics import mean

# public, no-auth BTC/USD price endpoints
ENDPOINTS = {
    'coinbase':     'https://api.coinbase.com/v2/prices/BTC-USD/spot',
    'coinbase_pro': 'https://api.exchange.coinbase.com/products/BTC-USD/ticker',
    'kraken':       'https://api.kraken.com/0/public/Ticker?pair=XBTUSD',
    'gemini':       'https://api.gemini.com/v1/pubticker/btcusd',
    'binance_us':   'https://api.binance.us/api/v3/ticker/price?symbol=BTCUSD',
    'bittrex':      'https://api.bittrex.com/v3/markets/BTC-USD/ticker',
    'robinhood':    'https://api.robinhood.com/crypto/quotes/BTCUSD/',
    'itbit':        'https://api.itbit.com/v1/markets/XBTUSD/ticker',
}

class BTCVolFeed:
    def __init__(self, refresh: float = 1.0):
        """
        refresh – seconds between polls (default 0.5 s)
        """
        self.refresh       = refresh
        self.spot          = None
        self._closes       = deque(maxlen=60)
        self._lock         = threading.Lock()
        self.latest_prices = {}
        threading.Thread(target=self._run, daemon=True).start()

    def _fetch_price(self, url, name):
        try:
            r = requests.get(url, timeout=3)
            r.raise_for_status()
            data = r.json()
            if name == 'coinbase':
                return float(data['data']['amount'])
            if name == 'coinbase_pro':
                return float(data['price'])
            if name == 'kraken':
                pair = next(iter(data['result'].values()))
                return float(pair['c'][0])
            if name == 'gemini':
                return float(data['last'])
            if name == 'binance_us':
                return float(data['price'])
            if name == 'bittrex':
                return float(data['lastTradeRate'])
            if name == 'robinhood':
                return float(data.get('last_trade_price') or data.get('mark_price'))
            if name == 'itbit':
                return float(data['lastPrice'])
        except Exception:
            return None

    def _run(self):
        last_minute = None
        while True:
            prices = {}
            for name, url in ENDPOINTS.items():
                p = self._fetch_price(url, name)
                if p is not None:
                    prices[name] = p

            avg_price = sum(prices.values()) / len(prices) if prices else None

            now = datetime.now(timezone.utc)
            with self._lock:
                self.spot          = avg_price
                self.latest_prices = prices.copy()
                if avg_price is not None and (last_minute is None or now.minute != last_minute):
                    self._closes.append(avg_price)
                    last_minute = now.minute

            time.sleep(self.refresh)

    def get(self):
        """
        Returns (avg_spot, vol1h).
        vol1h – annualised σ of log returns of the last 60 minute-closes.
        """
        with self._lock:
            spot   = self.spot
            closes = list(self._closes)

        if spot is None or len(closes) < 2:
            return None, None

        rets  = [math.log(closes[i] / closes[i-1]) for i in range(1, len(closes))]
        mu    = mean(rets)
        sigma = math.sqrt(mean((r - mu)**2 for r in rets))
        vol1h = sigma * math.sqrt(len(rets))
        return spot, vol1h

if __name__ == "__main__":
    feed = BTCVolFeed()
    # wait for first tick
    while True:
        spot, vol1h = feed.get()
        if spot is not None:
            break
        time.sleep(0.1)

    try:
        while True:
            with feed._lock:
                prices = feed.latest_prices.copy()
            ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
            line = "  ".join(f"{name}={price:,.2f}" for name, price in prices.items())
            print(f"{ts}  {line}")
            time.sleep(feed.refresh)
    except KeyboardInterrupt:
        print("\nStopped.")
