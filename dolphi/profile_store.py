"""Investor profile persistence + hotkey-style interactive prompts.

Default storage path: ``~/.dolphi/profile.json``. The same file can be
inspected / edited by hand; the loader is tolerant of missing keys
(older profiles get sensible defaults).

Prompting style: every choice prompt shows ``[U]SD / [E]UR / [A]ED``
letters in line with the options, and accepts the letter, the full
value, or press-Enter for the default. Free-text validation (currency
codes, asset class lists) is strict — bad input is re-prompted, not
silently accepted.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

import click

from .models import UserProfile

logger = logging.getLogger(__name__)


# ---------- constants ---------------------------------------------------------


DEFAULT_PROFILE_PATH = Path.home() / ".dolphi" / "profile.json"

# Letter-keyed currency menu. Press Enter or "U" or "USD" — all return "USD".
_CURRENCY_CHOICES: tuple[tuple[str, str], ...] = (
    ("U", "USD"),
    ("E", "EUR"),
    ("G", "GBP"),
    ("A", "AED"),
    ("S", "SAR"),
    ("J", "JPY"),
    ("C", "CAD"),
)

_GOAL_CHOICES: tuple[tuple[str, str], ...] = (
    ("R", "retirement"),
    ("G", "growth"),
    ("I", "income"),
    ("O", "other"),
)

_RISK_CHOICES: tuple[tuple[str, str], ...] = (
    ("A", "Aggressive"),
    ("M", "Moderate"),
    ("C", "Conservative"),
)

_ASSET_CHOICES: tuple[tuple[str, str], ...] = (
    ("S", "stocks"),
    ("E", "etfs"),
    ("B", "bonds"),
    ("C", "crypto"),
)


# ---------- formatting helpers ------------------------------------------------


def _render_letter_menu(choices: tuple[tuple[str, str], ...]) -> str:
    """Format a menu like '[U]SD / [E]UR / [G]BP'."""
    return " / ".join(f"[{letter}]{name[1:]}" if name.upper().startswith(letter.upper())
                      else f"[{letter}]{name}"
                      for letter, name in choices)


def _resolve_letter(value: str, choices: tuple[tuple[str, str], ...]) -> str | None:
    """Map a user input (letter, full name, or case-insensitive value) to its canonical form."""
    v = value.strip()
    if not v:
        return None
    v_upper = v.upper()
    # Letter shortcut.
    for letter, name in choices:
        if v_upper == letter.upper():
            return name
    # Full name match.
    for _, name in choices:
        if v_upper == name.upper():
            return name
    return None


def _parse_assets(raw: str) -> list[str] | None:
    """Parse an asset-class input. Accepts 'stocks,etfs' or 'se' or 's e'."""
    raw = raw.strip()
    if not raw:
        return None
    tokens = [t for t in raw.replace(",", " ").split() if t]
    out: list[str] = []
    by_letter = {letter.upper(): name for letter, name in _ASSET_CHOICES}
    by_name = {name.lower(): name for _, name in _ASSET_CHOICES}
    for token in tokens:
        if token.upper() in by_letter:
            choice = by_letter[token.upper()]
            if choice not in out:
                out.append(choice)
        elif token.lower() in by_name:
            choice = by_name[token.lower()]
            if choice not in out:
                out.append(choice)
        elif len(token) > 1:
            # Treat 'se' as 's' + 'e' if every character maps.
            letters = list(token.upper())
            if all(letter in by_letter for letter in letters):
                for letter in letters:
                    choice = by_letter[letter]
                    if choice not in out:
                        out.append(choice)
            else:
                return None
    return out or None


def _parse_money(raw: str) -> float | None:
    """Accept '900,000', '$3000', '5_000', '900k', '1.2m'."""
    s = raw.strip().lower().replace("$", "").replace(",", "").replace("_", "").replace(" ", "")
    if not s:
        return None
    multiplier = 1.0
    if s.endswith("k"):
        multiplier = 1_000.0
        s = s[:-1]
    elif s.endswith("m"):
        multiplier = 1_000_000.0
        s = s[:-1]
    elif s.endswith("b"):
        multiplier = 1_000_000_000.0
        s = s[:-1]
    try:
        return float(s) * multiplier
    except ValueError:
        return None


# ---------- low-level prompts -------------------------------------------------


def prompt_money(label: str, default: float | None = None) -> float:
    """Prompt for a money amount; tolerate commas, $, k/m/b suffixes."""
    while True:
        raw = click.prompt(
            label,
            default=("" if default is None else f"{default:,.0f}"),
            show_default=default is not None,
        )
        value = _parse_money(raw)
        if value is not None and value >= 0:
            return value
        click.echo("  Enter a non-negative number (e.g. 900000, 900,000, $3k).")


def prompt_letter_choice(
    label: str,
    choices: tuple[tuple[str, str], ...],
    default: str,
) -> str:
    """Prompt with letter shortcuts; return canonical value."""
    menu = _render_letter_menu(choices)
    while True:
        raw = click.prompt(f"{label} ({menu})", default=default, show_default=True)
        resolved = _resolve_letter(raw, choices)
        if resolved is not None:
            return resolved
        # Allow a raw 3-letter currency code if not in the menu — but keep it
        # gated to the currency context (the alphabetic check).
        if choices is _CURRENCY_CHOICES and raw.strip().isalpha() and len(raw.strip()) == 3:
            return raw.strip().upper()
        valid = ", ".join(name for _, name in choices)
        click.echo(f"  Enter one of: {valid}.")


def prompt_assets(default: list[str]) -> list[str]:
    menu = _render_letter_menu(_ASSET_CHOICES)
    default_str = ",".join(default)
    while True:
        raw = click.prompt(
            f"Asset classes ({menu}). Letters or names; multiple OK.",
            default=default_str,
            show_default=True,
        )
        parsed = _parse_assets(raw)
        if parsed is not None:
            return parsed
        click.echo("  Enter one or more of: stocks, etfs, bonds, crypto.")


def prompt_percentage(label: str, default: float) -> float:
    while True:
        raw = click.prompt(label, default=f"{default:.0f}", show_default=True)
        cleaned = raw.strip().rstrip("%").strip()
        try:
            value = float(cleaned)
        except ValueError:
            click.echo("  Enter a number between 0 and 100.")
            continue
        if 0 <= value <= 100:
            return value
        click.echo("  Must be between 0 and 100.")


# ---------- persistence -------------------------------------------------------


def load_profile(path: Path | None = None) -> UserProfile | None:
    """Load a saved profile. Returns None if missing or unreadable.

    Tolerates older profiles missing ``investment_percentage`` by filling in
    the default of 100 (deploy everything).
    """
    target = Path(path) if path else DEFAULT_PROFILE_PATH
    if not target.exists():
        return None
    try:
        raw = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning("Could not read profile %s: %s", target, exc)
        return None
    if not isinstance(raw, dict):
        return None
    try:
        profile: UserProfile = {
            "total_savings": float(raw["total_savings"]),
            "monthly_salary": float(raw["monthly_salary"]),
            "currency": str(raw["currency"]).upper(),
            "goal": str(raw["goal"]).lower(),
            "risk_tolerance": str(raw["risk_tolerance"]).capitalize(),
            "preferred_asset_classes": [str(a).lower() for a in raw["preferred_asset_classes"]],
            "investment_percentage": float(raw.get("investment_percentage", 100.0)),
        }
    except (KeyError, TypeError, ValueError) as exc:
        logger.warning("Profile %s is malformed: %s", target, exc)
        return None
    return profile


def save_profile(profile: UserProfile, path: Path | None = None) -> Path:
    target = Path(path) if path else DEFAULT_PROFILE_PATH
    target.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "total_savings": float(profile["total_savings"]),
        "monthly_salary": float(profile["monthly_salary"]),
        "currency": str(profile["currency"]).upper(),
        "goal": str(profile["goal"]).lower(),
        "risk_tolerance": str(profile["risk_tolerance"]).capitalize(),
        "preferred_asset_classes": list(profile["preferred_asset_classes"]),
        "investment_percentage": float(profile.get("investment_percentage", 100.0)),
    }
    target.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return target


# ---------- high-level flow ---------------------------------------------------


def format_profile_summary(profile: UserProfile) -> str:
    currency = profile["currency"]
    savings = profile["total_savings"]
    salary = profile["monthly_salary"]
    pct = profile.get("investment_percentage", 100.0)
    invested = savings * pct / 100.0
    assets = ", ".join(profile["preferred_asset_classes"]) or "—"
    lines = [
        f"  Total savings:    {savings:,.0f} {currency}",
        f"  Monthly salary:   {salary:,.0f} {currency}",
        f"  Goal:             {profile['goal']}     |  Risk: {profile['risk_tolerance']}",
        f"  Invest:           {pct:.0f}% of savings  ({invested:,.0f} {currency})",
        f"  Asset classes:    {assets}",
    ]
    return "\n".join(lines)


def prompt_for_profile(saved: UserProfile | None = None) -> UserProfile:
    """Interactive prompt. If ``saved`` is provided, every field defaults to its current value."""
    click.echo()
    if saved is None:
        click.echo("Let's build your investor profile. Press Enter to accept any default in [brackets].")
    else:
        click.echo("Edit your profile. Press Enter to keep each current value.")
    click.echo()

    s = saved or {}
    currency_default = str(s.get("currency", "USD")).upper()
    currency = prompt_letter_choice("Currency", _CURRENCY_CHOICES, default=currency_default)

    savings = prompt_money(
        f"Total savings ({currency})",
        default=float(s["total_savings"]) if "total_savings" in s else None,
    )
    salary = prompt_money(
        f"Monthly salary ({currency})",
        default=float(s["monthly_salary"]) if "monthly_salary" in s else None,
    )
    goal = prompt_letter_choice(
        "Investment goal",
        _GOAL_CHOICES,
        default=str(s.get("goal", "growth")).lower(),
    )
    risk = prompt_letter_choice(
        "Risk tolerance",
        _RISK_CHOICES,
        default=str(s.get("risk_tolerance", "Moderate")).capitalize(),
    )
    assets = prompt_assets(
        default=list(s.get("preferred_asset_classes", ["stocks", "etfs"])),
    )
    invest_pct = prompt_percentage(
        "% of savings to invest (the rest stays in cash)",
        default=float(s.get("investment_percentage", 70.0)),
    )

    return UserProfile(
        total_savings=savings,
        monthly_salary=salary,
        currency=currency,
        goal=goal,
        risk_tolerance=risk,
        preferred_asset_classes=assets,
        investment_percentage=invest_pct,
    )


def resolve_profile(
    *,
    path: Path | None = None,
    force_new: bool = False,
    force_edit: bool = False,
    interactive: bool = True,
) -> UserProfile:
    """Top-level entry the CLI calls.

    Behaviour:
    - If ``force_new``: always prompt fresh (existing profile is overwritten on save).
    - If ``force_edit``: load existing as defaults, walk the user through.
    - Otherwise: if a profile exists, ask [Y]es / [E]dit / [N]ew (default: Yes).
      If no profile exists, prompt fresh.

    Always saves to ``path`` (or default) before returning.
    """
    target = Path(path) if path else DEFAULT_PROFILE_PATH
    existing = None if force_new else load_profile(target)

    if force_new or existing is None:
        profile = prompt_for_profile(saved=None) if interactive else _require_existing(existing, target)
    elif force_edit:
        profile = prompt_for_profile(saved=existing)
    else:
        click.echo()
        click.echo(f"Existing profile found at {target}:")
        click.echo(format_profile_summary(existing))
        click.echo()
        choice = prompt_letter_choice(
            "Continue with this profile?",
            (("Y", "yes"), ("E", "edit"), ("N", "new")),
            default="yes",
        )
        if choice == "yes":
            profile = existing
        elif choice == "edit":
            profile = prompt_for_profile(saved=existing)
        else:
            profile = prompt_for_profile(saved=None)

    save_path = save_profile(profile, target)
    click.echo(f"Profile saved to {save_path}")
    return profile


def _require_existing(existing: UserProfile | None, target: Path) -> UserProfile:
    if existing is None:
        raise SystemExit(
            f"No saved profile at {target} and --no-interactive was set. "
            f"Run once interactively to create one."
        )
    return existing
