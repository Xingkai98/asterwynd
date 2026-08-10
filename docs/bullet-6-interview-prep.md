# Bullet 6 面试讲稿：3 层纵深防御安全体系

> 实现 3 层纵深防御安全体系：工作区路径边界 + 敏感文件 deny 与 mode 权限 fail-closed → CommandGuard 语义级命令检查覆盖绕过变体 → 进程沙箱 + cgroup v2 资源限制 / Docker 容器隔离双后端，配合细粒度工具权限、受控只读浏览器（URL 白名单 + 只读工具集）和人工审批链路

---

## 主讲述稿（~450 字）

安全体系是我在 Asterwynd 里花了很多心思设计的部分——因为一个能执行 Bash 命令和文件读写的 AI agent，安全问题不是可选的，是生存问题。我设计了三层纵深防御，每层承担不同的职责。

第一层是工作区策略和权限模型。WorkspacePolicy 限制 agent 只能读写 workspace 内的文件，35 条 glob 模式拒绝敏感文件（.git、.env、私钥、SSH 密钥等）。权限模型定义了 8 种 Capability（如 WORKSPACE_READ、COMMAND_EXECUTE、BROWSER_CONTROL）、3 级风险（LOW/MEDIUM/HIGH）、4 种 Mode（BUILD/READ_ONLY/PLAN/BYPASS）。核心设计是 fail-closed——如果 mode 没有配置对应的权限 profile，默认返回一个空能力集的 fail_closed profile，拒绝一切操作。配置缺失不应等于全通。

第二层是 CommandGuard，专门解决"正则黑名单可以被绕过"的问题。除了 59 个危险命令正则模式外，我加了 18 个扩展模式覆盖绕过变体（如 rm -fr vs rm -rf 的 flag 重排、$IFS 变量空格绕过、反斜杠逃逸命令名），还对 7 个高危命令做了 argv 语义级检查——timeout 5 rm -rf / 这种包装攻击会被递归检查被包装的命令。但我必须诚实地说，CommandGuard 文档自身定性为"guardrail, not boundary"——正则命令检查在根本上是可以绕过的（Claude Code 2025 年的 CVE 已经证明了这一点）。真正的硬边界在第三层。

第三层是进程级隔离。双后端设计——ProcessBackend 用独立进程组 + cgroup v2（memory.max、swap.max=0 禁用 swap、cpu.max 配额），DockerBackend 用容器级隔离（--network none 无网络、-v 仅挂载 workspace、--rm 自动清理）。统一 ExecutionBackend Protocol 切换。cgroup 不可用时降级为无限制但打 degraded 事件，Docker 不可用时直接抛 RuntimeError 而不是静默退回 ProcessBackend——静默降级会丢失用户期望的容器隔离。

旁路防线包括细粒度工具权限（每个工具绑定 Capability 和 RiskLevel，按 mode 的权限 profile 决策）、受控只读浏览器（7 个只读工具 + URL 白名单 + 默认关闭）、人工审批链路（fail-closed 默认 N，非交互环境 UNAVAILABLE 等价拒绝，参数自动脱敏）。

---

## 追问 1：三层防线是不是太多了？去掉一层会怎样？

**回答（~250 字）：**

三层防线遵循"纵深防御"原则——没有单层是完美的，但组合起来让攻击面大幅缩小。每层去掉后的后果不同。

去掉第一层（权限+fail-closed）——CommandGuard 拦截了危险命令，Bash 工具仍然需要经过 deny 检查，但 Read/Write 等文件工具失去了 capability 保护。一个 READ_ONLY mode 的 agent 仍然可以写文件，因为 READ_ONLY 的限制来自第一层的 capability 检查而非第二层的命令检查。

去掉第二层（CommandGuard）——第一层还有命令黑名单，但黑名单是正则匹配且只有 42 个 + 扩展 18 个模式。rm -fr / 这种 flag 重排、timeout 5 rm -rf / 这种包装攻击会直接通过黑名单，因为没有 argv 语义检查来做递归分析。第三层 sandbox 能限制破坏范围但无法阻止 workspace 内的破坏。

去掉第三层（sandbox）——Docker 隔离的缺失意味着 agent 进程有完整的宿主机文件系统和网络访问。即使有两层软防护，Bash 命令的任何逃逸都会导致宿主机沦陷。这就是为什么第三层被定义为"the real boundary"。

面试官可能会追问"会不会过度设计"——我的回答是：这是 AI coding agent，能执行任意命令。安全不是功能需求，是生存条件。

---

## 追问 2：fail-closed 具体怎么实现的？和 fail-open 的区别在哪里？

**回答（~200 字）：**

