## Symptom

WebSearch / WebFetch 已有最小实现，但缺少对无结果、解析失败、网络失败和长内容截断的稳定诊断。历史流程文档提到需要补 WebSearch hardening，但没有保留 active change。

## Reproduction

后续细化时需要用 fake provider 和 fixture HTML 复现：搜索无结果、provider HTML 结构变化、网络异常、WebFetch 内容过长、WebFetch 返回非 HTML 内容等场景。

## Evidence

当前 `openspec/specs/research-tools/spec.md` 只规定 WebSearch / WebFetch 的最小成功和错误行为；工具代码已有联网请求路径，但缺少统一结果结构和 fake provider 测试边界。

## Root Cause

研究工具先以最小 read-only 能力接入，尚未把外部 provider 不稳定性、解析失败和展示/trace 诊断作为独立能力设计。

## Recommended Direction

先建立 fake provider / fixture 测试，再增强 WebSearch 结果结构和 WebFetch 错误/截断语义；不在本 change 引入浏览器自动化或长期缓存。

## Regression Tests

新增 research tools 单元测试覆盖无结果、解析失败、网络异常、截断和 read-only 权限保持；验证不依赖真实外网。
