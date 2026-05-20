from dolphi.data import yfinance_wrapper


class FakeHistory:
    empty = False

    def __getitem__(self, key):
        assert key == "Close"
        return self

    @property
    def iloc(self):
        return [-1, 123.45]


class FakeTicker:
    calls = []

    def __init__(self, symbol):
        self.symbol = symbol

    def history(self, start=None, end=None, period=None):
        self.calls.append({"start": start, "end": end, "period": period})
        return FakeHistory()


def test_yfinance_date_lookup_uses_exclusive_next_day_end(monkeypatch):
    FakeTicker.calls = []
    monkeypatch.setattr(yfinance_wrapper.yf, "Ticker", FakeTicker)

    price = yfinance_wrapper.get_stock_price("NVDA", "2026-01-15", skip_cache=True)

    assert price == 123.45
    assert FakeTicker.calls[0]["start"] == "2026-01-15"
    assert FakeTicker.calls[0]["end"] == "2026-01-16"
