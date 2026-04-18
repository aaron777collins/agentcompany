---
name: Feature request
about: Propose a new capability or improvement to AgentCompany
title: "[FEAT] "
labels: enhancement
assignees: ""
---

## Problem statement

<!--
Describe the problem or gap this feature addresses.
Focus on the user/operator need, not the solution.
Example: "When an agent exceeds its budget mid-run, there is no way to
notify the team in Mattermost. The only signal is a log line."
-->

## Proposed solution

<!--
Describe what you want to happen.
Be specific about the interface: API endpoint, UI element, config option,
CLI flag, etc.
-->

## Alternatives considered

<!--
What other approaches did you think about?
Why did you reject them?
-->

## Affected components

<!-- Check all that apply -->

- [ ] agent-runtime (Python / FastAPI)
- [ ] web-ui (Next.js)
- [ ] LLM adapters
- [ ] Agent tools
- [ ] Org hierarchy engine
- [ ] Keycloak / auth
- [ ] CI/CD pipelines
- [ ] Infrastructure / Docker Compose
- [ ] Documentation

## Acceptance criteria

<!--
Bullet list of conditions that must be true for this feature to be
considered done.  Write these as testable statements.

Example:
- Given an agent whose daily budget is exhausted, when the agent-runtime
  receives a trigger, it posts a Mattermost DM to the agent's owner
  before returning HTTP 429.
- The DM includes the agent name, current spend, and daily limit.
- A new `budget.exhausted` event appears in the Redis stream.
-->

- [ ]
- [ ]
- [ ]

## Priority / impact

| Question | Answer |
|----------|--------|
| How many users / agents does this affect? | <!-- all / most / some / one --> |
| Can the affected users work around it today? | <!-- yes / no / partially --> |
| Is this blocking a release? | <!-- yes / no --> |

## Additional context

<!-- Mockups, architecture diagrams, links to related issues or docs -->
