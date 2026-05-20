from dolphi.data.base import DataFetcher
from dolphi.ideas.pipeline import discover_ranked_ideas
from dolphi.research.beneficiaries import map_beneficiaries
from dolphi.research.narratives import discover_narratives
from dolphi.research.pipeline import DEFAULT_RESEARCH_QUERIES, discover_research_themes
from dolphi.research.sources.brave import BraveResearchSource
from dolphi.research.sources.base import ResearchDocument, dedupe_documents
from dolphi.research.sources.registry import build_source_registry
from dolphi.research.sources.searxng import SearXNGResearchSource
from dolphi.research.sources.static import StaticResearchSource
from dolphi.scoring.composite import rank_candidates
from dolphi.universe.symbols import default_universe


def docs():
    return [
        ResearchDocument(
            title="AI data centers accelerate power demand",
            snippet="Utilities and grid equipment suppliers are seeing demand from AI data center load growth.",
            source="fixture",
            url="https://example.test/ai-power",
            published_at="2026-05-01",
            query="AI infrastructure",
        ),
        ResearchDocument(
            title="Foundries expand capacity for AI accelerators",
            snippet="Advanced foundries, memory makers, and semiconductor equipment vendors benefit from AI chip demand.",
            source="fixture",
            url="https://example.test/ai-semis",
            published_at="2026-05-03",
            query="AI infrastructure",
        ),
        ResearchDocument(
            title="Healthcare defensive rotation grows",
            snippet="Investors are rotating into healthcare as earnings uncertainty rises.",
            source="fixture",
            url="https://example.test/healthcare",
            published_at="2026-04-20",
            query="defensive sectors",
        ),
    ]


def profile(asset_classes=None):
    return {
        "risk_tolerance": "Moderate",
        "goal": "growth",
        "preferred_asset_classes": asset_classes or ["stocks", "etfs"],
    }


def test_dedupe_documents_by_url_and_content_hash():
    first = docs()[0]
    duplicate = ResearchDocument(
        title=first.title,
        snippet=first.snippet,
        source="other",
        url=first.url,
        published_at=first.published_at,
        query=first.query,
    )

    assert dedupe_documents([first, duplicate, docs()[1]]) == [first, docs()[1]]


def test_source_registry_includes_free_static_source_by_default():
    registry = build_source_registry(static_documents=docs(), newsapi_key=None)

    documents = registry.fetch_all(["AI infrastructure"])

    assert documents
    assert {document.source for document in documents} == {"static"}


def test_source_registry_activates_searxng_when_base_url_is_configured():
    registry = build_source_registry(static_documents=docs(), searxng_base_url="http://localhost:8080")

    assert any(source.name == "searxng" for source in registry.sources)


def test_source_registry_activates_brave_when_api_key_is_configured():
    registry = build_source_registry(static_documents=docs(), brave_api_key="test-key")

    assert any(source.name == "brave" for source in registry.sources)


def test_brave_source_parses_web_results(monkeypatch):
    class Response:
        def raise_for_status(self):
            return None

        def json(self):
            return {
                "web": {
                    "results": [
                        {
                            "title": "Market breadth improves",
                            "description": "More sectors are participating in the rally.",
                            "url": "https://example.test/breadth",
                            "age": "May 19, 2026",
                        }
                    ]
                }
            }

    calls = []

    def fake_get(url, headers, params, timeout):
        calls.append((url, headers, params, timeout))
        return Response()

    monkeypatch.setattr("requests.get", fake_get)

    documents = BraveResearchSource("test-key").fetch("market breadth", limit=3)

    assert calls[0][0] == "https://api.search.brave.com/res/v1/web/search"
    assert calls[0][1]["X-Subscription-Token"] == "test-key"
    assert calls[0][2]["q"] == "market breadth"
    assert documents[0].source == "brave:web"
    assert documents[0].url == "https://example.test/breadth"


