"""
conftest.py — session-wide test configuration.

Resets the slowapi rate-limiter storage before each test so that
rate-limit counters from one test never bleed into another.

The @limiter.limit(...) decorators on auth endpoints capture the
module-level limiter instance at import time.  We therefore reset
the storage on that same instance — we do NOT replace the instance.
"""

import pytest


@pytest.fixture(autouse=True)
def reset_rate_limiter():
    """Clear the in-memory rate-limiter counters before every test."""
    try:
        from backend.rate_limit import limiter
        # limiter.reset() clears all counters on the underlying storage.
        limiter.reset()
    except Exception:
        # If the module hasn't been imported yet (e.g. pure unit tests),
        # silently skip — there's nothing to reset.
        pass

    yield
