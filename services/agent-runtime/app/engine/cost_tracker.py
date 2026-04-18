"""
Token budget and cost tracking.

Tracks token usage and cost per agent, per day, and per month. Budget checks
happen before every LLM call — not once at the start of a run. A run that
starts under budget can exceed it mid-run if it takes many steps.

Two-tier accounting:
  1. Redis counters — fast atomic increments, checked on every LLM call
  2. PostgreSQL — durable record for billing, dashboards, and retention

The Redis tier uses time-keyed keys (agent:{id}:daily:{YYYY-MM-DD}) with a
TTL so old keys expire automatically. Budget limits come from the agent config
stored in PostgreSQL.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Optional

logger = logging.getLogger(__name__)


@dataclass
class BudgetStatus:
    """
    Result of a budget check.

    When allowed=False the caller must pause the agent immediately.
    remaining_* fields are informational — include them in the PAUSED
    state reason so operators know why the agent stopped.
    """

    allowed: bool
    reason: str           # "ok" | "daily_budget_exceeded" | "monthly_budget_exceeded" | "company_budget_exceeded"
    remaining_daily_tokens: int
    remaining_monthly_tokens: int
    remaining_daily_usd: float
    remaining_monthly_usd: float


@dataclass
class UsageRecord:
    """A single LLM call's resource consumption, ready for DB insertion."""

    agent_id: str
    company_id: str
    run_id: Optional[str]
    model: str
    provider: str
    input_tokens: int
    output_tokens: int
    total_tokens: int
    cost_usd: float
    recorded_at: datetime


