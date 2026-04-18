"""Metrics API — /api/v1/metrics.

Token usage, cost breakdown, and agent performance metrics.  All queries run
against the metrics schema (append-only token_usage table).
"""

import logging
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import func, select, text

from app.dependencies import DBSession, OrgAdmin, OrgMember

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/platform", summary="Platform-wide aggregate stats")
async def platform_stats(
    db: DBSession,
    claims: OrgAdmin,
) -> dict:
    """Return platform-wide aggregates for the dashboard overview panel.

    Scoped to the caller's org so multi-tenant deployments stay isolated.
    Active agents are those whose status is 'active' or 'starting'.
    """
    # Run independent aggregates in a single round-trip via CTEs rather than
    # issuing four separate queries.
    sql = text("""
        WITH
        company_count AS (
            SELECT COUNT(*) AS n
            FROM companies
            WHERE org_id = :org_id AND deleted_at IS NULL
        ),
        agent_counts AS (
            SELECT
                COUNT(*)                                           AS total_agents,
                COUNT(*) FILTER (WHERE status IN ('active', 'starting')) AS active_agents
            FROM agents
            WHERE org_id = :org_id AND deleted_at IS NULL
        ),
        task_count AS (
            SELECT COUNT(*) AS n
            FROM tasks
            WHERE org_id = :org_id AND deleted_at IS NULL
        ),
        token_totals AS (
            SELECT
                COALESCE(SUM(total_tokens), 0) AS total_tokens,
                COALESCE(SUM(cost_usd), 0)     AS total_cost_usd
            FROM metrics.token_usage
            WHERE org_id = :org_id
        )
        SELECT
            (SELECT n FROM company_count)       AS total_companies,
            (SELECT total_agents FROM agent_counts) AS total_agents,
            (SELECT active_agents FROM agent_counts) AS active_agents,
            (SELECT n FROM task_count)          AS total_tasks,
            (SELECT total_tokens FROM token_totals) AS total_tokens,
            (SELECT total_cost_usd FROM token_totals) AS total_cost_usd
    """)

    row = (await db.execute(sql, {"org_id": claims.org_id})).one()

    return {
        "data": {
            "total_companies": row.total_companies or 0,
            "total_agents": row.total_agents or 0,
            "active_agents": row.active_agents or 0,
            "total_tasks": row.total_tasks or 0,
            "total_tokens": row.total_tokens or 0,
            "total_cost_usd": float(row.total_cost_usd or 0),
        }
    }


@router.get("/tokens", summary="Token usage stats")
async def token_usage(
    db: DBSession,
    claims: OrgMember,
    company_id: str = Query(...),
    agent_id: str | None = Query(default=None),
    period: str = Query(default="7d"),
    start_at: datetime | None = Query(default=None),
    end_at: datetime | None = Query(default=None),
) -> dict:
    since, until = _resolve_period(period, start_at, end_at)

    # Base filter — always scope to org and company
    filters = [
        "org_id = :org_id",
        "company_id = :company_id",
        "recorded_at >= :since",
        "recorded_at < :until",
    ]
    params: dict = {
        "org_id": claims.org_id,
        "company_id": company_id,
        "since": since,
        "until": until,
    }
    if agent_id:
        filters.append("agent_id = :agent_id")
        params["agent_id"] = agent_id

    where_clause = " AND ".join(filters)

    summary_sql = text(f"""
        SELECT
            SUM(prompt_tokens)     AS prompt_tokens,
            SUM(completion_tokens) AS completion_tokens,
            SUM(total_tokens)      AS total_tokens,
            SUM(cost_usd)          AS cost_usd,
            COUNT(*)               AS call_count
        FROM metrics.token_usage
        WHERE {where_clause}
    """)

    row = (await db.execute(summary_sql, params)).one()

    by_agent_sql = text(f"""
        SELECT
            agent_id,
            SUM(total_tokens)  AS tokens,
            SUM(cost_usd)      AS cost_usd,
            COUNT(*)           AS call_count
        FROM metrics.token_usage
        WHERE {where_clause}
        GROUP BY agent_id
        ORDER BY tokens DESC
        LIMIT 50
    """)
    agent_rows = (await db.execute(by_agent_sql, params)).fetchall()

    timeseries_sql = text(f"""
        SELECT
            date_trunc('day', recorded_at) AS day,
            SUM(total_tokens)              AS tokens,
            SUM(cost_usd)                  AS cost_usd,
            COUNT(*)                       AS calls
        FROM metrics.token_usage
        WHERE {where_clause}
        GROUP BY 1
        ORDER BY 1
    """)
    ts_rows = (await db.execute(timeseries_sql, params)).fetchall()

    return {
        "data": {
            "summary": {
                "prompt_tokens": row.prompt_tokens or 0,
                "completion_tokens": row.completion_tokens or 0,
                "total_tokens": row.total_tokens or 0,
                "total_cost_usd": float(row.cost_usd or 0),
                "call_count": row.call_count or 0,
                "period": f"{since.isoformat()}/{until.isoformat()}",
            },
            "by_agent": [
                {
                    "agent_id": r.agent_id,
                    "tokens": r.tokens,
                    "cost_usd": float(r.cost_usd),
                    "call_count": r.call_count,
                }
                for r in agent_rows
            ],
            "timeseries": [
                {
                    "timestamp": r.day.isoformat(),
                    "tokens": r.tokens,
                    "cost_usd": float(r.cost_usd),
                    "calls": r.calls,
                }
                for r in ts_rows
            ],
        }
    }


