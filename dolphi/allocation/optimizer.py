from __future__ import annotations

from ..models import (
    Allocation,
    DebateJudgment,
    PortfolioRecommendation,
    PreMortemFinding,
    RankedIdea,
)


_RISK_CONFIG = {
    "Aggressive": {"max_position": 45.0, "sector_cap": 55.0, "defensive": 10.0},
    "Moderate": {"max_position": 35.0, "sector_cap": 45.0, "defensive": 25.0},
    "Conservative": {"max_position": 30.0, "sector_cap": 35.0, "defensive": 45.0},
}

# How aggressively to discount a fragile idea. 0.75 means at fragility = 1.0
# the weight is multiplied by 0.25; at fragility = 0.5 the weight is halved.
_FRAGILITY_PENALTY = 0.75


def _risk_config(profile: dict) -> dict[str, float]:
    risk = str(profile.get("risk_tolerance", "Moderate")).capitalize()
    return _RISK_CONFIG.get(risk, _RISK_CONFIG["Moderate"])


def _normalize(allocations: list[Allocation]) -> list[Allocation]:
    total = sum(item["allocation_pct"] for item in allocations)
    if total <= 0:
        return allocations
    factor = 100.0 / total
    normalized = [
        {
            "symbol": item["symbol"],
            "allocation_pct": round(item["allocation_pct"] * factor, 1),
            "rationale": item["rationale"],
        }
        for item in allocations
    ]
    drift = round(100.0 - sum(item["allocation_pct"] for item in normalized), 1)
    if normalized and drift:
        normalized[0]["allocation_pct"] = round(normalized[0]["allocation_pct"] + drift, 1)
    return normalized


def _finalize_allocations(allocations: list[Allocation]) -> list[Allocation]:
    allocations = [item for item in allocations if item["allocation_pct"] > 0]
    total = round(sum(item["allocation_pct"] for item in allocations), 1)
    drift = round(100.0 - total, 1)
    if not allocations or not drift:
        return allocations
    if drift > 0:
        for symbol in ("CASH", "BND"):
            for item in allocations:
                if item["symbol"] == symbol:
                    item["allocation_pct"] = round(item["allocation_pct"] + drift, 1)
                    return allocations
        allocations.append({"symbol": "CASH", "allocation_pct": drift, "rationale": "Rounding reserve."})
        return allocations
    reduction = abs(drift)
    for symbol in ("CASH", "BND"):
        for item in allocations:
            if item["symbol"] == symbol and item["allocation_pct"] >= reduction:
                item["allocation_pct"] = round(item["allocation_pct"] - reduction, 1)
                return [allocation for allocation in allocations if allocation["allocation_pct"] > 0]
    largest = max(allocations, key=lambda item: item["allocation_pct"])
    largest["allocation_pct"] = round(max(largest["allocation_pct"] - reduction, 0.0), 1)
    return [allocation for allocation in allocations if allocation["allocation_pct"] > 0]


def _add_allocation(allocations: list[Allocation], allocation: Allocation) -> None:
    for item in allocations:
        if item["symbol"] == allocation["symbol"]:
            item["allocation_pct"] = round(item["allocation_pct"] + allocation["allocation_pct"], 1)
            item["rationale"] = f"{item['rationale']} {allocation['rationale']}"
            return
    allocations.append(allocation)
    return allocations


def _adjusted_score(
    idea: RankedIdea,
    fragility_by_symbol: dict[str, float],
    delta_by_symbol: dict[str, float],
) -> float:
    base = idea["score"] + delta_by_symbol.get(idea["symbol"], 0.0)
    base = max(base, 0.05)
    fragility = max(0.0, min(1.0, fragility_by_symbol.get(idea["symbol"], 0.0)))
    return base * max(0.05, 1.0 - fragility * _FRAGILITY_PENALTY)


def _fragility_note(symbol: str, fragility: float, fragility_by_symbol: dict[str, float]) -> str:
    if symbol not in fragility_by_symbol:
        return ""
    if fragility >= 0.5:
        return f" Down-weighted: pre-mortem fragility {fragility:.2f}."
    if fragility >= 0.25:
        return f" Pre-mortem fragility {fragility:.2f}."
    return ""


