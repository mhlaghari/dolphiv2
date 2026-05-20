from __future__ import annotations

from pathlib import Path

from dolphi.universe import loader
from dolphi.universe.loader import (
    _parse_nasdaq_listed,
    _parse_other_listed,
    _read_bundled_csv,
    load_us_listed,
)


_FAKE_NASDAQ = """Symbol|Security Name|Market Category|Test Issue|Financial Status|Round Lot Size|ETF|NextShares
AAPL|Apple Inc. - Common Stock|Q|N|N|100|N|N
TSLA|Tesla, Inc. - Common Stock|Q|N|N|100|N|N
TEST|Test Issue - Common Stock|Q|Y|N|100|N|N
QQQ|Invesco QQQ Trust|G|N|N|100|Y|N
File Creation Time: 2026051902
"""

_FAKE_OTHER = """ACT Symbol|Security Name|Exchange|CQS Symbol|ETF|Round Lot Size|Test Issue|NASDAQ Symbol
TSM|Taiwan Semi - ADR|N|TSM|N|100|N|TSM
SPY|SPDR S&P 500 ETF|P|SPY|Y|100|N|SPY
ZZZ|Suspicious. Bad Symbol|N|ZZZ|N|100|N|ZZZ
BAD.A|Class A Share|N|BAD A|N|100|N|BADA
File Creation Time: 2026051902
"""


def test_parse_nasdaq_listed_drops_test_issues_and_marks_etfs():
    rows = _parse_nasdaq_listed(_FAKE_NASDAQ)
    symbols = {row["symbol"]: row for row in rows}

    assert "AAPL" in symbols
    assert symbols["AAPL"]["asset_type"] == "stock"
    assert symbols["AAPL"]["exchange"] == "NASDAQ"
    assert "TEST" not in symbols
    assert symbols["QQQ"]["asset_type"] == "etf"


def test_parse_other_listed_translates_exchange_codes_and_drops_dot_symbols():
    rows = _parse_other_listed(_FAKE_OTHER)
    symbols = {row["symbol"]: row for row in rows}

    assert symbols["TSM"]["exchange"] == "NYSE"
    assert symbols["SPY"]["asset_type"] == "etf"
    assert symbols["SPY"]["exchange"] == "NYSEARCA"
    assert "BAD.A" not in symbols


def test_bundled_csv_provides_offline_universe():
    bundled = _read_bundled_csv()
    by_symbol = {row["symbol"] for row in bundled}

    assert {"NVDA", "TSM", "ASML", "CEG", "BND", "SPY", "QQQ"}.issubset(by_symbol)
    assert all(row["asset_type"] in {"stock", "etf"} for row in bundled)
    assert any(row["is_adr"] for row in bundled)


def test_load_us_listed_falls_back_to_bundled_when_network_disabled(tmp_path, monkeypatch):
    monkeypatch.setattr(loader, "_http_get", lambda url, timeout=30: None)

    rows = load_us_listed(cache_dir=tmp_path, fetch=True)

    by_symbol = {row["symbol"] for row in rows}
    assert "NVDA" in by_symbol
    assert "TSM" in by_symbol


def test_load_us_listed_prefers_fresh_cache_over_network(tmp_path, monkeypatch):
    (tmp_path / "nasdaqlisted.txt").write_text(_FAKE_NASDAQ, encoding="utf-8")
    (tmp_path / "otherlisted.txt").write_text(_FAKE_OTHER, encoding="utf-8")

    called = {"hit": False}

    def fail(url, timeout=30):
        called["hit"] = True
        raise AssertionError("network should not be called when cache is fresh")

    monkeypatch.setattr(loader, "_http_get", fail)

    rows = load_us_listed(cache_dir=tmp_path, max_age_hours=24, fetch=True, enrich_with_bundled=False)
    by_symbol = {row["symbol"] for row in rows}

    assert called["hit"] is False
    assert {"AAPL", "TSM", "QQQ", "SPY"}.issubset(by_symbol)


def test_load_us_listed_writes_cache_after_network_fetch(tmp_path, monkeypatch):
    def fake_get(url, timeout=30):
        if "nasdaqlisted" in url:
            return _FAKE_NASDAQ
        return _FAKE_OTHER

    monkeypatch.setattr(loader, "_http_get", fake_get)

    rows = load_us_listed(cache_dir=tmp_path, fetch=True, enrich_with_bundled=False)

    assert {row["symbol"] for row in rows}.issuperset({"AAPL", "TSM"})
    assert Path(tmp_path / "nasdaqlisted.txt").read_text(encoding="utf-8") == _FAKE_NASDAQ
    assert Path(tmp_path / "otherlisted.txt").read_text(encoding="utf-8") == _FAKE_OTHER


def test_load_us_listed_overlay_enriches_sector_from_bundled(tmp_path, monkeypatch):
    monkeypatch.setattr(
        loader,
        "_http_get",
        lambda url, timeout=30: _FAKE_NASDAQ if "nasdaqlisted" in url else _FAKE_OTHER,
    )

    rows = load_us_listed(cache_dir=tmp_path, fetch=True, enrich_with_bundled=True)
    by_symbol = {row["symbol"]: row for row in rows}

    assert by_symbol["AAPL"]["sector"] == "Technology"
    assert by_symbol["TSM"]["is_adr"] is True


# ---------- UAE loader --------------------------------------------------------


def test_load_uae_listed_returns_bundled_uae_symbols():
    from dolphi.universe import load_uae_listed
    rows = load_uae_listed()
    assert len(rows) >= 20
    by_symbol = {row["symbol"]: row for row in rows}
    # UAE tickers use the .AE suffix (load-bearing — DON'T strip it).
    assert "IHC.AE" in by_symbol
    assert "EMAAR.AE" in by_symbol
    assert "ADCB.AE" in by_symbol
    # Exchange field distinguishes the two UAE markets.
    exchanges = {row["exchange"] for row in rows}
    assert "ADX" in exchanges
    assert "DFM" in exchanges
    # No symbol should be missing a sector — populated from the bundled CSV.
    for row in rows:
        assert row["sector"], f"{row['symbol']} has no sector"


def test_open_universe_includes_uae_when_flag_is_set(monkeypatch):
    from dolphi.universe.loader import open_universe
    monkeypatch.setattr(
        loader,
        "_http_get",
        lambda url, timeout=30: _FAKE_NASDAQ if "nasdaqlisted" in url else _FAKE_OTHER,
    )
    rows_us = open_universe(fetch=True, include_uae=False)
    rows_with_uae = open_universe(fetch=True, include_uae=True)
    us_symbols = {r["symbol"] for r in rows_us}
    combined = {r["symbol"] for r in rows_with_uae}
    assert "IHC.AE" not in us_symbols
    assert "IHC.AE" in combined
    assert len(combined) > len(us_symbols)
