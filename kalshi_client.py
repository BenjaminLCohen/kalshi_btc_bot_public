#!/usr/bin/env python3
"""
Lightweight Kalshi REST client.
Usage:
    from kalshi_client import Kalshi
    k = Kalshi(env="demo")              # or env="live"
    positions = k.get("/portfolio/positions")["positions"]
"""
import os, json, time, base64, hashlib
from pathlib import Path
from typing import Dict, Any
from dotenv import load_dotenv
import requests
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding

class Kalshi:
    def __init__(self, env: str = "demo"):
        dotenv_path = Path.home() / f".env.{env}"
        load_dotenv(dotenv_path, override=True)

        self.base   = os.environ["KALSHI_BASE"]        # domain only
        self._api_prefix = "/trade-api/v2"
        key_id      = os.environ["KALSHI_KEY_ID"]
        pem_path    = Path(os.environ["KALSHI_PRIV_KEY"]).expanduser()

        with pem_path.open("rb") as f:
            self._priv = serialization.load_pem_private_key(f.read(), password=None)
        self._key_id = key_id

    # ---------- internal helpers ----------
    def _sign(self, ts: str, method: str, path: str) -> str:
        msg = f"{ts}{method}{path}".encode()
        sig = self._priv.sign(
            msg,
            padding.PSS(mgf=padding.MGF1(hashes.SHA256()),
                        salt_length=padding.PSS.DIGEST_LENGTH),
            hashes.SHA256(),
        )
        return base64.b64encode(sig).decode()

    def _headers(self, method: str, path: str) -> Dict[str, str]:
        ts  = str(int(time.time() * 1000))
        sig = self._sign(ts, method, self._api_prefix + path)
        return {
            "KALSHI-ACCESS-KEY":       self._key_id,
            "KALSHI-ACCESS-TIMESTAMP": ts,
            "KALSHI-ACCESS-SIGNATURE": sig,
        }

    # ---------- public request wrapper ----------
    def request(self, method: str, path: str, **kw):
        url = f"https://{self.base}{self._api_prefix}{path}"
        resp = requests.request(method, url, headers=self._headers(method, path),
                            timeout=10, **kw)
        resp.raise_for_status()
        return resp.json()
    # convenience shorthands
    def get(self, path: str, **kw):  return self.request("GET",  path, **kw)
    def post(self, path: str, **kw): return self.request("POST", path, **kw)
