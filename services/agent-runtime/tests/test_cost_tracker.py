"""
Unit tests for CostTracker.

Based on app/engine/cost_tracker.py.
Redis is replaced with fakeredis. The DB pool is mocked with an AsyncMock.
Tests are time-deterministic because date keys are mocked.
"""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import fakeredis.aioredis as fake_aioredis
import pytest

from app.engine.cost_tracker import BudgetStatus, CostTracker, UsageRecord


pytestmark = pytest.mark.asyncio

TODAY = "2026-04-18"
THIS_MONTH = "2026-04"


def _make_tracker(
    redis=None,
    daily_tokens: int = 1000,
    monthly_tokens: int = 10_000,
    daily_usd: float = 1.0,
    monthly_usd: float = 10.0,
) -> tuple[CostTracker, any]:
    if redis is None:
        redis = fake_aioredis.FakeRedis(decode_responses=True)
    mock_db = MagicMock()
    mock_db.execute = AsyncMock(return_value=None)
    tracker = CostTracker(
        agent_id="agt-001",
        company_id="cmp-001",
        db_pool=mock_db,
        redis=redis,
        daily_token_budget=daily_tokens,
        monthly_token_budget=monthly_tokens,
        daily_usd_budget=daily_usd,
        monthly_usd_budget=monthly_usd,
    )
    return tracker, mock_db


# ---------------------------------------------------------------------------
# Constructor validation
# ---------------------------------------------------------------------------


def test_empty_agent_id_raises():
    with pytest.raises(ValueError, match="agent_id"):
        CostTracker(
            agent_id="", company_id="cmp", db_pool=None, redis=None
        )


def test_empty_company_id_raises():
    with pytest.raises(ValueError, match="company_id"):
        CostTracker(
            agent_id="agt", company_id="", db_pool=None, redis=None
        )


def test_negative_daily_budget_raises():
    with pytest.raises(ValueError):
        CostTracker(
            agent_id="agt", company_id="cmp", db_pool=None, redis=None,
            daily_token_budget=-1,
        )


# ---------------------------------------------------------------------------
# record_usage
# ---------------------------------------------------------------------------


async def test_record_usage_increments_redis_counters():
    redis = fake_aioredis.FakeRedis(decode_responses=True)
    tracker, _ = _make_tracker(redis=redis, daily_tokens=10_000)

    with patch.object(tracker, "_today_key", return_value=TODAY), \
         patch.object(tracker, "_month_key", return_value=THIS_MONTH):
        await tracker.record_usage(
            input_tokens=100, output_tokens=50, cost_usd=0.01,
            model="claude-sonnet-4-5", provider="anthropic"
        )
        await tracker.record_usage(
            input_tokens=200, output_tokens=100, cost_usd=0.02,
            model="claude-sonnet-4-5", provider="anthropic"
        )

    daily_key = f"budget:agent:agt-001:daily_tokens:{TODAY}"
    val = await redis.get(daily_key)
    # 150 + 300 = 450 total tokens
    assert float(val) == pytest.approx(450.0)


async def test_record_usage_persists_to_db():
    tracker, mock_db = _make_tracker()
    with patch.object(tracker, "_today_key", return_value=TODAY), \
         patch.object(tracker, "_month_key", return_value=THIS_MONTH):
        await tracker.record_usage(
            input_tokens=50, output_tokens=25, cost_usd=0.005,
            model="gpt-4o", provider="openai"
        )
    # DB execute should have been called for the INSERT
    mock_db.execute.assert_called_once()


async def test_record_usage_negative_tokens_raises():
    tracker, _ = _make_tracker()
    with pytest.raises(ValueError, match="Token counts"):
        await tracker.record_usage(
            input_tokens=-1, output_tokens=50, cost_usd=0.0,
            model="x", provider="x"
        )


async def test_record_usage_negative_cost_raises():
    tracker, _ = _make_tracker()
    with pytest.raises(ValueError, match="cost_usd"):
        await tracker.record_usage(
            input_tokens=10, output_tokens=10, cost_usd=-0.01,
            model="x", provider="x"
        )


# ---------------------------------------------------------------------------
# check — budget OK
# ---------------------------------------------------------------------------


async def test_check_returns_allowed_when_under_budget():
    tracker, _ = _make_tracker(daily_tokens=1000)
    with patch.object(tracker, "_today_key", return_value=TODAY), \
         patch.object(tracker, "_month_key", return_value=THIS_MONTH):
        status = await tracker.check(estimated_tokens=100)
    assert status.allowed is True
    assert status.reason == "ok"


async def test_check_negative_estimated_tokens_raises():
    tracker, _ = _make_tracker()
    with pytest.raises(ValueError):
        await tracker.check(estimated_tokens=-1)


# ---------------------------------------------------------------------------
# check — daily budget exceeded
# ---------------------------------------------------------------------------


