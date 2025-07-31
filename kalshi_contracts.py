from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime
from zoneinfo import ZoneInfo     # needs Python ≥3.9

ET = ZoneInfo("America/New_York")

@dataclass
class ContractId:
    series: str        # KXBTC or KXBTCD
    dt_et: datetime    # event datetime (ET)
    strike: float
    above: bool        # True = ≥ strike

    @classmethod
    def parse(cls, market: str) -> "ContractId":
        # e.g. KXBTC-25JUL3109-B109375
        ser, rest = market.split("-", 1)
        datecode, side_strike = rest.split("-", 1)

        # ---- date decoding ----
        # 25JUL3109  →  2025-07-31 09:00 ET
        year   = 2000 + int(datecode[0:2])
        month  = datetime.strptime(datecode[2:5], "%b").month
        day    = int(datecode[5:7])
        hour   = int(datecode[7:9])
        minute = 0                               # all Kalshi codes end on :00

        dt_et  = datetime(year, month, day, hour, minute, tzinfo=ET)
        above = side_strike[0] in ("B", "T")      # B≥ for hourly, T≥ for daily
        strike = float(side_strike[1:])

        return cls(ser, dt_et, strike, above)

    def market_code(self) -> str:
        y2   = str(self.dt_et.year)[2:]
        mmm  = self.dt_et.strftime("%b").upper()
        dd   = f"{self.dt_et.day:02d}"
        hh   = f"{self.dt_et.hour:02d}"
        side = ("B" if self.series == "KXBTC" else "T") if self.above else (
               "S" if self.series == "KXBTC" else "B")
        strike_txt = f"{self.strike:0.2f}"
        return f"{self.series}-{y2}{mmm}{dd}{hh}-{side}{strike_txt}"
