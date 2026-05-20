"""US equity + ETF universe loader.

Pulls daily NASDAQ-listed and other-listed symbol files from
nasdaqtrader.com (free, no API key) and caches them locally. Falls back
to a small bundled CSV if the network is unavailable so first-run and
offline demos still produce a credible universe.

Symbol file definitions:
https://www.nasdaqtrader.com/trader.aspx?id=symboldirdefs
"""

from __future__ import annotations

import csv
import logging
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Iterable

from ..models import UniverseSymbol

logger = logging.getLogger(__name__)

NASDAQ_LISTED_URL = "https://www.nasdaqtrader.com/dynamic/SymDir/nasdaqlisted.txt"
OTHER_LISTED_URL = "https://www.nasdaqtrader.com/dynamic/SymDir/otherlisted.txt"

_BUNDLED_CSV = Path(__file__).parent / "data" / "us_listed.csv"
_UAE_BUNDLED_CSV = Path(__file__).parent / "data" / "uae_listed.csv"

_EXCHANGE_NAMES = {
    "A": "NYSEAMERICAN",
    "N": "NYSE",
    "P": "NYSEARCA",
    "Z": "CBOE",
    "V": "IEX",
}


def _http_get(url: str, timeout: int = 30) -> str | None:
    try:
        with urllib.request.urlopen(url, timeout=timeout) as response:
            return response.read().decode("utf-8")
    except Exception as exc:
        logger.warning("Failed to fetch %s: %s", url, exc)
        return None


def _parse_nasdaq_listed(text: str) -> list[UniverseSymbol]:
    rows: list[UniverseSymbol] = []
    lines = text.splitlines()
    if not lines:
        return rows
    for line in lines[1:]:
        if line.startswith("File Creation") or not line.strip():
            continue
        parts = line.split("|")
        if len(parts) < 8:
            continue
        symbol, name, _market, test_issue, financial_status, _lot, etf_flag, _next = parts[:8]
        if test_issue == "Y":
            continue
        if financial_status and financial_status not in {"N", ""}:
            continue
        if not symbol or any(ch in symbol for ch in "$."):
            continue
        rows.append(
            {
                "symbol": symbol.strip().upper(),
                "name": name.strip(),
                "asset_type": "etf" if etf_flag == "Y" else "stock",
                "sector": "",
                "industry": "",
                "exchange": "NASDAQ",
                "is_adr": False,
            }
        )
    return rows


def _parse_other_listed(text: str) -> list[UniverseSymbol]:
    rows: list[UniverseSymbol] = []
    lines = text.splitlines()
    if not lines:
        return rows
    for line in lines[1:]:
        if line.startswith("File Creation") or not line.strip():
            continue
        parts = line.split("|")
        if len(parts) < 8:
            continue
        symbol, name, exchange_code, _cqs, etf_flag, _lot, test_issue, _ndq = parts[:8]
        if test_issue == "Y":
            continue
        if not symbol or any(ch in symbol for ch in "$."):
            continue
        rows.append(
            {
                "symbol": symbol.strip().upper(),
                "name": name.strip(),
                "asset_type": "etf" if etf_flag == "Y" else "stock",
                "sector": "",
                "industry": "",
                "exchange": _EXCHANGE_NAMES.get(exchange_code, exchange_code or ""),
                "is_adr": False,
            }
        )
    return rows


def _read_bundled_csv() -> list[UniverseSymbol]:
    if not _BUNDLED_CSV.exists():
        return []
    rows: list[UniverseSymbol] = []
    with _BUNDLED_CSV.open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            rows.append(
                {
                    "symbol": row["symbol"].strip().upper(),
                    "name": row.get("name", "").strip(),
                    "asset_type": row.get("asset_type", "stock").strip().lower() or "stock",
                    "sector": row.get("sector", "").strip(),
                    "industry": row.get("industry", "").strip(),
                    "exchange": row.get("exchange", "").strip(),
                    "is_adr": row.get("is_adr", "").strip().lower() in {"1", "true", "yes", "y"},
                }
            )
    return rows


def _dedupe(symbols: Iterable[UniverseSymbol]) -> list[UniverseSymbol]:
    seen: dict[str, UniverseSymbol] = {}
    for symbol in symbols:
        key = symbol["symbol"]
        if key in seen:
            existing = seen[key]
            if not existing.get("sector") and symbol.get("sector"):
                seen[key] = symbol
            continue
        seen[key] = symbol
    return list(seen.values())


def _merge_overlay(loaded: list[UniverseSymbol], overlay: list[UniverseSymbol]) -> list[UniverseSymbol]:
    by_symbol = {item["symbol"]: dict(item) for item in loaded}
    for entry in overlay:
        key = entry["symbol"]
        target = by_symbol.setdefault(key, dict(entry))
        for field_name in ("sector", "industry", "is_adr", "name"):
            value = entry.get(field_name)
            if value and (not target.get(field_name) or field_name == "is_adr"):
                target[field_name] = value
    return list(by_symbol.values())


