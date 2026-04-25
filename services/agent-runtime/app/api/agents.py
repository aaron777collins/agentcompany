"""Agents API — /api/v1/agents.

Full lifecycle management for Agent resources: CRUD plus start/stop/trigger.
"""

import logging
from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import func, select

from app.dependencies import DBSession, EngineService, OrgAdmin, OrgMember, Pagination
from app.engine.engine_service import EngineError
from app.models.agent import Agent
from app.schemas.agent import (
    AgentCreate,
    AgentRead,
    AgentStopRequest,
    AgentTriggerRequest,
    AgentUpdate,
)
from app.schemas.common import DataResponse, make_list_response

logger = logging.getLogger(__name__)
router = APIRouter()


@router.post(
    "/",
    response_model=DataResponse[AgentRead],
    status_code=status.HTTP_201_CREATED,
    summary="Create an agent",
)
async def create_agent(
    body: AgentCreate,
    db: DBSession,
    claims: OrgAdmin,
) -> DataResponse[AgentRead]:
    existing = await db.scalar(
        select(Agent).where(
            Agent.company_id == body.company_id,
            Agent.slug == body.slug,
            Agent.deleted_at.is_(None),
        )
    )
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"An agent with slug '{body.slug}' already exists in company '{body.company_id}'"
            ),
        )

    agent = Agent(
        org_id=claims.org_id,
        company_id=body.company_id,
        role_id=body.role_id,
        name=body.name,
        slug=body.slug,
        llm_config=body.llm_config.model_dump(),
        capabilities=body.capabilities,
        tool_permissions=body.tool_permissions,
        token_budget_daily=body.token_budget_daily,
        token_budget_monthly=body.token_budget_monthly,
        status="idle",
    )
    db.add(agent)
    await db.flush()
    await db.refresh(agent)

    logger.info("Agent created: %s (company=%s)", agent.id, body.company_id)
    return DataResponse(data=AgentRead.model_validate(agent))


@router.get(
    "/",
    summary="List agents",
)
async def list_agents(
    db: DBSession,
    claims: OrgMember,
    pagination: Pagination,
    company_id: str | None = Query(default=None),
    role_id: str | None = Query(default=None),
    agent_status: str | None = Query(default=None, alias="status"),
) -> dict:
    query = select(Agent).where(
        Agent.org_id == claims.org_id,
        Agent.deleted_at.is_(None),
    )
    if company_id:
        query = query.where(Agent.company_id == company_id)
    if role_id:
        query = query.where(Agent.role_id == role_id)
    if agent_status:
        query = query.where(Agent.status == agent_status)

    total: int = await db.scalar(select(func.count()).select_from(query.subquery())) or 0
    rows = await db.scalars(
        query.order_by(Agent.created_at.desc()).limit(pagination.limit).offset(pagination.offset)
    )
    items = [AgentRead.model_validate(a) for a in rows]
    return make_list_response(items, total, pagination.limit, pagination.offset)


@router.get(
    "/{agent_id}",
    response_model=DataResponse[AgentRead],
    summary="Get an agent",
)
async def get_agent(
    agent_id: str,
    db: DBSession,
    claims: OrgMember,
) -> DataResponse[AgentRead]:
    agent = await _get_or_404(db, agent_id, claims.org_id)
    return DataResponse(data=AgentRead.model_validate(agent))


@router.put(
    "/{agent_id}",
    response_model=DataResponse[AgentRead],
    summary="Update agent configuration",
)
async def update_agent(
    agent_id: str,
    body: AgentUpdate,
    db: DBSession,
    claims: OrgAdmin,
) -> DataResponse[AgentRead]:
    agent = await _get_or_404(db, agent_id, claims.org_id)

    if body.name is not None:
        agent.name = body.name
    if body.role_id is not None:
        agent.role_id = body.role_id
    if body.llm_config is not None:
        agent.llm_config = body.llm_config.model_dump()
    if body.capabilities is not None:
        agent.capabilities = body.capabilities
    if body.tool_permissions is not None:
        agent.tool_permissions = body.tool_permissions
    if body.token_budget_daily is not None:
        agent.token_budget_daily = body.token_budget_daily
    if body.token_budget_monthly is not None:
        agent.token_budget_monthly = body.token_budget_monthly

    agent.version += 1
    await db.flush()
    await db.refresh(agent)
    return DataResponse(data=AgentRead.model_validate(agent))


@router.delete(
    "/{agent_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Soft-delete an agent",
)
async def delete_agent(
    agent_id: str,
    db: DBSession,
    claims: OrgAdmin,
) -> None:
    agent = await _get_or_404(db, agent_id, claims.org_id)
    if agent.status not in ("idle", "paused"):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Agent must be idle or paused before deletion. Current status: {agent.status}",
        )
    agent.soft_delete()
    logger.info("Agent soft-deleted: %s", agent_id)


