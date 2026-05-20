"""Tests for the investor-profile persistence + prompt helpers."""

from __future__ import annotations

import json
from pathlib import Path

import click
import pytest

from dolphi.profile_store import (
    _parse_assets,
    _parse_money,
    _resolve_letter,
    _CURRENCY_CHOICES,
    _GOAL_CHOICES,
    _RISK_CHOICES,
    format_profile_summary,
    load_profile,
    save_profile,
)


# ---------- money parser ------------------------------------------------------


@pytest.mark.parametrize("raw,expected", [
    ("900000", 900_000),
    ("900,000", 900_000),
    ("$900,000", 900_000),
    ("900_000", 900_000),
    ("900k", 900_000),
    ("1.2m", 1_200_000),
    ("2b", 2_000_000_000),
    ("3000", 3000),
    ("  $3,000.50 ", 3000.5),
])
def test_money_parser_accepts_common_shapes(raw, expected):
    assert _parse_money(raw) == pytest.approx(expected)


@pytest.mark.parametrize("raw", ["", "abc", "300x", "$$", "1m2"])
def test_money_parser_rejects_garbage(raw):
    assert _parse_money(raw) is None


# ---------- letter resolution -------------------------------------------------


def test_currency_resolves_letter_and_full_name():
    assert _resolve_letter("U", _CURRENCY_CHOICES) == "USD"
    assert _resolve_letter("u", _CURRENCY_CHOICES) == "USD"
    assert _resolve_letter("USD", _CURRENCY_CHOICES) == "USD"
    assert _resolve_letter("aed", _CURRENCY_CHOICES) == "AED"
    assert _resolve_letter("300", _CURRENCY_CHOICES) is None  # the original bug
    assert _resolve_letter("", _CURRENCY_CHOICES) is None


def test_goal_resolves_letter_and_full_name():
    assert _resolve_letter("R", _GOAL_CHOICES) == "retirement"
    assert _resolve_letter("growth", _GOAL_CHOICES) == "growth"
    assert _resolve_letter("00", _GOAL_CHOICES) is None  # the other original bug


def test_risk_resolves_letter_and_full_name():
    assert _resolve_letter("A", _RISK_CHOICES) == "Aggressive"
    assert _resolve_letter("moderate", _RISK_CHOICES) == "Moderate"
    assert _resolve_letter("xyz", _RISK_CHOICES) is None


# ---------- asset parser ------------------------------------------------------


@pytest.mark.parametrize("raw,expected", [
    ("stocks,etfs", ["stocks", "etfs"]),
    ("s,e", ["stocks", "etfs"]),
    ("S E", ["stocks", "etfs"]),
    ("sb", ["stocks", "bonds"]),
    ("stocks bonds crypto", ["stocks", "bonds", "crypto"]),
    ("STOCKS, BONDS", ["stocks", "bonds"]),
])
def test_asset_parser_accepts_letters_and_names(raw, expected):
    assert _parse_assets(raw) == expected


def test_asset_parser_dedupes():
    assert _parse_assets("s,stocks,S") == ["stocks"]


def test_asset_parser_rejects_unknown():
    assert _parse_assets("nft") is None
    assert _parse_assets("stocks,bogus") is None
    assert _parse_assets("") is None


# ---------- persistence -------------------------------------------------------


def _sample_profile():
    return {
        "total_savings": 900_000.0,
        "monthly_salary": 3000.0,
        "currency": "USD",
        "goal": "income",
        "risk_tolerance": "Moderate",
        "preferred_asset_classes": ["stocks", "etfs"],
        "investment_percentage": 70.0,
    }


def test_save_then_load_round_trips(tmp_path: Path):
    target = tmp_path / "profile.json"
    save_profile(_sample_profile(), target)
    loaded = load_profile(target)
    assert loaded is not None
    assert loaded["total_savings"] == 900_000.0
    assert loaded["currency"] == "USD"
    assert loaded["investment_percentage"] == 70.0


def test_load_missing_file_returns_none(tmp_path: Path):
    assert load_profile(tmp_path / "nope.json") is None


def test_load_tolerates_old_profile_missing_investment_pct(tmp_path: Path):
    target = tmp_path / "profile.json"
    legacy = {k: v for k, v in _sample_profile().items() if k != "investment_percentage"}
    target.write_text(json.dumps(legacy), encoding="utf-8")
    loaded = load_profile(target)
    assert loaded is not None
    assert loaded["investment_percentage"] == 100.0  # backward-compat default


def test_load_rejects_malformed_payload(tmp_path: Path):
    target = tmp_path / "bad.json"
    target.write_text("not a json object", encoding="utf-8")
    assert load_profile(target) is None

    target.write_text(json.dumps({"missing_fields": True}), encoding="utf-8")
    assert load_profile(target) is None


