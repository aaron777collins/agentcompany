---
name: Bug report
about: Report a reproducible defect in AgentCompany
title: "[BUG] "
labels: bug
assignees: ""
---

## Summary

<!-- One-line description of the bug -->

## Environment

| Field | Value |
|-------|-------|
| AgentCompany version / commit | <!-- e.g. v0.3.1 or abc1234 --> |
| Service affected | <!-- agent-runtime / web-ui / keycloak / mattermost / outline / infra --> |
| Host OS | <!-- e.g. Ubuntu 24.04, macOS 14 --> |
| Docker version | <!-- docker --version --> |
| Browser (if UI bug) | <!-- Chrome 124 / Firefox 126 --> |

## Steps to reproduce

<!--
List the exact steps someone else can follow to see the bug.
Include API calls (with `curl` examples), UI navigation paths, or
configuration changes that trigger it.
-->

1.
2.
3.

## Expected behaviour

<!-- What should happen -->

## Actual behaviour

<!-- What actually happens, including error messages verbatim -->

## Logs / screenshots

<!--
Paste relevant container logs (docker compose logs -f <service>).
Trim to the relevant window; do NOT paste thousands of lines.
Replace any secret values with REDACTED before pasting.
-->

<details>
<summary>Container logs</summary>

```
paste logs here
```

</details>

## Minimal reproduction

<!--
If the bug is in the API: a single curl command that demonstrates it.
If in the UI: the shortest sequence of clicks.
If in a script: the smallest script that triggers it.
-->

## Additional context

<!-- Anything else that might help: recent config changes, upgrade path, etc. -->