@router.get("/costs", summary="Cost breakdown by agent and provider")
async def cost_breakdown(
    db: DBSession,
    claims: OrgMember,
    company_id: str = Query(...),
    period: str = Query(default="30d"),
) -> dict:
    since, until = _resolve_period(period, None, None)

    sql = text("""
        SELECT
            agent_id,
            provider,
            model,
            SUM(total_tokens)  AS total_tokens,
            SUM(cost_usd)      AS cost_usd,
            COUNT(*)           AS calls
        FROM metrics.token_usage
        WHERE org_id = :org_id
          AND company_id = :company_id
          AND recorded_at >= :since
          AND recorded_at < :until
        GROUP BY agent_id, provider, model
        ORDER BY cost_usd DESC
        LIMIT 100
    """)
    rows = (
        await db.execute(
            sql,
            {
                "org_id": claims.org_id,
                "company_id": company_id,
                "since": since,
                "until": until,
            },
        )
    ).fetchall()

    return {
        "data": [
            {
                "agent_id": r.agent_id,
                "provider": r.provider,
                "model": r.model,
                "total_tokens": r.total_tokens,
                "cost_usd": float(r.cost_usd),
                "calls": r.calls,
            }
            for r in rows
        ]
    }


@router.get("/agents/{agent_id}/performance", summary="Agent performance metrics")
async def agent_performance(
    agent_id: str,
    db: DBSession,
    claims: OrgMember,
    period: str = Query(default="7d"),
) -> dict:
    since, until = _resolve_period(period, None, None)

    sql = text("""
        SELECT
            COUNT(*)                        AS total_calls,
            SUM(total_tokens)               AS total_tokens,
            SUM(cost_usd)                   AS total_cost_usd,
            AVG(duration_ms)                AS avg_duration_ms,
            PERCENTILE_CONT(0.5)
                WITHIN GROUP (ORDER BY duration_ms) AS p50_ms,
            PERCENTILE_CONT(0.99)
                WITHIN GROUP (ORDER BY duration_ms) AS p99_ms,
            SUM(tool_calls)                 AS total_tool_calls
        FROM metrics.token_usage
        WHERE agent_id = :agent_id
          AND org_id = :org_id
          AND recorded_at >= :since
          AND recorded_at < :until
    """)
    row = (
        await db.execute(
            sql,
            {
                "agent_id": agent_id,
                "org_id": claims.org_id,
                "since": since,
                "until": until,
            },
        )
    ).one()

    return {
        "data": {
            "agent_id": agent_id,
            "period": f"{since.isoformat()}/{until.isoformat()}",
            "total_calls": row.total_calls or 0,
            "total_tokens": row.total_tokens or 0,
            "total_cost_usd": float(row.total_cost_usd or 0),
            "avg_duration_ms": float(row.avg_duration_ms or 0),
            "p50_duration_ms": float(row.p50_ms or 0),
            "p99_duration_ms": float(row.p99_ms or 0),
            "total_tool_calls": row.total_tool_calls or 0,
        }
    }


# ── Helpers ───────────────────────────────────────────────────────────────────

def _resolve_period(
    period: str,
    start_at: datetime | None,
    end_at: datetime | None,
) -> tuple[datetime, datetime]:
    """Convert a period shorthand (7d, 30d, etc.) to absolute UTC datetimes."""
    from datetime import timedelta

    now = datetime.now(timezone.utc)
    if period == "custom":
        if not start_at or not end_at:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="start_at and end_at are required when period=custom",
            )
        return start_at, end_at

    offsets = {"1h": timedelta(hours=1), "24h": timedelta(hours=24),
               "7d": timedelta(days=7), "30d": timedelta(days=30)}
    delta = offsets.get(period)
    if not delta:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid period '{period}'. Use 1h, 24h, 7d, 30d, or custom.",
        )
    return now - delta, now