@router.post(
    "/{agent_id}/start",
    status_code=status.HTTP_202_ACCEPTED,
    summary="Start an agent",
)
async def start_agent(
    agent_id: str,
    db: DBSession,
    claims: OrgAdmin,
    engine: EngineService,
) -> dict:
    agent = await _get_or_404(db, agent_id, claims.org_id)
    if agent.status == "active":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Agent is already active",
        )
    if agent.status == "error":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Agent is in an error state. Resolve the error before starting.",
        )

    # Stage the status optimistically; the engine finalises it to 'active'.
    agent.status = "starting"
    agent.version += 1
    await db.flush()

    try:
        await engine.start_agent(
            agent_id=agent_id,
            db=db,
            triggered_by=claims.sub,
        )
    except EngineError as exc:
        # Revert the DB status so the record is not left stuck in 'starting'.
        agent.status = "idle"
        agent.version += 1
        await db.flush()
        logger.error("Engine failed to start agent %s: %s", agent_id, exc)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Agent engine error: {exc}",
        ) from exc

    logger.info("Agent started: %s (triggered_by=%s)", agent_id, claims.sub)
    return {
        "data": {
            "agent_id": agent_id,
            "status": "active",
            "message": "Agent is active. Subscribe to /api/v1/events/stream for status updates.",
        }
    }


@router.post(
    "/{agent_id}/stop",
    status_code=status.HTTP_202_ACCEPTED,
    summary="Stop an agent",
)
async def stop_agent(
    agent_id: str,
    body: AgentStopRequest,
    db: DBSession,
    claims: OrgAdmin,
    engine: EngineService,
) -> dict:
    agent = await _get_or_404(db, agent_id, claims.org_id)
    if agent.status not in ("active", "starting"):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Cannot stop an agent with status '{agent.status}'",
        )

    previous_status = agent.status
    agent.status = "stopping" if body.drain else "idle"
    agent.version += 1
    await db.flush()

    try:
        await engine.stop_agent(
            agent_id=agent_id,
            db=db,
            drain=body.drain,
            reason=body.reason,
            triggered_by=claims.sub,
        )
    except EngineError as exc:
        # Revert so the agent is not left in a phantom 'stopping' status.
        agent.status = previous_status
        agent.version += 1
        await db.flush()
        logger.error("Engine failed to stop agent %s: %s", agent_id, exc)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Agent engine error: {exc}",
        ) from exc

    logger.info("Agent stopped: %s (drain=%s, triggered_by=%s)", agent_id, body.drain, claims.sub)
    return {
        "data": {
            "agent_id": agent_id,
            "status": agent.status,
            "message": (
                "Agent is draining and will stop soon."
                if body.drain
                else "Agent stopped immediately."
            ),
        }
    }


@router.post(
    "/{agent_id}/trigger",
    status_code=status.HTTP_202_ACCEPTED,
    summary="Manually trigger an agent run",
)
async def trigger_agent(
    agent_id: str,
    body: AgentTriggerRequest,
    db: DBSession,
    claims: OrgMember,
    engine: EngineService,
) -> dict:
    agent = await _get_or_404(db, agent_id, claims.org_id)
    if agent.status not in ("idle", "active"):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Cannot trigger an agent with status '{agent.status}'",
        )

    agent.last_active_at = datetime.now(UTC)
    await db.flush()

    # Build the event payload to enqueue to Redis Streams.
    event_data = {
        "type": "agent.trigger",
        "agent_id": agent_id,
        "task_id": body.task_id,
        "priority": body.priority,
        "context": body.context,
    }

    try:
        trigger_id = await engine.trigger_agent(
            agent_id=agent_id,
            db=db,
            event_data=event_data,
            triggered_by=claims.sub,
        )
    except EngineError as exc:
        logger.error("Engine failed to enqueue trigger for agent %s: %s", agent_id, exc)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Agent engine error: {exc}",
        ) from exc

    logger.info(
        "Agent manually triggered: %s (task=%s, priority=%s, trigger_id=%s)",
        agent_id,
        body.task_id,
        body.priority,
        trigger_id,
    )
    return {
        "data": {
            "agent_id": agent_id,
            "triggered": True,
            "task_id": body.task_id,
            "trigger_id": trigger_id,
            "message": "Trigger queued. The agent will pick it up shortly.",
        }
    }


# ── Helpers ───────────────────────────────────────────────────────────────────


async def _get_or_404(db: DBSession, agent_id: str, org_id: str) -> Agent:
    agent = await db.scalar(
        select(Agent).where(
            Agent.id == agent_id,
            Agent.org_id == org_id,
            Agent.deleted_at.is_(None),
        )
    )
    if not agent:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Agent '{agent_id}' not found",
        )
    return agent
