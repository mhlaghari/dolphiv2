from dolphi.data.base import DataFetcher
from dolphi.data import newsapi_wrapper


def test_data_fetcher_configures_newsapi_key(monkeypatch):
    monkeypatch.setattr(newsapi_wrapper, "_api_key", None)

    def fake_get_headlines(query: str, days_back: int = 7, skip_cache: bool = False):
        return [{"title": f"{query} headline", "description": "", "source": "Test"}]

    monkeypatch.setattr(newsapi_wrapper, "get_headlines", fake_get_headlines)

    fetcher = DataFetcher(None, newsapi_key="test-key")
    headlines = fetcher.get_headlines("NVDA")

    assert headlines == [{"title": "NVDA headline", "description": "", "source": "Test"}]