class CostTracker:
    """
    Manages token budgets and cost records for a single agent.

    Designed for concurrent access: Redis INCRBY is atomic, so multiple
    coroutines can safely call record_usage() simultaneously.
    """

    # Redis key TTLs — long enough to survive the relevant period
    _DAILY_KEY_TTL_SECONDS = 86_400 * 2    # 2 days
    _MONTHLY_KEY_TTL_SECONDS = 86_400 * 35  # 35 days

    def __init__(
        self,
        agent_id: str,
        company_id: str,
        db_pool: Any,      # asyncpg Pool
        redis: Any,        # redis.asyncio client
        daily_token_budget: int = 100_000,
        monthly_token_budget: int = 2_000_000,
        daily_usd_budget: float = 10.0,
        monthly_usd_budget: float = 200.0,
    ) -> None:
        if not agent_id:
            raise ValueError("agent_id must not be empty")
        if not company_id:
            raise ValueError("company_id must not be empty")
        if daily_token_budget < 0:
            raise ValueError("daily_token_budget must be >= 0")
        if monthly_token_budget < 0:
            raise ValueError("monthly_token_budget must be >= 0")

        self._agent_id = agent_id
        self._company_id = company_id
        self._db = db_pool
        self._redis = redis
        self._daily_token_budget = daily_token_budget
        self._monthly_token_budget = monthly_token_budget
        self._daily_usd_budget = daily_usd_budget
        self._monthly_usd_budget = monthly_usd_budget

    async def check(self, estimated_tokens: int = 500) -> BudgetStatus:
        """
        Check whether the agent can spend estimated_tokens more tokens.

        This is a read operation — it does not consume any budget.
        Call before every LLM invocation; the cost check must be inside the
        decision loop, not just at run start.
        """
        if estimated_tokens < 0:
            raise ValueError("estimated_tokens must be >= 0")

        used_today_tokens = await self._get_daily_tokens()
        used_month_tokens = await self._get_monthly_tokens()
        used_today_usd = await self._get_daily_usd()
        used_month_usd = await self._get_monthly_usd()

        remaining_daily_tokens = max(0, self._daily_token_budget - used_today_tokens)
        remaining_monthly_tokens = max(0, self._monthly_token_budget - used_month_tokens)
        remaining_daily_usd = max(0.0, self._daily_usd_budget - used_today_usd)
        remaining_monthly_usd = max(0.0, self._monthly_usd_budget - used_month_usd)

        if used_today_tokens + estimated_tokens > self._daily_token_budget:
            return BudgetStatus(
                allowed=False,
                reason="daily_budget_exceeded",
                remaining_daily_tokens=remaining_daily_tokens,
                remaining_monthly_tokens=remaining_monthly_tokens,
                remaining_daily_usd=remaining_daily_usd,
                remaining_monthly_usd=remaining_monthly_usd,
            )

        if used_month_tokens + estimated_tokens > self._monthly_token_budget:
            return BudgetStatus(
                allowed=False,
                reason="monthly_budget_exceeded",
                remaining_daily_tokens=remaining_daily_tokens,
                remaining_monthly_tokens=remaining_monthly_tokens,
                remaining_daily_usd=remaining_daily_usd,
                remaining_monthly_usd=remaining_monthly_usd,
            )

        return BudgetStatus(
            allowed=True,
            reason="ok",
            remaining_daily_tokens=remaining_daily_tokens,
            remaining_monthly_tokens=remaining_monthly_tokens,
            remaining_daily_usd=remaining_daily_usd,
            remaining_monthly_usd=remaining_monthly_usd,
        )

    async def record_usage(
        self,
        input_tokens: int,
        output_tokens: int,
        cost_usd: float,
        model: str,
        provider: str,
        run_id: Optional[str] = None,
    ) -> None:
        """
        Record actual token usage after a completed LLM call.

        Redis counters are updated atomically (fast path).
        A durable DB write follows asynchronously.
        """
        if input_tokens < 0 or output_tokens < 0:
            raise ValueError("Token counts must be >= 0")
        if cost_usd < 0:
            raise ValueError("cost_usd must be >= 0")

        total_tokens = input_tokens + output_tokens
        today = self._today_key()
        month = self._month_key()

        # Atomic Redis increments — safe for concurrent coroutines
        pipe = self._redis.pipeline()
        pipe.incrbyfloat(f"budget:agent:{self._agent_id}:daily_tokens:{today}", total_tokens)
        pipe.incrbyfloat(f"budget:agent:{self._agent_id}:monthly_tokens:{month}", total_tokens)
        pipe.incrbyfloat(f"budget:agent:{self._agent_id}:daily_usd:{today}", cost_usd)
        pipe.incrbyfloat(f"budget:agent:{self._agent_id}:monthly_usd:{month}", cost_usd)
        # Set TTL on each key — using SET with EX is not atomic with INCRBYFLOAT
        # so we EXPIRE separately; a crash between the two is acceptable because
        # the key will eventually be cleaned up by the next EXPIRE call.
        pipe.expire(f"budget:agent:{self._agent_id}:daily_tokens:{today}", self._DAILY_KEY_TTL_SECONDS)
        pipe.expire(f"budget:agent:{self._agent_id}:monthly_tokens:{month}", self._MONTHLY_KEY_TTL_SECONDS)
        pipe.expire(f"budget:agent:{self._agent_id}:daily_usd:{today}", self._DAILY_KEY_TTL_SECONDS)
        pipe.expire(f"budget:agent:{self._agent_id}:monthly_usd:{month}", self._MONTHLY_KEY_TTL_SECONDS)
        await pipe.execute()

        # Durable record — write to metrics.token_usage
        await self._persist_usage(
            UsageRecord(
                agent_id=self._agent_id,
                company_id=self._company_id,
                run_id=run_id,
                model=model,
                provider=provider,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                total_tokens=total_tokens,
                cost_usd=cost_usd,
                recorded_at=datetime.now(timezone.utc),
            )
        )

        logger.debug(
            "Recorded usage for agent %s: tokens=%d cost_usd=%.6f model=%s",
            self._agent_id,
            total_tokens,
            cost_usd,
            model,
        )

    async def daily_summary(self) -> dict:
        """Return today's aggregated usage for monitoring/dashboards."""
        today = self._today_key()
        tokens = await self._get_daily_tokens()
        usd = await self._get_daily_usd()
        return {
            "date": today,
            "agent_id": self._agent_id,
            "tokens_used": int(tokens),
            "cost_usd": round(usd, 6),
            "token_budget": self._daily_token_budget,
            "usd_budget": self._daily_usd_budget,
            "token_utilization_pct": round(tokens / max(1, self._daily_token_budget) * 100, 1),
        }

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    async def _get_daily_tokens(self) -> float:
        val = await self._redis.get(f"budget:agent:{self._agent_id}:daily_tokens:{self._today_key()}")
        return float(val or 0)

    async def _get_monthly_tokens(self) -> float:
        val = await self._redis.get(f"budget:agent:{self._agent_id}:monthly_tokens:{self._month_key()}")
        return float(val or 0)

    async def _get_daily_usd(self) -> float:
        val = await self._redis.get(f"budget:agent:{self._agent_id}:daily_usd:{self._today_key()}")
        return float(val or 0)

    async def _get_monthly_usd(self) -> float:
        val = await self._redis.get(f"budget:agent:{self._agent_id}:monthly_usd:{self._month_key()}")
        return float(val or 0)

    async def _persist_usage(self, record: UsageRecord) -> None:
        """Write a usage record to the metrics schema. Fails silently to not disrupt runs."""
        try:
            await self._db.execute(
                """
                INSERT INTO metrics.token_usage
                    (recorded_at, org_id, company_id, agent_id, run_id,
                     provider, model, prompt_tokens, completion_tokens,
                     total_tokens, cost_usd)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11)
                """,
                record.recorded_at,
                None,  # org_id — filled in by caller if available
                record.company_id,
                record.agent_id,
                record.run_id,
                record.provider,
                record.model,
                record.input_tokens,
                record.output_tokens,
                record.total_tokens,
                record.cost_usd,
            )
        except Exception:
            # A failed metrics write must never crash an agent run.
            # Log and continue — the Redis counters are still accurate.
            logger.exception(
                "Failed to persist usage record for agent %s to DB (non-fatal)",
                self._agent_id,
            )

    def _today_key(self) -> str:
        return time.strftime("%Y-%m-%d", time.gmtime())

    def _month_key(self) -> str:
        return time.strftime("%Y-%m", time.gmtime())
