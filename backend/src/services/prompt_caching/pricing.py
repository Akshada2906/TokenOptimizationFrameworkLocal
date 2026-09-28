"""Transparent, configurable estimated-cost calculations for the POC."""

from __future__ import annotations

import os
from dataclasses import dataclass


def _optional_float(name: str) -> float | None:
    value = os.getenv(name, "").strip()
    return float(value) if value else None


@dataclass(frozen=True)
class Pricing:
    """USD rates per one million tokens, except storage (token-hours)."""

    standard_input_per_m: float | None
    cached_input_per_m: float | None
    output_per_m: float | None
    cache_write_per_m: float | None
    cache_storage_per_m_token_hour: float | None

    @classmethod
    def from_environment(cls) -> "Pricing":
        return cls(
            standard_input_per_m=_optional_float("EXPENSE_CACHE_STANDARD_INPUT_USD_PER_M"),
            cached_input_per_m=_optional_float("EXPENSE_CACHE_CACHED_INPUT_USD_PER_M"),
            output_per_m=_optional_float("EXPENSE_CACHE_OUTPUT_USD_PER_M"),
            cache_write_per_m=_optional_float("EXPENSE_CACHE_CACHE_WRITE_USD_PER_M"),
            cache_storage_per_m_token_hour=_optional_float("EXPENSE_CACHE_STORAGE_USD_PER_M_TOKEN_HOUR"),
        )

    def complete(self) -> bool:
        return all(value is not None for value in (
            self.standard_input_per_m,
            self.cached_input_per_m,
            self.output_per_m,
            self.cache_storage_per_m_token_hour,
        ))

    def rates_for_report(self) -> dict[str, float | None]:
        return {
            "standard_input_usd_per_m": self.standard_input_per_m,
            "cached_input_usd_per_m": self.cached_input_per_m,
            "output_usd_per_m": self.output_per_m,
            "cache_write_usd_per_m": self.cache_write_per_m,
            "storage_usd_per_m_token_hour": self.cache_storage_per_m_token_hour,
        }


def token_cost(tokens: int, price_per_million: float | None) -> float | None:
    return None if price_per_million is None else tokens * price_per_million / 1_000_000