async def test_budget_exceeded_daily_returns_denied():
    redis = fake_aioredis.FakeRedis(decode_responses=True)
    tracker, _ = _make_tracker(redis=redis, daily_tokens=100)

    with patch.object(tracker, "_today_key", return_value=TODAY), \
         patch.object(tracker, "_month_key", return_value=THIS_MONTH):
        # Pre-seed Redis to simulate 90 tokens already used today
        await redis.set(
            f"budget:agent:agt-001:daily_tokens:{TODAY}", "90"
        )
        # Requesting 20 more would push total to 110, over the 100 limit
        status = await tracker.check(estimated_tokens=20)

    assert status.allowed is False
    assert status.reason == "daily_budget_exceeded"
    assert status.remaining_daily_tokens == 10


# ---------------------------------------------------------------------------
# check — monthly budget exceeded
# ---------------------------------------------------------------------------


async def test_budget_exceeded_monthly_returns_denied():
    redis = fake_aioredis.FakeRedis(decode_responses=True)
    tracker, _ = _make_tracker(redis=redis, daily_tokens=100_000, monthly_tokens=500)

    with patch.object(tracker, "_today_key", return_value=TODAY), \
         patch.object(tracker, "_month_key", return_value=THIS_MONTH):
        await redis.set(
            f"budget:agent:agt-001:monthly_tokens:{THIS_MONTH}", "490"
        )
        status = await tracker.check(estimated_tokens=20)

    assert status.allowed is False
    assert status.reason == "monthly_budget_exceeded"


# ---------------------------------------------------------------------------
# daily_summary
# ---------------------------------------------------------------------------


async def test_daily_summary_format():
    redis = fake_aioredis.FakeRedis(decode_responses=True)
    tracker, _ = _make_tracker(redis=redis, daily_tokens=1000, daily_usd=5.0)

    with patch.object(tracker, "_today_key", return_value=TODAY), \
         patch.object(tracker, "_month_key", return_value=THIS_MONTH):
        await redis.set(f"budget:agent:agt-001:daily_tokens:{TODAY}", "250")
        await redis.set(f"budget:agent:agt-001:daily_usd:{TODAY}", "0.25")

        summary = await tracker.daily_summary()

    assert summary["date"] == TODAY
    assert summary["tokens_used"] == 250
    assert summary["token_budget"] == 1000
    assert summary["token_utilization_pct"] == pytest.approx(25.0)
    assert summary["cost_usd"] == pytest.approx(0.25)


# ---------------------------------------------------------------------------
# DB failure in _persist_usage is non-fatal
# ---------------------------------------------------------------------------


async def test_db_failure_in_persist_usage_does_not_raise():
    """A failed DB write must not propagate — runs must continue."""
    redis = fake_aioredis.FakeRedis(decode_responses=True)
    mock_db = MagicMock()
    mock_db.execute = AsyncMock(side_effect=RuntimeError("DB unavailable"))

    tracker = CostTracker(
        agent_id="agt-002", company_id="cmp-001",
        db_pool=mock_db, redis=redis,
        daily_token_budget=10_000, monthly_token_budget=100_000,
    )

    with patch.object(tracker, "_today_key", return_value=TODAY), \
         patch.object(tracker, "_month_key", return_value=THIS_MONTH):
        # This must not raise even though DB is broken
        await tracker.record_usage(
            input_tokens=10, output_tokens=5, cost_usd=0.001,
            model="claude-sonnet-4-5", provider="anthropic"
        )


# ---------------------------------------------------------------------------
# Daily budget reset — new day key is independent
# ---------------------------------------------------------------------------


async def test_daily_budget_reset_on_new_day():
    """Usage from yesterday does not count against today's budget."""
    redis = fake_aioredis.FakeRedis(decode_responses=True)
    tracker, _ = _make_tracker(redis=redis, daily_tokens=100)
    yesterday = "2026-04-17"
    today = "2026-04-18"

    # Pre-seed yesterday with 95 tokens (would exceed budget if on same day)
    await redis.set(f"budget:agent:agt-001:daily_tokens:{yesterday}", "95")

    with patch.object(tracker, "_today_key", return_value=today), \
         patch.object(tracker, "_month_key", return_value=THIS_MONTH):
        # Today has 0 usage — requesting 50 tokens should be allowed
        status = await tracker.check(estimated_tokens=50)

    assert status.allowed is True


# ---------------------------------------------------------------------------
# get_usage_report (daily_summary acts as the report)
# ---------------------------------------------------------------------------


async def test_get_usage_report_all_zeros_when_no_usage():
    tracker, _ = _make_tracker()
    with patch.object(tracker, "_today_key", return_value=TODAY), \
         patch.object(tracker, "_month_key", return_value=THIS_MONTH):
        summary = await tracker.daily_summary()

    assert summary["tokens_used"] == 0
    assert summary["cost_usd"] == 0.0
    assert summary["token_utilization_pct"] == 0.0
