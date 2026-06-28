## 1. 规格

- [x] 1.1 新增 OpenSpec change，记录正式重命名范围、非目标和验收标准。
- [x] 1.2 更新 `cli`、`web-ui`、`configuration` 和 `benchmark` 的 spec delta。
- [x] 1.3 使用 `grill-with-docs` 或等价设计追问审视 `design.md`；本次追补基于当前代码、CONTEXT、README/Web/CLI 影响面完成，关键决策已写入设计文档。
- [x] 1.4 合入前同步对应 current spec 到 `openspec/specs/<capability>/spec.md`。

## 2. 测试

- [x] 2.1 新增或调整 CLI 交互 banner、`--no-banner`、单轮无 banner 和 benchmark runner 选择测试。
- [x] 2.2 新增或调整配置、benchmark runner 和品牌模块测试，覆盖 `ASTERWYND_*`、`asterwynd.yaml`、`AsterwyndConfig`、`AsterwyndRunner` 和宽/窄终端 banner。
- [x] 2.3 新增或调整 Web server/static asset 测试，覆盖品牌资产路径和页面标题。
- [x] 2.4 运行 Web 浏览器 smoke，确认 header 不遮挡现有控件。当前环境无 root 权限，已将 Chromium 依赖库解到本地 `.dev/playwright-libs/` 并通过 `LD_LIBRARY_PATH` 启动 Playwright；desktop/mobile header smoke 通过。

## 3. 实现

- [x] 3.1 新增共享品牌常量和 TUI banner 文本资产。
- [x] 3.2 CLI 交互模式接入 Asterwynd wordmark，并提供 `--no-banner`。
- [x] 3.3 Web UI header 接入 Asterwynd wordmark，并挂载品牌资产静态路径。
- [x] 3.4 README 中文/英文入口接入 wordmark、语言链接、slogan 和第一段介绍。
- [x] 3.5 将 Python project name、CLI script、配置文件、环境变量前缀、配置类型、benchmark runner 和活动 benchmark task 迁移到 Asterwynd。
- [x] 3.6 保留 `agent/` Python package 目录，不添加旧名兼容别名。
- [x] 3.7 清理验证过程中产生的无关依赖锁文件变更，避免 `uv.lock` 噪声混入本 change。

## 4. 验证

- [x] 4.1 运行目标测试：`uv run pytest -q tests/agent/test_config.py tests/agent/test_branding.py tests/test_cli.py tests/benchmark/test_cli_benchmark.py tests/benchmark/test_asterwynd_runner.py tests/benchmark/test_asterwynd_runner_timeout.py tests/web_tests/test_server.py tests/web_tests/test_session.py`，结果 86 passed。
- [x] 4.2 运行 `openspec validate --all --strict`，结果 24 passed, 0 failed。
- [x] 4.3 运行 `uv run python scripts/check_openspec_artifacts.py`，结果通过。
- [x] 4.4 运行相关文档影响检查，至少覆盖 README、README_EN、AGENTS、CONTEXT、docs/、OpenSpec 文档和活动 benchmark tasks；活动文件旧名扫描无残留，OpenSpec change 内保留旧名用于描述迁移动机和非兼容验收。
- [x] 4.5 运行全量测试：`uv run python -m pytest -q`，结果 475 passed, 7 skipped。

## 5. 合入后收尾

- [x] 5.1 PR 合入后，将本 change 归档到 `openspec/changes/archive/YYYY-MM-DD-rename-project-to-asterwynd/`。
- [x] 5.2 从 `docs/openspec-change-backlog.md` 移除本 change，并同步并行开发批次。
- [x] 5.3 运行 `openspec validate --all --strict` 和 `uv run python scripts/check_openspec_artifacts.py`。