fail-closed 在三个层面体现。权限维度——ModePolicy 的 permission_profile 属性在找不到 mode 对应配置时，返回一个 `allowed_capabilities=frozenset()` 的空 profile，任何需要 Capability 的工具都会被 DENY。这就是"配置缺失则拒绝一切"。

审批维度——FailClosedApprovalHandler 永远返回 UNAVAILABLE，在 AgentLoop 的审批接线中 UNAVAILABLE 等价于拒绝（pre_denied_error_type="approval_unavailable"）。CLI 交互式审批的默认答案是 N——用户按一个回车不做选择等价于拒绝。

沙箱维度——DockerBackend 不可用时，build_sandbox_from_config 直接抛 RuntimeError，不会静默退回 ProcessBackend。ProcessBackend 的 cgroup 不可用时降级为无限制运行但打 degraded 事件——这里是 degrade but alert，不是 silent fail-open。

和 fail-open 的核心区别：fail-open 在异常路径上"宁可放行不错杀"，fail-closed 是"宁可错杀不放行"。对一个能执行任意命令的 AI agent 来说，后者是唯一合理的默认。

---

## 追问 3：CommandGuard 是 guardrail 不是 boundary，为什么还要做？

**回答（~200 字）：**

因为深度防御的第一原则就是"不要让单层承担全部责任"。

CommandGuard 要做的是拦截 95% 的常见攻击变体，让剩下的 5% 由 sandbox 兜底。如果在第一层就全放过，sandbox 的压力会大得多——比如 rm -rf / 和 fork bomb 这些明显有害的命令，不应该让 cgroup/Docker 来拦，应该在语义层面就直接拒绝。而且 sandbox 拦截意味着进程已经启动了，性能开销和副作用已经产生了。

另一个价值是可观测性——CommandGuard 的 deny 事件通过 SandboxEventSink 写入 trace，比 sandbox kill 事件更容易分析。运维层面可以回答"上周有多少次命令被拦截"这类问题，sandbox kill 很难区分"恶意攻击"和"普通超时"。

说白了——正则命令检查确实不是安全边界，但它是一个极低成本、极高收益的预过滤器。好比机场安检的金属探测门不是绝对安全（陶瓷刀能过），但不能因为它不完美就不装。

---

## 追问 4：受控浏览器是怎么做安全的？和浏览器沙箱有区别吗？

**回答（~200 字）：**

首先要澄清术语——这不叫"浏览器沙箱"。沙箱意味着进程级隔离——cgroup 或 Docker。Asterwynd 的浏览器是 Playwright 驱动的真实 Chromium，运行在宿主机上，没有容器包装。它的安全依赖的是策略护栏而非执行隔离。

URL 白名单是第一道防线：空白名单 = 拒绝所有 URL，http 只能被显式白名单放行（强制 HTTPS），域名匹配支持精确和通配符两种模式。BrowserSession 的每次 navigate 操作都被 BrowserPolicy.assert_url_allowed 拦截。

只读工具集是第二道防线：7 个浏览器工具全部是 read-only——导航、获取内容、截图、滚动、标签管理。没有表单填写、文件上传、数据提交。当然这里有个现实的局限——只读是"工具层面"的。如果一个页面有 JavaScript 能访问 Playwright 的 API，理论上仍可能突破。但 URL 白名单大幅缩小了这个攻击面——agent 只能访问你明确允许的域名。

浏览器默认关闭（config.enabled=False），需要用户显式开启并配置白名单。惰性启动意味着只在首次浏览器工具调用时才启动 Chromium，不做无谓初始化。

---

## 追问 5：如果有 MCP 工具接入，怎么保证它的安全？

**回答（~150 字）：**

MCP 工具是外部注入的，不在 Asterwynd 的编译时安全控制范围内，这是一个真实的风险面。当前有三层保护：MCP 工具在注册时被分配 ToolOrigin.MCP，权限级别默认是 HIGH——所有 MCP 工具都需要审批才能执行，在 BUILD mode 下也不例外。MCP 工具权限走相同的 ModePolicy 决策链——如果 mode 的 profile 不允许 EXTERNAL_SIDE_EFFECT capability，MCP 工具直接 DENY。命令型 MCP 工具如果在执行侧调了 Bash，仍然受 CommandGuard 和 sandbox 约束。

但 MCP 工具的安全确实是当前最薄弱的环节——一个恶意的 MCP 服务端可以伪造 description 让模型频繁调用它、可以做数据外泄。这也是为什么 MCP 工具默认标记为 HIGH 风险 + EXTERNAL_SIDE_EFFECT capability——它的安全假设是"不可信"。
