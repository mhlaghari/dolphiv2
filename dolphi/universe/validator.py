from __future__ import annotations

from .symbols import find_symbol
from ..models import UniverseSymbol


def allowed_asset_types(profile: dict) -> set[str]:
    preferred = {asset.strip().lower() for asset in profile.get("preferred_asset_classes", [])}
    allowed: set[str] = set()
    if not preferred or "stocks" in preferred:
        allowed.add("stock")
    if not preferred or "etfs" in preferred:
        allowed.add("etf")
    return allowed


def validate_symbol(
    symbol: str,
    universe: list[UniverseSymbol],
    profile: dict | None = None,
) -> UniverseSymbol | None:
    entry = find_symbol(symbol, universe)
    if entry is None:
        return None
    if profile is None:
        return entry
    if entry["asset_type"] not in allowed_asset_types(profile):
        return None
    return entry
