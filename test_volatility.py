import pytest
from volatility import VolatilityMetrics, VolatilitySource

def test_error_sigma_handles_zero():
    vm = VolatilityMetrics(
        sigma_1m=VolatilitySource(lambda: 0.0, "1m"),
        sigma_1h=VolatilitySource(lambda: 0.02, "1h"),
        sigma_24h=VolatilitySource(lambda: 0.04, "24h"),
    )
    assert vm.error_sigma() == 0.0


def test_error_sigma_fallback_zero_from_1h():
    vm = VolatilityMetrics(
        sigma_1m=VolatilitySource(lambda: None, "1m"),
        sigma_1h=VolatilitySource(lambda: 0.0, "1h"),
        sigma_24h=VolatilitySource(lambda: 0.04, "24h"),
    )
    assert vm.error_sigma() == 0.0