def test_searxng_source_parses_json_results(monkeypatch):
    class Response:
        def raise_for_status(self):
            return None

        def json(self):
            return {
                "results": [
                    {
                        "title": "Grid suppliers benefit from AI demand",
                        "content": "Data centers need power equipment and utilities.",
                        "url": "https://example.test/grid",
                        "publishedDate": "2026-05-19",
                        "engine": "news",
                    }
                ]
            }

    calls = []

    def fake_get(url, params, timeout):
        calls.append((url, params, timeout))
        return Response()

    monkeypatch.setattr("requests.get", fake_get)

    documents = SearXNGResearchSource("http://localhost:8080").fetch("AI power", limit=3)

    assert calls[0][0] == "http://localhost:8080/search"
    assert calls[0][1]["format"] == "json"
    assert documents[0].source == "searxng:news"
    assert documents[0].url == "https://example.test/grid"


def test_newsapi_source_preserves_url_and_published_date(monkeypatch):
    def fake_get_headlines(query, days_back=7):
        return [
            {
                "title": "AI infrastructure demand rises",
                "description": "Utilities and foundries benefit.",
                "source": "News Source",
                "url": "https://example.test/news",
                "published_at": "2026-05-18T10:00:00Z",
            }
        ]

    monkeypatch.setattr("dolphi.research.sources.registry.newsapi_wrapper.get_headlines", fake_get_headlines)
    documents = build_source_registry(newsapi_key="test-key").fetch_all(["AI infrastructure"])

    news_doc = next(document for document in documents if document.source == "News Source")
    assert news_doc.url == "https://example.test/news"
    assert news_doc.published_at == "2026-05-18T10:00:00Z"


def test_narrative_discovery_groups_documents_without_tickers():
    narratives = discover_narratives(docs())

    assert len(narratives) >= 2
    ai = narratives[0]
    assert "AI" in ai.title or "Power" in ai.title
    assert ai.source_count == 2
    assert ai.confidence > narratives[-1].confidence


def test_narrative_discovery_parses_rss_pubdate_freshness():
    narratives = discover_narratives(
        [
            ResearchDocument(
                title="AI power demand rises",
                snippet="Data center power and grid equipment demand is rising.",
                source="rss",
                url="https://example.test/rss",
                published_at="Tue, 19 May 2026 10:44:00 UTC",
                query="AI infrastructure",
            )
        ]
    )

    assert narratives[0].freshness == 1.0


def test_beneficiary_mapping_validates_symbols_and_preserves_evidence():
    narratives = discover_narratives(docs())

    clusters = map_beneficiaries(narratives, default_universe(), profile())

    symbols = {relation["symbol"] for cluster in clusters for relation in cluster["related_symbols"]}
    assert {"TSM", "ASML", "MU", "CEG", "ETN"}.intersection(symbols)
    assert "NOTREAL" not in symbols
    assert all(relation["evidence"] for cluster in clusters for relation in cluster["related_symbols"])


def test_beneficiary_mapping_supports_non_ai_market_narratives():
    documents = [
        ResearchDocument(
            title="Banks benefit as credit conditions stabilize",
            snippet="Financial stocks and payment networks improve as loan growth and credit quality stabilize.",
            source="fixture",
            url="https://example.test/financials",
            published_at="2026-05-10",
            query="credit conditions equities",
        ),
        ResearchDocument(
            title="Consumer spending remains resilient",
            snippet="Retail sales and consumer payments point to durable demand across discount stores and online retail.",
            source="fixture",
            url="https://example.test/consumer",
            published_at="2026-05-11",
            query="consumer spending retail earnings",
        ),
    ]

    clusters = map_beneficiaries(discover_narratives(documents), default_universe(), profile())
    symbols = {relation["symbol"] for cluster in clusters for relation in cluster["related_symbols"]}

    assert {"JPM", "V", "WMT", "AMZN"}.issubset(symbols)


def test_beneficiary_mapping_respects_asset_preferences():
    narratives = discover_narratives(docs())

    clusters = map_beneficiaries(narratives, default_universe(), profile(["stocks"]))

    symbols = {relation["symbol"] for cluster in clusters for relation in cluster["related_symbols"]}
    assert "SMH" not in symbols
    assert "XLU" not in symbols
    assert "TSM" in symbols


