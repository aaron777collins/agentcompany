"""Main API router — aggregates all sub-routers under /api/v1."""

from fastapi import APIRouter

from app.api import agents, approvals, companies, events, metrics, roles, search, tasks, webhooks

api_router = APIRouter(prefix="/api/v1")

api_router.include_router(companies.router, prefix="/companies", tags=["Companies"])
api_router.include_router(agents.router, prefix="/agents", tags=["Agents"])
api_router.include_router(approvals.router, prefix="/approvals", tags=["Approvals"])
api_router.include_router(roles.router, prefix="/roles", tags=["Roles"])
api_router.include_router(tasks.router, prefix="/tasks", tags=["Tasks"])
api_router.include_router(search.router, prefix="/search", tags=["Search"])
api_router.include_router(events.router, prefix="/events", tags=["Events"])
api_router.include_router(metrics.router, prefix="/metrics", tags=["Metrics"])

# Webhooks sit outside /api/v1 because they use tool-specific auth, not JWT
webhooks_router = APIRouter(prefix="/api/v1/webhooks")
webhooks_router.include_router(webhooks.router, tags=["Webhooks"])
