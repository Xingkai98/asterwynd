# Issue tracker: GitHub

本仓库的 issue、PRD 和可交给 agent 执行的任务都发布到 GitHub Issues。仓库从 `git remote -v` 推断，当前为 `Xingkai98/asterwynd`。

Matt Pocock skills 需要发布或读取 issue 时，默认使用 `gh` CLI。

## 约定

- 创建 issue：`gh issue create --title "..." --body "..."`
- 读取 issue：`gh issue view <number> --comments`
- 列出 issue：`gh issue list --state open --json number,title,body,labels,comments`
- 评论 issue：`gh issue comment <number> --body "..."`
- 添加或移除标签：`gh issue edit <number> --add-label "..."` / `--remove-label "..."`
- 关闭 issue：`gh issue close <number> --comment "..."`

## 当 skill 要求发布到 issue tracker

创建 GitHub issue。多行正文使用 heredoc 或临时文件，避免 shell 转义破坏 Markdown。

## 当 skill 要求读取相关 ticket

运行 `gh issue view <number> --comments`，并同时关注标题、正文、评论、标签和当前状态。