def test_discovery_pipeline_is_theme_first_without_seed_symbols():
    source = StaticResearchSource(docs())
    data = DataFetcher(cache=None, mock=True)

    result = discover_ranked_ideas(
        profile(),
        data,
        top_k=5,
        seed_symbols=None,
        research_sources=[source],
        research_queries=["AI infrastructure"],
    )

    assert result.theme_clusters
    assert result.candidate_symbols
    assert any("AI" in cluster["theme"] or "Power" in cluster["theme"] for cluster in result.theme_clusters)


def test_discovery_pipeline_merges_seed_symbols_and_research_queries():
    source = StaticResearchSource(docs())
    data = DataFetcher(cache=None, mock=True)

    result = discover_ranked_ideas(
        profile(),
        data,
        top_k=5,
        seed_symbols=["NVDA"],
        research_sources=[source],
        research_queries=["AI infrastructure"],
    )

    assert result.narratives
    assert any(cluster["seed_symbol"] == "NVDA" for cluster in result.theme_clusters)
    assert any(cluster["seed_symbol"] != "NVDA" for cluster in result.theme_clusters)


def test_score_uses_narrative_evidence_strength():
    weak = {
        "symbol": "TSM",
        "name": "Taiwan Semiconductor",
        "asset_type": "stock",
        "is_adr": True,
        "sector": "Technology",
        "theme": "AI infrastructure",
        "price": 100,
        "features": {
            "narrative_confidence": 0.2,
            "source_diversity": 0.2,
            "source_recency": 0.3,
            "relationship_strength": 0.4,
            "market_trend": 0.4,
            "valuation": 0.5,
            "liquidity": 0.9,
            "risk_penalty": 0.1,
        },
        "evidence": ["single weak source"],
        "risks": ["ADR risk"],
    }
    strong = {**weak, "symbol": "CEG", "is_adr": False, "features": {**weak["features"], "narrative_confidence": 0.9, "source_diversity": 0.8, "relationship_strength": 0.9}}

    ranked = rank_candidates([weak, strong], top_k=2)

    assert ranked[0]["symbol"] == "CEG"
    assert ranked[0]["score_breakdown"]["narrative_confidence"] > ranked[1]["score_breakdown"]["narrative_confidence"]


def test_research_pipeline_discovers_themes_from_sources():
    source = StaticResearchSource(docs())

    result = discover_research_themes(
        profile(),
        default_universe(),
        research_sources=[source],
        research_queries=["AI infrastructure"],
    )

    assert result.documents
    assert result.narratives
    assert result.theme_clusters


def test_research_pipeline_defaults_to_broad_market_agenda_without_user_queries():
    class CapturingSource:
        name = "capturing"

        def __init__(self):
            self.queries = []

        def fetch(self, query, limit=10):
            self.queries.append(query)
            return []

    source = CapturingSource()

    discover_research_themes(profile(), default_universe(), research_sources=[source])

    assert source.queries == DEFAULT_RESEARCH_QUERIES
    assert len(DEFAULT_RESEARCH_QUERIES) >= 6
    assert any("sector rotation" in query for query in DEFAULT_RESEARCH_QUERIES)
    assert any("earnings" in query for query in DEFAULT_RESEARCH_QUERIES)
    assert any("consumer" in query for query in DEFAULT_RESEARCH_QUERIES)
    assert not all("ai" in query.lower() or "data center" in query.lower() for query in DEFAULT_RESEARCH_QUERIES)


def test_research_pipeline_deep_mode_expands_market_agenda_without_user_queries():
    class CapturingSource:
        name = "capturing"

        def __init__(self):
            self.queries = []

        def fetch(self, query, limit=10):
            self.queries.append((query, limit))
            return []

    source = CapturingSource()

    discover_research_themes(profile(), default_universe(), research_sources=[source], research_depth="deep")

    assert len(source.queries) > len(DEFAULT_RESEARCH_QUERIES)
    assert all(limit >= 15 for _, limit in source.queries)
    assert any("beginner" in query for query, _ in source.queries)
    assert any("professional investor" in query for query, _ in source.queries)