def test_load_coerces_field_types(tmp_path: Path):
    target = tmp_path / "weird.json"
    target.write_text(json.dumps({
        "total_savings": "900000",  # str instead of number
        "monthly_salary": 3000,
        "currency": "usd",          # lowercase
        "goal": "INCOME",            # uppercase
        "risk_tolerance": "moderate",
        "preferred_asset_classes": ["STOCKS"],
    }), encoding="utf-8")
    loaded = load_profile(target)
    assert loaded is not None
    assert loaded["total_savings"] == 900_000.0
    assert loaded["currency"] == "USD"
    assert loaded["goal"] == "income"
    assert loaded["risk_tolerance"] == "Moderate"
    assert loaded["preferred_asset_classes"] == ["stocks"]


# ---------- summary formatting ------------------------------------------------


def test_format_profile_summary_shows_invested_amount():
    summary = format_profile_summary(_sample_profile())
    assert "900,000 USD" in summary
    assert "70% of savings" in summary
    assert "630,000 USD" in summary  # 70% of 900k
    assert "stocks, etfs" in summary


# ---------- integration: full prompt flow -------------------------------------


def test_resolve_profile_full_flow_first_time(tmp_path: Path, monkeypatch):
    """First-time user with no saved profile is taken through the new prompt UX."""
    from dolphi.profile_store import resolve_profile

    target = tmp_path / "profile.json"
    assert not target.exists()

    # Simulate the *exact* sequence the user typed in the bug report — but with
    # the new flow accepting the corrected input on each retry:
    #   Currency: "300" rejected → "U" accepted
    #   Goal:     "00" rejected → "I" accepted
    inputs = iter([
        "300",          # currency, bad
        "U",            # currency, retry → USD
        "900,000",      # savings (parser accepts commas)
        "3k",           # salary (parser accepts k suffix)
        "00",           # goal, bad
        "I",            # goal, retry → income
        "M",            # risk → Moderate
        "se",           # assets → stocks, etfs
        "70",           # investment %
    ])
    monkeypatch.setattr("builtins.input", lambda *a, **k: next(inputs))
    monkeypatch.setattr(click, "prompt", _click_prompt_stub(inputs))

    profile = resolve_profile(path=target, interactive=True)

    assert profile["currency"] == "USD"
    assert profile["total_savings"] == 900_000.0
    assert profile["monthly_salary"] == 3000.0
    assert profile["goal"] == "income"
    assert profile["risk_tolerance"] == "Moderate"
    assert profile["preferred_asset_classes"] == ["stocks", "etfs"]
    assert profile["investment_percentage"] == 70.0
    assert target.exists()


def test_resolve_profile_second_run_offers_keep_edit_new(tmp_path: Path, monkeypatch):
    """Second run with a saved profile asks [Y]es/[E]dit/[N]ew, default keep."""
    from dolphi.profile_store import resolve_profile

    target = tmp_path / "profile.json"
    save_profile(_sample_profile(), target)

    inputs = iter(["Y"])  # accept the saved profile
    monkeypatch.setattr(click, "prompt", _click_prompt_stub(inputs))

    profile = resolve_profile(path=target, interactive=True)

    # Same as the saved one — no re-prompting
    assert profile["currency"] == "USD"
    assert profile["investment_percentage"] == 70.0


def test_resolve_profile_edit_flow_lets_user_change_one_field(tmp_path: Path, monkeypatch):
    """[E]dit accepts the saved values as defaults; user changes only one."""
    from dolphi.profile_store import resolve_profile

    target = tmp_path / "profile.json"
    save_profile(_sample_profile(), target)

    # Choose Edit at the menu, then change risk from Moderate to Aggressive,
    # accept every other field by pressing Enter (click returns the default).
    inputs = iter([
        "E",        # menu → Edit
        "",         # currency → keep USD
        "",         # savings → keep
        "",         # salary → keep
        "",         # goal → keep income
        "A",        # risk → Aggressive
        "",         # assets → keep
        "",         # invest_pct → keep
    ])
    monkeypatch.setattr(click, "prompt", _click_prompt_stub(inputs))

    profile = resolve_profile(path=target, interactive=True)

    assert profile["risk_tolerance"] == "Aggressive"  # changed
    assert profile["currency"] == "USD"               # kept


def _click_prompt_stub(inputs):
    """Build a fake click.prompt that consumes the supplied input iterator
    and honours the ``default=`` argument when the input is empty."""
    def _prompt(_label, default=None, **_kwargs):
        try:
            value = next(inputs)
        except StopIteration:
            raise AssertionError("Test ran out of canned inputs — flow ordering changed?")
        if value == "" and default is not None:
            return default
        return value
    return _prompt
