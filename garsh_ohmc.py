#!/usr/bin/env python3
import math, random

def mc_digital(S0: float, K: float, T: float, sigma: float, sims: int = 10000) -> float:
    """
    Monte Carlo digital price – GARSH-OHMC flavour (simple GBM).
    Returns the fraction of paths finishing above strike.
    """
    hits = 0
    drift = -0.5 * sigma * sigma * T
    vol   = sigma * math.sqrt(T)
    for _ in range(sims):
        z   = random.gauss(0, 1)
        ST  = S0 * math.exp(drift + vol * z)
        hits += ST > K
    return hits / sims