def _cache_file(cache_dir: Path, source: str) -> Path:
    cache_dir.mkdir(parents=True, exist_ok=True)
    return cache_dir / f"{source}.txt"


def _fresh(path: Path, max_age_hours: int) -> bool:
    if not path.exists():
        return False
    mtime = datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)
    return datetime.now(tz=timezone.utc) - mtime < timedelta(hours=max_age_hours)


def load_us_listed(
    cache_dir: Path | None = None,
    max_age_hours: int = 24,
    fetch: bool = True,
    enrich_with_bundled: bool = True,
) -> list[UniverseSymbol]:
    """Return the US-listed equity + ETF universe.

    Resolution order:
    1. Fresh cache files under ``cache_dir`` (if ``cache_dir`` and < ``max_age_hours``).
    2. Live HTTPS fetch from nasdaqtrader.com (only if ``fetch`` is True),
       persisted to ``cache_dir`` on success.
    3. The bundled fallback CSV (always tried as a last resort).

    When ``enrich_with_bundled`` is True the bundled CSV is also used to
    overlay sector/industry/ADR metadata onto fetched rows, since
    nasdaqtrader.com does not publish that classification.
    """
    rows: list[UniverseSymbol] = []

    if cache_dir is not None:
        nasdaq_cached = _cache_file(cache_dir, "nasdaqlisted")
        other_cached = _cache_file(cache_dir, "otherlisted")
        if _fresh(nasdaq_cached, max_age_hours) and _fresh(other_cached, max_age_hours):
            try:
                rows = _parse_nasdaq_listed(nasdaq_cached.read_text(encoding="utf-8")) + _parse_other_listed(
                    other_cached.read_text(encoding="utf-8")
                )
            except OSError as exc:
                logger.warning("Cached universe parse failed: %s", exc)
                rows = []

    if not rows and fetch:
        nasdaq_text = _http_get(NASDAQ_LISTED_URL)
        other_text = _http_get(OTHER_LISTED_URL)
        if nasdaq_text and other_text:
            rows = _parse_nasdaq_listed(nasdaq_text) + _parse_other_listed(other_text)
            if cache_dir is not None and rows:
                try:
                    _cache_file(cache_dir, "nasdaqlisted").write_text(nasdaq_text, encoding="utf-8")
                    _cache_file(cache_dir, "otherlisted").write_text(other_text, encoding="utf-8")
                except OSError as exc:
                    logger.warning("Universe cache write failed: %s", exc)

    if not rows:
        logger.warning("Falling back to bundled US-listed universe")
        return _dedupe(_read_bundled_csv())

    if enrich_with_bundled:
        rows = _merge_overlay(rows, _read_bundled_csv())

    return _dedupe(rows)


def load_uae_listed(csv_path: Path | None = None) -> list[UniverseSymbol]:
    """Return the bundled UAE-listed equity universe (DFM + ADX).

    UAE tickers use a ``.AE`` suffix on yfinance (e.g. ``IHC.AE``,
    ``EMAAR.AE``), which is why this loader exists separately from
    :func:`load_us_listed` — the US path strips symbols containing ``.``
    on purpose (corporate-action & special-class noise), but those very
    dots are load-bearing for UAE listings.

    No live HTTPS feed is available without a paid data vendor, so the
    UAE universe is a curated bundled list (top ~28 names by market
    cap across both exchanges). Tickers that yfinance can't price are
    dropped silently downstream by the data fetcher.
    """
    path = Path(csv_path) if csv_path else _UAE_BUNDLED_CSV
    if not path.exists():
        return []
    rows: list[UniverseSymbol] = []
    with path.open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            symbol = row.get("symbol", "").strip().upper()
            if not symbol:
                continue
            rows.append(
                {
                    "symbol": symbol,
                    "name": row.get("name", "").strip(),
                    "asset_type": row.get("asset_type", "stock").strip().lower() or "stock",
                    "sector": row.get("sector", "").strip(),
                    "industry": row.get("industry", "").strip(),
                    "exchange": row.get("exchange", "").strip(),
                    "is_adr": row.get("is_adr", "").strip().lower() in {"1", "true", "yes", "y"},
                }
            )
    return rows


def open_universe(
    cache_dir: Path | None = None,
    max_age_hours: int = 24,
    fetch: bool = True,
    *,
    include_uae: bool = False,
) -> list[UniverseSymbol]:
    """Convenience entry point used by the CLI / pipeline.

    When ``include_uae`` is True, the bundled UAE universe is appended
    to the US universe so the pipeline can rank UAE listings alongside
    US symbols. Currency / asset-class preferences are still honoured
    downstream by the validator.
    """
    rows = load_us_listed(cache_dir=cache_dir, max_age_hours=max_age_hours, fetch=fetch)
    if include_uae:
        rows = _dedupe(rows + load_uae_listed())
    return rows
