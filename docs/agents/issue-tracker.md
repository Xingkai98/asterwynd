# Issue tracker: GitHub

本仓库的 issue、PRD 和可交给 agent 执行的任务默认发布到 GitHub Issues。后端配置来自 `scripts/workflow_methods.json` 的 `ticket_tracker` 段，当前仓库目标为 `Xingkai98/asterwynd`，backend 默认值为 `github`。

Matt Pocock skills 需要发布或读取 issue 时，默认使用 `gh` CLI。

## 约定

- 创建 issue：`gh issue create --title "..." --body "..."`
- 读取 issue：`gh issue view <number> --comments`
- 列出 issue：`gh issue list --state open --json number,title,body,labels,comments`
- 评论 issue：`gh issue comment <number> --body "..."`
- 添加或移除标签：`gh issue edit <number> --add-label "..."` / `--remove-label "..."`
- 关闭 issue：`gh issue close <number> --comment "..."`

如果 `ticket_tracker.backend` 改成其他值，以上约定应替换为对应后端的等价命令。

## OpenSpec change 跟踪 issue

每个 OpenSpec 立项必须关联一个 GitHub issue 作为跟踪入口，创建时机为需求文档落定（proposal 阶段）：

- 标题以【feature】开头标明类型，例如 `【feature】Agent 侧 worktree 隔离工具`。
- 正文写明：背景、需求、OpenSpec change 路径（`openspec/changes/<change-id>/`）和跟踪约定。
- change 的 `proposal.md` 或 backlog 条目记录关联 issue 号（如 `issue #111`）。
- change 实现 PR 合入时，给对应 issue 添加完成说明 comment（写明合入的 PR 号与验证结果）并关闭。

## 当 skill 要求发布到 issue tracker

创建 GitHub issue。多行正文使用 heredoc 或临时文件，避免 shell 转义破坏 Markdown。

## 当 skill 要求读取相关 ticket

运行 `gh issue view <number> --comments`，并同时关注标题、正文、评论、标签和当前状态。
