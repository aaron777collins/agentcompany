# Research Handoff: Tool Selection for AgentCompany

**From:** Research Agent
**Date:** 2026-04-18
**Status:** Complete
**Full Report:** `docs/research/tool-selection.md`

---

## Summary

Completed evaluation of 16 open-source tools across 5 categories for the AgentCompany platform. The user's recommended stack has been validated and confirmed as the optimal selection.

## Final Stack

| Category | Tool | Version | License | Docker Image |
|---|---|---|---|---|
| Project Management | **Plane** | v1.3.0 | AGPL-3.0 | `makeplane/plane-frontend` + backend/admin/space |
| Documentation | **Outline** | v1.6.1 | BSL 1.1 | `outlinewiki/outline` |
| Team Chat | **Mattermost** | v11.6.0 | MIT | `mattermost/mattermost-team-edition` |
| Identity / Auth | **Keycloak** | v26.6.1 | Apache 2.0 | `quay.io/keycloak/keycloak` |
| Search | **Meilisearch** | v1.42.1 | MIT (Community) | `getmeili/meilisearch` |

## Key Decisions and Rationale

1. **Plane over Taiga/OpenProject:** Best API (REST + OAuth 2.0 + webhooks + typed SDKs in Python/Node.js), most modern UI, highest GitHub stars (48.1k). Purpose-built for the agent-driven workflow.

2. **Outline over BookStack/Wiki.js:** Notion-like UI with comprehensive RPC API. Python and Go SDKs exist. BSL 1.1 license is the only caveat -- self-hosting for internal use is permitted. BookStack (MIT) is the fallback if strict OSI compliance is required.

3. **Mattermost over Rocket.Chat/Zulip:** First-class bot account system that does not consume user licenses. OpenAPI-spec REST API with Go/JS SDKs. Plugin framework for deep integration. Zulip's topic-based threading is worth revisiting if message organization becomes a priority.

4. **Keycloak over Authentik/Authelia:** Industry-standard IdP with native Client Credentials Grant for machine-to-machine auth. Service accounts with scoped roles for per-agent access control. Recent additions (CIMD for MCP, federated client auth, K8s service accounts) show active investment in machine identity. Authentik has a better UI but less mature machine identity support.

5. **Meilisearch over Typesense/OpenSearch:** Simplest developer experience with hybrid search (keyword + semantic via vector embeddings). Single-binary deployment. MIT community license. 57.2k GitHub stars. OpenSearch is the fallback for large-scale deployments needing clustering.

## Next Steps for Receiving Team

1. **Infrastructure:** Create a unified Docker Compose or Kubernetes manifest with all 5 tools + PostgreSQL + Redis + MinIO.
2. **Auth Integration:** Configure Keycloak as the OIDC provider for Plane, Outline, and Mattermost. Create service accounts (Client Credentials) for each AI agent.
3. **Search Pipeline:** Build an indexing service that listens to webhooks from Plane, Outline, and Mattermost, then indexes content into Meilisearch with vector embeddings.
4. **Agent SDK:** Create a unified Python/Node.js SDK wrapping all 5 tool APIs behind a consistent interface for agents to use.
5. **License Review:** Have legal review the BSL 1.1 (Outline, Meilisearch Enterprise) and AGPL-3.0 (Plane) licenses for compliance with your organization's policies.

## Risks

- **Outline's BSL 1.1 license** may not satisfy strict open-source requirements. Mitigation: BookStack (MIT) as fallback.
- **Meilisearch single-node** limitation in Community Edition. Mitigation: sufficient for <1M documents; migrate to OpenSearch if scale demands it.
- **Keycloak resource usage** is higher than alternatives (JVM). Mitigation: allocate 1-2GB RAM; use optimized production build.
- **Integration maintenance** across 5 tools requires ongoing effort. Mitigation: event-driven architecture via webhooks reduces polling overhead.

## Artifacts

- Full research report: `/home/ubuntu/topics/agentcompany/docs/research/tool-selection.md`
- This handoff: `/home/ubuntu/topics/agentcompany/docs/handoffs/research-handoff.md`
