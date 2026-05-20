"""``python -m dolphi.eval`` — run the falsifier-quality leaderboard.

Example:

    python -m dolphi.eval \
        --models anthropic:claude-sonnet-4-6,deepseek:deepseek-v4-pro,ollama:llama3:8b \
        --fixtures all \
        --judge anthropic:claude-sonnet-4-6 \
        --repeats 1 \
        --out docs/eval/

Model spec syntax: ``<provider>:<model>``. Supported providers are
``ollama``, ``openai``, ``openrouter``, ``deepseek`` (routed through
``dolphi.llm.create_llm_client``). The factory respects environment
variables loaded from ``.env``: ``OPENAI_API_KEY``,
``OPENROUTER_API_KEY``, ``DEEPSEEK_API_KEY``, ``OLLAMA_ENDPOINT``.

To compare Anthropic models in v0.2.0, route them through OpenRouter:
``openrouter:anthropic/claude-sonnet-4-6``. A native Anthropic provider
is on the v0.3 roadmap.
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from ..config import Config
from ..llm import create_llm_client
from .fixtures import fixtures_by_slug
from .harness import ModelSpec, run_eval
from .report import write_reports

logger = logging.getLogger(__name__)


def _parse_model_spec(spec: str) -> ModelSpec:
    if ":" not in spec:
        raise SystemExit(f"Bad --models spec '{spec}': expected provider:model")
    provider, _, model = spec.partition(":")
    provider = provider.strip().lower()
    model = model.strip()
    if not provider or not model:
        raise SystemExit(f"Bad --models spec '{spec}': empty provider or model")

    def _factory():
        cfg = Config()
        cfg.llm_provider = provider
        cfg.llm_model = model
        return create_llm_client(cfg)

    return ModelSpec(label=spec, client_factory=_factory)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m dolphi.eval",
        description="Falsifier-quality leaderboard across LLMs.",
    )
    parser.add_argument(
        "--models",
        required=True,
        help="Comma-separated provider:model specs (e.g. 'anthropic:claude-sonnet-4-6,deepseek:deepseek-v4-pro').",
    )
    parser.add_argument(
        "--fixtures",
        default="all",
        help="Comma-separated fixture slugs, or 'all'. See dolphi/eval/fixtures.py.",
    )
    parser.add_argument(
        "--judge",
        required=True,
        help="Single provider:model spec for the fixed judge model.",
    )
    parser.add_argument("--repeats", type=int, default=1, help="Repeats per (model, fixture) pair.")
    parser.add_argument("--out", default="docs/eval", help="Output directory.")
    parser.add_argument("--verbose", action="store_true")

    args = parser.parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )

    model_specs = [_parse_model_spec(s.strip()) for s in args.models.split(",") if s.strip()]
    judge_spec = _parse_model_spec(args.judge.strip())
    fixture_slugs = [s.strip() for s in args.fixtures.split(",") if s.strip()]
    fixtures = fixtures_by_slug(fixture_slugs)
    if not fixtures:
        logger.error("No fixtures matched %r — see dolphi/eval/fixtures.py", fixture_slugs)
        return 2

    report = run_eval(
        models=model_specs,
        fixtures=fixtures,
        judge_spec=judge_spec,
        repeats=args.repeats,
    )
    paths = write_reports(report, Path(args.out))
    logger.info("Wrote leaderboard: %s", paths["markdown"])
    logger.info("Wrote raw rows:    %s", paths["csv"])
    logger.info("Wrote audit JSON:  %s", paths["json"])

    print("\n=== Leaderboard ===")
    for i, row in enumerate(report.leaderboard(), 1):
        print(
            f"  {i}. {row['model']}  aggregate={row['mean_aggregate']:.3f}  "
            f"(horizon={row['horizon_observability']:.2f}, "
            f"assumption={row['assumption_coherence']:.2f}, "
            f"indicator={row['indicator_specificity']:.2f}, "
            f"probability={row['probability_calibration']:.2f})"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