def _debate_note(symbol: str, delta_by_symbol: dict[str, float]) -> str:
    if symbol not in delta_by_symbol:
        return ""
    delta = delta_by_symbol[symbol]
    if delta >= 0.15:
        return f" Debate: bull side won (+{delta:.2f})."
    if delta >= 0.05:
        return f" Debate: slight bull edge (+{delta:.2f})."
    if delta <= -0.15:
        return f" Debate: bear side won ({delta:.2f})."
    if delta <= -0.05:
        return f" Debate: slight bear edge ({delta:.2f})."
    return ""


def allocate_ranked_ideas(
    ranked_ideas: list[RankedIdea],
    profile: dict,
    pre_mortem_findings: list[PreMortemFinding] | None = None,
    debate_judgments: list[DebateJudgment] | None = None,
) -> PortfolioRecommendation:
    config = _risk_config(profile)
    max_position = config["max_position"]
    sector_cap = config["sector_cap"]
    defensive_target = config["defensive"]
    idea_budget = max(0.0, 100.0 - defensive_target)

    fragility_by_symbol = {
        finding["symbol"]: float(finding.get("overall_fragility", 0.0))
        for finding in (pre_mortem_findings or [])
    }
    delta_by_symbol = {
        judgment["symbol"]: float(judgment.get("conviction_delta", 0.0))
        for judgment in (debate_judgments or [])
    }

    if not ranked_ideas:
        return {
            "allocations": [
                {"symbol": "SPY", "allocation_pct": 40.0, "rationale": "Default broad equity exposure"},
                {"symbol": "BND", "allocation_pct": 40.0, "rationale": "Default bond ballast"},
                {"symbol": "CASH", "allocation_pct": 20.0, "rationale": "Default liquidity reserve"},
            ],
            "notes": "No ranked ideas were available, so a generic starter allocation was used.",
        }

    total_score = sum(_adjusted_score(idea, fragility_by_symbol, delta_by_symbol) for idea in ranked_ideas)
    if total_score <= 0:
        total_score = 1e-6
    allocations: list[Allocation] = []
    used = 0.0
    sector_used: dict[str, float] = {}
    for idea in ranked_ideas:
        raw_weight = idea_budget * _adjusted_score(idea, fragility_by_symbol, delta_by_symbol) / total_score
        sector = idea.get("sector", "Other")
        remaining_sector = max(sector_cap - sector_used.get(sector, 0.0), 0.0)
        weight = min(raw_weight, max_position, remaining_sector)
        if weight <= 0:
            continue
        used += weight
        sector_used[sector] = sector_used.get(sector, 0.0) + weight
        fragility = fragility_by_symbol.get(idea["symbol"], 0.0)
        rationale = (
            f"{idea['theme']}: {idea['thesis']}"
            + _fragility_note(idea["symbol"], fragility, fragility_by_symbol)
            + _debate_note(idea["symbol"], delta_by_symbol)
        )
        _add_allocation(
            allocations,
            {
                "symbol": idea["symbol"],
                "allocation_pct": round(weight, 1),
                "rationale": rationale,
            },
        )

    if defensive_target > 0:
        _add_allocation(
            allocations,
            {
                "symbol": "BND",
                "allocation_pct": round(defensive_target, 1),
                "rationale": "Defensive ballast based on the investor risk profile.",
            },
        )
    cash_reserve = round(idea_budget - used, 1)
    if cash_reserve > 0:
        _add_allocation(
            allocations,
            {
                "symbol": "CASH",
                "allocation_pct": cash_reserve,
                "rationale": "Reserved because position caps limited concentration.",
            },
        )

    notes = "Allocation generated from ranked discovery ideas with deterministic risk caps."
    if fragility_by_symbol:
        notes += " Pre-mortem fragilities applied as a multiplier on each idea's weight."
    if delta_by_symbol:
        notes += " Debate conviction deltas adjusted per-symbol scores before sizing."

    return {
        "allocations": _finalize_allocations(allocations),
        "notes": notes,
    }
