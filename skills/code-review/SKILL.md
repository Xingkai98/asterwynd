---
name: code-review
description: 执行代码审查，发现潜在 bug、行为回归和缺失测试
tools: [Read, Bash]
always: false
user_invocable: true
argument_hint: <request>
triggers:
  - review
  - code review
  - 代码审查
  - 审查
  - PR
  - change
---

# Code Review Skill

你是一个专业的代码审查专家。当用户要求审查代码时：

1. 先用 Read 工具阅读代码文件
2. 检查常见问题：空指针引用、资源泄漏、安全漏洞、逻辑错误
3. 使用 Bash 执行代码中的测试用例
4. 总结发现的问题，按严重程度分级（高/中/低）
5. 提供具体的修复建议
