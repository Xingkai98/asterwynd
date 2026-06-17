# Cross-Agent Benchmark Comparison

| Task | myagent | claude |
|------|------|------|
| myagent-001-tool-registry | passed (21.0s) | passed (26.1s) |
| myagent-002-myagent-runner | failed (119.2s) | failed (275.3s) |
| myagent-002-sandbox-executor | failed (301.3s) | passed_with_warnings (601.2s) |
| myagent-003-agentloop-trace | failed (66.3s) | failed (166.5s) |
| myagent-003-read-write-tools | failed (58.0s) | failed (98.9s) |
| myagent-004-benchmark-cli | failed (61.1s) | failed (140.1s) |
| myagent-004-harden-write | failed (39.7s) | failed (22.4s) |
| myagent-005-bash-workspace | failed (125.0s) | failed (110.9s) |
| myagent-006-memory-manager | passed (70.3s) | passed (119.8s) |
| myagent-007-skill-loader | passed (49.7s) | passed (85.7s) |
| myagent-008-parent-channel | passed (30.5s) | failed (133.8s) |
| myagent-009-subagent-manager | passed (172.3s) | failed (146.1s) |
| myagent-010-agent-loop | passed (54.4s) | passed (100.2s) |
| myagent-011-repeater-fix | passed (57.1s) | passed (146.5s) |
| myagent-012-sse-streaming | failed (198.0s) | failed (355.3s) |
| myagent-013-hook-manager | passed (68.6s) | passed (51.9s) |
| myagent-014-logging-tracing | passed (99.1s) | passed (95.8s) |
| myagent-015-retry-budget | passed (118.5s) | passed (209.0s) |
| myagent-017-interactive-fix | failed (107.8s) | failed (223.6s) |
| myagent-018-warning-passes | failed (51.6s) | failed (85.0s) |
| myagent-019-runner-timeout | failed (44.5s) | failed (94.0s) |
| myagent-020-close-clients | failed (125.9s) | failed (67.4s) |
| myagent-readme-title | passed (7.6s) | passed (9.2s) |

## Summary

| Agent | passed | passed_with_warnings | failed | error | Total |
|------|------|------|------|------|------|
| myagent | 11 | 0 | 12 | 0 | 23 |
| claude | 9 | 1 | 13 | 0 | 23 |
