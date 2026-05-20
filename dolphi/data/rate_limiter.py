from __future__ import annotations

import logging
import time
from functools import wraps
from typing import Any, Callable

logger = logging.getLogger(__name__)


class RateLimitError(Exception):
    pass


def exponential_backoff(
    max_retries: int = 5,
    base_delay: float = 1.0,
    timeout: int = 60,
) -> Callable:
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            last_exception = None
            for attempt in range(max_retries):
                try:
                    return func(*args, **kwargs)
                except RateLimitError as e:
                    last_exception = e
                    wait = base_delay * (2 ** attempt)
                    logger.warning(
                        "Rate limited on %s, retrying in %.1fs (attempt %d/%d)",
                        func.__name__, wait, attempt + 1, max_retries,
                    )
                    time.sleep(wait)
                except Exception as e:
                    last_exception = e
                    if attempt == max_retries - 1:
                        raise
                    wait = base_delay * (2 ** attempt)
                    logger.warning(
                        "Error %s on %s, retrying in %.1fs (attempt %d/%d)",
                        e, func.__name__, wait, attempt + 1, max_retries,
                    )
                    time.sleep(wait)
            raise last_exception  # type: ignore[misc]
        return wrapper
    return decorator
