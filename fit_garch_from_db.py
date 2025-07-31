#!/usr/bin/env python3
"""
fit_garch_from_db.py  (v3: 5-sec feed, JSON output)
---------------------------------------------------
• Pull last N hours of BTC prices from a live SQLite file.
• Clean zeros / NaNs.
• Fit GARCH(1,1) on percent log-returns.
• Save latest parameters to a small JSON file for downstream use.
"""

import argparse, json, shutil, sqlite3, sys, warnings
from datetime import datetime, timezone
from pathlib import Path
from tempfile import NamedTemporaryFile

import numpy as np
from arch import arch_model
from numpy import isfinite

# ─── CLI ────────────────────────────────────────────────────────────────────
p = argparse.ArgumentParser(formatter_class=argparse.ArgumentDefaultsHelpFormatter)
p.add_argument("--src", default="../btc_cache/btc_1s.sqlite",
               help="Path to live btc_1s.sqlite (copied locally, read-only)")
p.add_argument("hours_back", nargs="?", type=int, default=5,
               help="Look-back window in hours")
p.add_argument("--out", default=str(Path.home() / "latest_garch.json"),
               help="Where to write the JSON with fresh parameters")
args = p.parse_args()

if args.hours_back <= 0:
    sys.exit("hours_back must be a positive integer")

src_path = Path(args.src).expanduser().resolve()
if not src_path.is_file():
    sys.exit(f"Source DB not found: {src_path}")

# ─── Fast local copy ───────────────────────────────────────────────────────
tmp = NamedTemporaryFile(prefix="btc_1s_copy_", suffix=".sqlite", delete=True)
shutil.copy2(src_path, tmp.name)

lookback_sec = args.hours_back * 3600

# ─── Helper: load prices ───────────────────────────────────────────────────
def load_prices(db_path: str, seconds_back: int) -> np.ndarray:
    cutoff = int(datetime.now(timezone.utc).timestamp()) - seconds_back
    with sqlite3.connect(f"file:{db_path}?mode=ro", uri=True) as conn:
        rows = conn.execute(
            "SELECT price FROM prices WHERE ts >= ? ORDER BY ts ASC", (cutoff,)
        ).fetchall()
    prices = np.fromiter((r[0] for r in rows), dtype=np.float64)
    prices = prices[isfinite(prices) & (prices > 0)]
    if len(prices) < 2:
        raise RuntimeError("Not enough valid price points.")
    return prices

# ─── Fit GARCH ─────────────────────────────────────────────────────────────
def fit_garch(returns: np.ndarray):
    warnings.filterwarnings("ignore", category=UserWarning)  # silence convergence pep talk
    model = arch_model(returns, mean="Zero", vol="GARCH", p=1, q=1, rescale=False)
    res   = model.fit(disp="off")
    p     = res.params
    return float(p["omega"]), float(p["alpha[1]"]), float(p["beta[1]"])

# ─── Main ──────────────────────────────────────────────────────────────────
try:
    prices = load_prices(tmp.name, lookback_sec)
    log_ret = np.diff(np.log(prices)) * 100.0          # percent units
    log_ret = log_ret[isfinite(log_ret)]
    if len(log_ret) < 700:
        raise RuntimeError("Need ≥ 700 finite returns; only "
                           f"{len(log_ret)} after filtering.")
    omega, alpha1, beta1 = fit_garch(log_ret)

    # pretty print
    print(f"\nGARCH(1,1) fit using last {args.hours_back} h "
          f"({len(log_ret):,d} returns)\n" + "-"*46)
    print(f"omega  (ω) : {omega: .6e}")
    print(f"alpha1 (α₁): {alpha1: .6f}")
    print(f"beta1  (β₁): {beta1: .6f}")
    print("-"*46)

    # save JSON
    out_path = Path(args.out).expanduser()
    out_path.write_text(json.dumps({
        "timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "omega": omega,
        "alpha": alpha1,
        "beta": beta1
    }, indent=2))
except Exception as e:
    sys.stderr.write(f"[ERROR] {e}\n")
    sys.exit(1)

