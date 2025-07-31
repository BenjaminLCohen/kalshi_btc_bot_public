#!/usr/bin/env python3
import time, pathlib, requests
from kalshi_contracts import ContractId
from garch_quote_engine import load_garch_params, quote_for_contract

PARAM_PATH  = pathlib.Path.home() / "latest_garch.json"

# ---- replace these three with your real markets --------------------------
CONTRACT_CODES = [
    "KXBTC-25JUL3109-B109375",
    "KXBTC-25JUL3109-S117875",
    "KXBTCD-25JUL3117-T118749.99",
]
# --------------------------------------------------------------------------

def get_latest_btc_price() -> float:
    data = requests.get(
        "https://api.exchange.coinbase.com/products/BTC-USD/ticker",
        timeout=3
    ).json()
    return float(data["price"])

def seconds_to_top_of_hour() -> int:
    return 3600 - (int(time.time()) % 3600)

def main():
    while True:
        spot   = get_latest_btc_price()
        params = load_garch_params(PARAM_PATH)

        for code in CONTRACT_CODES:
            cid = ContractId.parse(code)
            q   = quote_for_contract(cid, spot, params)
            print(f"{q['market']}  |  Bid {q['bid']:.2f}  Ask {q['ask']:.2f}")

        time.sleep(1)

if __name__ == "__main__":
    main()

