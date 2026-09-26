"""Tests for command_guard — lightweight command tokenizer + argv semantic validation.

Covers design.md 第一/二轮：命令护栏是"护栏不是边界"——轻量分词 + argv 语义校验
（识别 rm 目标越界、重定向到 /etc、mv 目标敏感等）+ denylist 增强覆盖绕过面。
保持 default-allow（不破坏合法命令），高危句型命中即拒。
"""
from __future__ import annotations

import pytest

from agent.tools.command_guard import (
    CommandGuard,
    CommandVerdict,
    tokenize_command,
)


class TestTokenizer:
    def test_basic_command(self) -> None:
        assert tokenize_command("git status") == ["git", "status"]

    def test_quoted_args_preserved(self) -> None:
        assert tokenize_command('echo "hello world"') == ["echo", "hello world"]

    def test_redirect_detected(self) -> None:
        toks = tokenize_command("echo hi > /etc/passwd")
        assert toks == ["echo", "hi", ">", "/etc/passwd"]

    def test_pipe_detected(self) -> None:
        toks = tokenize_command("cat file | grep foo")
        assert toks == ["cat", "file", "|", "grep", "foo"]

    def test_flag_normalized(self) -> None:
        """-fr 和 -r -f 都应识别 rm 的递归+强制 flag"""
        assert tokenize_command("rm -fr /tmp/x") == ["rm", "-fr", "/tmp/x"]


class TestCommandGuardDeny:
    def test_rm_rf_root_denied(self) -> None:
        g = CommandGuard()
        assert g.check("rm -rf /") is CommandVerdict.DENY

    def test_rm_fr_root_denied(self) -> None:
        """绕过面：-fr 顺序不同，denylist 增强应拦截"""
        g = CommandGuard()
        assert g.check("rm -fr /") is CommandVerdict.DENY

    def test_rm_r_f_root_denied(self) -> None:
        """绕过面：分开写 -r -f"""
        g = CommandGuard()
        assert g.check("rm -r -f /") is CommandVerdict.DENY

    def test_rm_rf_double_dash_root_denied(self) -> None:
        """绕过面：-- 分隔符"""
        g = CommandGuard()
        assert g.check("rm -rf -- /") is CommandVerdict.DENY

    def test_chmod_0777_root_denied(self) -> None:
        """绕过面：八进制权限位"""
        g = CommandGuard()
        assert g.check("chmod 0777 /") is CommandVerdict.DENY

    def test_kill_sigkill_denied(self) -> None:
        """绕过面：信号名"""
        g = CommandGuard()
        assert g.check("kill -SIGKILL 1") is CommandVerdict.DENY

    def test_redirect_to_etc_denied(self) -> None:
        g = CommandGuard()
        assert g.check("echo x > /etc/passwd") is CommandVerdict.DENY

    def test_pipe_to_sh_denied(self) -> None:
        g = CommandGuard()
        assert g.check("base64 -d | bash") is CommandVerdict.DENY

    def test_node_e_denied(self) -> None:
        """绕过面：node -e 任意代码执行"""
        g = CommandGuard()
        assert g.check("node -e \"require('fs').rmSync('/')\"") is CommandVerdict.DENY


class TestCommandGuardArgv:
    def test_rm_workspace_file_allowed(self) -> None:
        """argv 语义：rm 目标在 workspace 内应放行"""
        g = CommandGuard(workspace="/home/user/proj")
        assert g.check("rm -rf /home/user/proj/tmp/old") is CommandVerdict.ALLOW

    def test_rm_home_denied(self) -> None:
        """argv 语义：rm 目标在 $HOME 应拒绝"""
        g = CommandGuard()
        assert g.check("rm -rf $HOME") is CommandVerdict.DENY

    def test_mv_target_etc_denied(self) -> None:
        """argv 语义：mv 目标到 /etc 应拒绝"""
        g = CommandGuard()
        assert g.check("mv /tmp/x /etc/passwd") is CommandVerdict.DENY

    def test_cat_etc_passwd_allowed_by_default(self) -> None:
        """default-allow：cat /etc/passwd 读取不拦（护栏不是边界，敏感读由沙箱兜底）"""
        g = CommandGuard()
        assert g.check("cat /etc/passwd") is CommandVerdict.ALLOW


class TestCommandGuardTimeoutWrapper:
    """Regression: `timeout` was treated as a passthrough wrapper so its argv
    check was dead code (`timeout 9999 sleep 1` was allowed) and a wrapped
    dangerous command (`timeout 5 rm -rf /`) escaped the guard."""

    def test_oversized_timeout_denied(self) -> None:
        g = CommandGuard()
        assert g.check("timeout 9999 sleep 1") is CommandVerdict.DENY
        assert g.last_reason == "timeout_range"

    def test_valid_timeout_allowed(self) -> None:
        g = CommandGuard()
        assert g.check("timeout 30 pytest tests/") is CommandVerdict.ALLOW

    def test_wrapped_destructive_command_denied(self) -> None:
        # A wrapped mv into a protected path must not pass just because
        # `timeout` is the first word (argv recursion into the wrapped command).
        # Target is `/root/foo`, not `/var/log/foo`: the latter is caught by the
        # denylist first, so the argv branch under test would never run
        # (fix-issue-247 R2 — this assertion previously used the look-alike
        # path `/etc-passwd/foo`, which is NOT under `/etc`).
        g = CommandGuard()
        assert g.check("timeout 5 mv /tmp/x /root/foo") is CommandVerdict.DENY
        assert g.last_reason == "mv_cp_dest"

    def test_wrapped_rm_rf_still_denied(self) -> None:
        # `timeout 5 rm -rf /` is caught by the denylist before argv recursion.
        g = CommandGuard()
        assert g.check("timeout 5 rm -rf /") is CommandVerdict.DENY


class TestCommandGuardDefaultAllow:
    def test_safe_git_allowed(self) -> None:
        g = CommandGuard()
        assert g.check("git status") is CommandVerdict.ALLOW

    def test_pytest_allowed(self) -> None:
        g = CommandGuard()
        assert g.check("pytest tests/test_x.py") is CommandVerdict.ALLOW

    def test_unknown_command_allowed(self) -> None:
        """default-allow：未知命令不拦（不 deny-by-default）"""
        g = CommandGuard()
        assert g.check("my-custom-tool --flag") is CommandVerdict.ALLOW


class TestCommandGuardLastReason:
    """CommandGuard.last_reason exposes the granular rejection category so
    sandbox trace events can carry a meaningful reason (design.md Decision 6)."""

    def test_reason_denylist(self) -> None:
        g = CommandGuard()
        g.check("shutdown now")
        assert g.last_reason == "denylist"

    def test_reason_pipe_to_shell(self) -> None:
        g = CommandGuard()
        g.check("cat file | sh")
        assert g.last_reason == "pipe_to_shell"

    def test_reason_protected_redirect(self) -> None:
        # Target is genuinely under a protected root but not covered by the
        # denylist's redirect regex (which requires literal /etc/, /proc/, /sys/),
        # so the argv check fires. Target is `/var/log/foo`, not the look-alike
        # `/etc-passwd/foo` (fix-issue-247 R2: the latter is not under /etc).
        g = CommandGuard()
        g.check("echo x > /var/log/foo")
        assert g.last_reason == "protected_redirect"

    def test_reason_rm_target_escape(self) -> None:
        g = CommandGuard()
        g.check("rm -rf /")
        assert g.last_reason == "rm_target_escape"

    def test_reason_mv_cp_dest(self) -> None:
        # Target is genuinely under a protected root but not covered by the
        # denylist's mv/cp regex (which requires literal /etc/, /proc/, /sys/,
        # /var/), so the argv check fires. Target is `/root/foo`, not the
        # look-alike `/etc-passwd/foo` (fix-issue-247 R2).
        g = CommandGuard()
        g.check("mv /tmp/x /root/foo")
        assert g.last_reason == "mv_cp_dest"

    def test_reason_chmod_bits(self) -> None:
        # The broad chmod denylist catches `chmod 0777 /` before the argv check;
        # unit-test the fallback branch directly (defense in depth).
        g = CommandGuard()
        g._check_chmod(tokenize_command("chmod 0777 /"))
        assert g.last_reason == "chmod_bits"

    def test_reason_timeout_range(self) -> None:
        g = CommandGuard()
        g.check("timeout 9999 sleep 1")
        assert g.last_reason == "timeout_range"

    def test_reason_none_on_allow(self) -> None:
        g = CommandGuard()
        assert g.check("git status") is CommandVerdict.ALLOW
        assert g.last_reason is None

    def test_reason_reset_on_subsequent_check(self) -> None:
        g = CommandGuard()
        g.check("shutdown now")
        assert g.last_reason == "denylist"
        g.check("git status")
        assert g.last_reason is None


# --- fix-issue-247: 路径段边界 / 设备豁免 / `..` 穿越 -----------------------


class TestPathSegmentBoundary:
    """受保护路径与工作区边界按**路径段**判定（issue #247 根因）。

    裸 `str.startswith(prefix)` 会把 `/various.txt` 当作 `/var` 下的路径，
    也会把 `/tmp/ws-evil` 当作工作区 `/tmp/ws` 内的路径。
    """

    @pytest.mark.parametrize(
        "command",
        [
            # fd 前缀重定向：tokenizer 把 2>/dev/null 拆成 '2' '>' '/dev/null'
            "ls -la 2>/dev/null",
            "echo hi > /dev/null",
            "cmd > /dev/null 2>&1",
            "python3 x.py > /dev/null 2>&1",
            "git log 2>/dev/null | head",
            "cat f 2>/dev/null",
        ],
    )
    def test_fd_redirect_to_devnull_allowed(self, command: str) -> None:
        assert CommandGuard().check(command) is CommandVerdict.ALLOW

    @pytest.mark.parametrize(
        "command",
        [
            # 假朋友前缀：与 /var /root /boot /etc /proc /sys /dev 仅字符串相同
            "echo x > /various.txt",
            "echo x > /variable",
            "echo x > /rooted.log",
            "echo x > /bootstrap.log",
            "echo x > /etcetera.conf",
            "echo x > /sysadmin.log",
            "echo x > /procmail.rc",
            "echo x > /devops.txt",
        ],
    )
    def test_lookalike_prefix_allowed(self, command: str) -> None:
        assert CommandGuard().check(command) is CommandVerdict.ALLOW

    @pytest.mark.parametrize(
        "command",
        [
            "cp r.md docs/.draft/x.md",
            "mv x src/.cache/",
            "cp x /tmp/.hidden/",
        ],
    )
    def test_ordinary_dotdir_allowed(self, command: str) -> None:
        """普通点目录不是敏感目标（原 `\\S*/\\.[a-z]+\\b` 无差别命中）。"""
        assert CommandGuard().check(command) is CommandVerdict.ALLOW

    @pytest.mark.parametrize(
        "command",
        [
            # workspace=/tmp/ws 时，这些都在工作区之外
            "rm -rf /tmp/ws-evil",
            "rm -rf /tmp/ws-evil/sub",
            "rm -rf /tmp/wsX",
        ],
    )
    def test_workspace_prefix_collision_denied(self, command: str) -> None:
        """前缀相同不构成包含关系：/tmp/ws-evil 不在 /tmp/ws 之下。"""
        g = CommandGuard(workspace="/tmp/ws")
        assert g.check(command) is CommandVerdict.DENY
        assert g.last_reason == "rm_target_escape"

    def test_workspace_inside_still_allowed(self) -> None:
        g = CommandGuard(workspace="/tmp/ws")
        assert g.check("rm -rf /tmp/ws/build") is CommandVerdict.ALLOW

    @pytest.mark.parametrize(
        "command",
        [
            "rm -rf /tmp/ws/../etc",
            "rm -rf /tmp/ws/../../etc",
            "rm -rf /tmp/ws/../etc/passwd",
        ],
    )
    def test_dotdot_traversal_denied(self, command: str) -> None:
        """`..` 规范化后落在工作区之外，不得因字面前缀匹配而放行。"""
        g = CommandGuard(workspace="/tmp/ws")
        assert g.check(command) is CommandVerdict.DENY

    @pytest.mark.parametrize("command", ["rm -rf /tmp/ws", "rm -rf /tmp/ws/"])
    def test_workspace_root_denied(self, command: str) -> None:
        """删工作区根本身的破坏性与越界相当。"""
        g = CommandGuard(workspace="/tmp/ws")
        assert g.check(command) is CommandVerdict.DENY


class TestSensitiveDotDirectories:
    """`_check_mv_cp` 的敏感点目录判定按**段**比较（不是正则前缀）。"""

    @pytest.mark.parametrize(
        "command",
        [
            # 误报检查：以敏感点目录名为**前缀**的普通文件/目录
            "cp x .gitignore",
            "cp x .env.example",
            "cp x .dockerignore",
            "cp x .github/workflows/ci.yml",
            "cp x src/.gitignore",
            "cp x .environment",
        ],
    )
    def test_sensitive_lookalike_allowed(self, command: str) -> None:
        assert CommandGuard().check(command) is CommandVerdict.ALLOW

    @pytest.mark.parametrize(
        "command",
        [
            # 裸形态
            "cp x .env",
            "mv y .ssh/id_rsa",
            "cp x .git/config",
            # 嵌套形态（原 `\\S*/\\.[a-z]+\\b` 能拦，正则白名单会漏）
            "cp x src/.git/hooks/pre-commit",
            "cp x sub/.env/secrets",
            "cp x proj/.npmrc",
            "cp x a/.git/",
        ],
    )
    def test_sensitive_dotdir_denied(self, command: str) -> None:
        assert CommandGuard().check(command) is CommandVerdict.DENY


class TestDeviceExemptionScope:
    """设备豁免只覆盖重定向 + mv/cp（用户拍板 Q2/Q3）。"""

    def test_redirect_to_devnull_allowed(self) -> None:
        assert CommandGuard().check("echo x > /dev/null") is CommandVerdict.ALLOW

    def test_cp_to_devnull_allowed(self) -> None:
        assert CommandGuard().check("cp x /dev/null") is CommandVerdict.ALLOW

    def test_rm_devnull_still_denied(self) -> None:
        """豁免不扩展到 rm（Q2 拍板：不放宽 rm 对 /dev/ 的拦截面）。"""
        assert CommandGuard().check("rm -rf /dev/null") is CommandVerdict.DENY

    def test_dev_fd_not_exempt(self) -> None:
        """Q3 拍板：/dev/fd/* 不纳入豁免。"""
        assert CommandGuard().check("echo x > /dev/fd/1") is CommandVerdict.DENY

    @pytest.mark.parametrize(
        "command",
        [
            "echo x > /dev/sda",
            "dd if=/dev/zero of=/dev/sda",
            "yes > /dev/null",
        ],
    )
    def test_other_dev_targets_still_denied(self, command: str) -> None:
        assert CommandGuard().check(command) is CommandVerdict.DENY


class TestRealProtectedTargetsStillDenied:
    """真危险对照：修复不得放松任何既有拦截面。"""

    @pytest.mark.parametrize(
        "command",
        [
            "echo x > /etc/passwd",
            "echo x > /var/log/syslog",
            "echo x > /etc/shadow",
            "rm -rf /",
            "rm -rf /var",
            "rm -rf /etc",
            "cp a /etc/x",
            "cp a /var/log/x",
            "chmod 777 /",
            "mv x /etc/passwd",
        ],
    )
    def test_real_protected_denied(self, command: str) -> None:
        assert CommandGuard().check(command) is CommandVerdict.DENY


class TestDeviceExemptIsExactMatch:
    """设备豁免是**精确匹配**，不是前缀（review I2 / R7-1）。

    早期实现用 lookahead 在正则里排豁免目标，但 `\b` 不是 `/` 感知的，
    `/dev/null/sda` 里 `null` 后接 `/` 同样满足 `\b`，被误判为「设备豁免」。
    现在豁免的判定归 `_check_mv_cp`（精确相等），全文扫描的 `/dev/` 分支
    用**后继分隔符**做 lookahead（空白/分号/引号/管道 或行尾），不再依赖 `\\b`。

    断言**行为**而非实现：不检查正则里有没有 `/dev/`（那是实现细节，
    R7-1 已把 `/dev/` 的全文覆盖加回来）。
    """

    @pytest.mark.parametrize(
        "target",
        ["/dev/sda", "/dev/fd/1", "/dev/tcp/x", "/dev/null/sda", "/dev/null/../sda"],
    )
    def test_non_exempt_dev_targets_denied(self, target: str) -> None:
        assert CommandGuard().check(f"cp x {target}") is CommandVerdict.DENY


class TestChainedCommandSegments:
    """链式命令里每一段都要过 argv 检查（review I1/I2 回归）。

    `_check_argv` 原先只看 `tokens[0]`，所以 `cd /tmp && cp evil ~/.ssh/x`
    里的 `cp` 完全不检查——修复前该形态在 master 上被 denylist 拦住，
    移除点目录正则后变成 ALLOW（拦截面收缩）。
    """

    @pytest.mark.parametrize(
        "command",
        [
            "cd /tmp && cp evil ~/.ssh/authorized_keys",
            'bash -c "cp evil ~/.ssh/authorized_keys"',
            "true; cp evil sub/.env/secrets",
            "cd /tmp && cp evil .git/hooks/pre-commit",
            "cd /tmp && cp evil a/.env",
            "echo x && cp evil .env",
            "ls && mv evil .git/config",
        ],
    )
    def test_chained_sensitive_dotdir_denied(self, command: str) -> None:
        assert CommandGuard().check(command) is CommandVerdict.DENY

    @pytest.mark.parametrize(
        "command",
        [
            "cd /tmp && mv a /root/foo",
            "true; mv a /boot/foo",
            "cd /tmp && cp a /etc/x",
            "echo x && chmod 777 /etc/x",
            "cd /tmp && rm -rf /var",
        ],
    )
    def test_chained_protected_target_denied(self, command: str) -> None:
        assert CommandGuard().check(command) is CommandVerdict.DENY

    @pytest.mark.parametrize(
        "command",
        [
            "cd /tmp && cp x .gitignore",
            "cd /tmp && ls -la 2>/dev/null",
            "echo a && echo b",
            "git add . && git commit -m x",
            "cd /tmp && cp x out.txt",
            "pytest -q && git status",
        ],
    )
    def test_chained_benign_still_allowed(self, command: str) -> None:
        assert CommandGuard().check(command) is CommandVerdict.ALLOW


class TestDeviceLookaheadSegmentBoundary:
    """豁免的 lookahead 必须按段判定（review I2）。

    `\\b` 不是 `/` 感知的：`/dev/null/sda` 里 `null` 后接 `/`，`\\b` 成立，
    于是该目标被误判为「设备豁免」，绕过了 `_EXTRA_DENYLIST` 的 mv/cp 分支。
    """

    @pytest.mark.parametrize(
        "command",
        [
            "cd /tmp && cp evil /dev/null/sda",
            "echo hi && cp evil /dev/null/sda",
            "cd /tmp && cp evil /dev/null/../sda",
            "cp evil /dev/null/sda",
            "cp evil /dev/fd/1",
        ],
    )
    def test_dev_subpath_not_exempt(self, command: str) -> None:
        assert CommandGuard().check(command) is CommandVerdict.DENY

    @pytest.mark.parametrize(
        "command",
        [
            "cp x /dev/null",
            "echo x > /dev/null",
            "cmd > /dev/null 2>&1",
            "cp x /dev/stdout",
        ],
    )
    def test_exact_device_target_still_exempt(self, command: str) -> None:
        assert CommandGuard().check(command) is CommandVerdict.ALLOW


class TestNewlineSeparatedCommands:
    """`\\n` 是 shell 的命令分隔符，但 tokenizer 把它折成空白（review R2）。

    `cd /tmp\\ncp evil a/.env` 在 shell 里是两条命令；修复前它是**单个 segment**，
    第二个 `cp` 完全不检查（master 上 DENY → 修复后 ALLOW）。
    """

    @pytest.mark.parametrize(
        "command",
        [
            "cd /tmp\ncp evil ~/.ssh/authorized_keys",
            "cd /tmp\ncp evil a/.env",
            "echo hi\ncp evil /dev/sda",
            "cd /tmp\nmv evil sub/.env/secrets",
            "ls\nrm -rf /var",
            "cd /tmp\r\ncp evil .env",
        ],
    )
    def test_newline_separated_denied(self, command: str) -> None:
        assert CommandGuard().check(command) is CommandVerdict.DENY

    @pytest.mark.parametrize(
        "command",
        [
            "cd /tmp\nls -la",
            "git add .\ngit commit -m x",
            "pytest -q\nuv run ruff check",
        ],
    )
    def test_newline_separated_benign_allowed(self, command: str) -> None:
        assert CommandGuard().check(command) is CommandVerdict.ALLOW


class TestShellGroupingAndFlags:
    """分组与组合 flag 的覆盖（review R2 第二轮）。

    `(...)` / `{ ...; }` 里的命令是独立命令；`bash -lc` / `zsh -ic` 与 `-c`
    跑同样的 payload；`env` 前缀不改变被执行的命令。这些形态在修复过程中
    一度从 DENY 退化成 ALLOW（master 上都是 DENY）。
    """

    @pytest.mark.parametrize(
        "command",
        [
            "cd /tmp && (cp evil ~/.ssh/authorized_keys)",
            "(cp evil ~/.ssh/authorized_keys)",
            "cd /tmp && { cp evil a/.env; }",
            "cd /tmp && { cp evil /dev/sda; }",
            "(cd /tmp; cp evil ~/.ssh/authorized_keys)",
        ],
    )
    def test_grouped_command_denied(self, command: str) -> None:
        assert CommandGuard().check(command) is CommandVerdict.DENY

    @pytest.mark.parametrize(
        "command",
        [
            'bash -lc "cp evil a/.env"',
            'zsh -ic "cp evil a/.env"',
            '/usr/bin/env bash -c "cp evil a/.env"',
            'bash -c "cp evil a/.env"',
            'sh -c "cp evil a/.env"',
        ],
    )
    def test_shell_flags_and_env_prefix_denied(self, command: str) -> None:
        assert CommandGuard().check(command) is CommandVerdict.DENY

    @pytest.mark.parametrize(
        "command",
        ["(ls)", "cd /tmp && (ls -la)", "bash -lc ls", "bash -c true"],
    )
    def test_grouping_and_flags_benign_allowed(self, command: str) -> None:
        assert CommandGuard().check(command) is CommandVerdict.ALLOW


class TestNestedShellRecursionIsBounded:
    """`bash -c "bash -c …"` 嵌套必须有界（review R2 实测无限递归）。"""

    def test_nested_within_limit_denied(self) -> None:
        inner = 'cp evil a/.env'
        for depth in range(1, 4):
            command = "bash -c " * depth + f'"{inner}"'
            assert CommandGuard().check(command) is CommandVerdict.DENY, depth

    def test_deep_nesting_terminates(self) -> None:
        # 超过上限即停止解包：不挂、不抛 RecursionError（护栏不是边界）。
        command = "bash -c " * 20 + '"cp evil a/.env"'
        assert CommandGuard().check(command) in (
            CommandVerdict.ALLOW,
            CommandVerdict.DENY,
        )


class TestShellKeywordPrefixedSegments:
    """shell 关键字引领的段里，命令仍须被检查（review R2 第三轮）。

    `if true; then cp x ~/.ssh/id_rsa; fi` 按 `;` 切分后，第二段以 `then`
    开头，`cp` 不是 tokens[0] —— master 靠「正则搜全文」拦住它，段级方案
    需要显式跳过关键字。
    """

    @pytest.mark.parametrize(
        "command",
        [
            "if true; then cp x ~/.ssh/authorized_keys; fi",
            "if true; then cp x .env; fi",
            "for f in *; do cp $f .env; done",
            "while true; do cp x .env; done",
            "time cp x .env",
            "exec cp x .env",
            "eval cp x .env",
        ],
    )
    def test_keyword_prefixed_command_denied(self, command: str) -> None:
        assert CommandGuard().check(command) is CommandVerdict.DENY

    @pytest.mark.parametrize(
        "command",
        [
            "if true; then ls; fi",
            "for f in *; do echo $f; done",
            "while true; do sleep 1; break; done",
        ],
    )
    def test_keyword_prefixed_benign_allowed(self, command: str) -> None:
        assert CommandGuard().check(command) is CommandVerdict.ALLOW


class TestShellPayloadParsingEdgeCases:
    """`-c` payload 解析的边界（review R5，全部实测 master 为 DENY）。"""

    @pytest.mark.parametrize(
        "command",
        [
            "env -i bash -c 'cp evil a/.env'",
            "env -u FOO bash -c 'cp evil a/.env'",
            "env --ignore-environment bash -c 'cp evil a/.env'",
            "env -i -- bash -c 'cp evil a/.env'",
        ],
    )
    def test_env_with_options_denied(self, command: str) -> None:
        assert CommandGuard().check(command) is CommandVerdict.DENY

    @pytest.mark.parametrize(
        "command",
        [
            "bash --norc -c 'cp evil a/.env'",
            "sh --norc -c 'cp evil a/.env'",
            "bash --rcfile foo -c 'cp evil a/.env'",
        ],
    )
    def test_long_option_must_not_hijack_dash_c(self, command: str) -> None:
        """`--norc` 含字母 c，但只有短选项簇能携带 `-c`（review R5 回归）。"""
        assert CommandGuard().check(command) is CommandVerdict.DENY

    @pytest.mark.parametrize(
        "command",
        [
            "bash -c 'echo hi' -c 'cp evil a/.env'",
            "bash -c ls -c 'cp evil a/.env'",
        ],
    )
    def test_repeated_dash_c_checks_every_payload(self, command: str) -> None:
        assert CommandGuard().check(command) is CommandVerdict.DENY

    @pytest.mark.parametrize(
        "command",
        ["cp evil a/.env\r\nls", "cp evil a/.env \r\nls"],
    )
    def test_crlf_destination_not_masked_by_carriage_return(self, command: str) -> None:
        """`\\r` 若不切分，会粘在目标末尾使 `a/.env` 变成 `a/.env\\r`。"""
        assert CommandGuard().check(command) is CommandVerdict.DENY


class TestPayloadChannelSharesKeywordStripping:
    """关键字跳过必须在 argv 与 payload 两条通道的共用入口（review R4 I-1）。

    R2 只在 `_check_argv_segment` 里跳关键字，payload 通道（`_strip_wrappers`）
    没跳，于是 `if true; then bash -c '…'; fi` 两条通道都放行。
    """

    @pytest.mark.parametrize(
        "command",
        [
            "if true; then bash -c 'cp evil ~/.ssh/authorized_keys'; fi",
            "for f in *; do env -i bash -c 'cp evil ~/.ssh/authorized_keys'; done",
            "! bash -c 'cp evil ~/.ssh/authorized_keys'",
            "eval bash -c 'cp evil ~/.ssh/authorized_keys'",
            "time bash -c 'cp evil ~/.ssh/authorized_keys'",
            "exec env -u FOO bash -c 'cp evil ~/.ssh/authorized_keys'",
        ],
    )
    def test_keyword_led_payload_denied(self, command: str) -> None:
        assert CommandGuard().check(command) is CommandVerdict.DENY


class TestPayloadPositionalArgsDoNotMaskScript:
    """`bash -c 'SCRIPT' $0 $1` 的位置参数不得掩盖 SCRIPT（review R4 I-2）。

    join 后的串末尾被当作 dest，于是真正的 script 被位置参数顶掉。
    """

    @pytest.mark.parametrize(
        "command",
        [
            "bash -c 'cp evil ~/.ssh/authorized_keys' extra",
            "env -i bash -c 'cp evil ~/.ssh/authorized_keys' extra",
            "cd /tmp && bash -c 'cp evil ~/.ssh/authorized_keys' extra more",
        ],
    )
    def test_positional_arg_does_not_mask_script(self, command: str) -> None:
        assert CommandGuard().check(command) is CommandVerdict.DENY

    def test_unquoted_payload_still_joined(self) -> None:
        """未加引号形态仍需 join 才能看出 dest（这条守住 I-2 的修法不倒退）。"""
        assert CommandGuard().check("bash -c cp evil a/.env") is CommandVerdict.DENY


class TestEnvSplitString:
    """`env -S '<cmd>'` 的值就是要执行的命令（review R4 I-3）。"""

    @pytest.mark.parametrize(
        "command",
        [
            "env -S 'cp evil ~/.ssh/authorized_keys'",
            "env --split-string 'cp evil ~/.ssh/authorized_keys'",
        ],
    )
    def test_split_string_value_checked(self, command: str) -> None:
        assert CommandGuard().check(command) is CommandVerdict.DENY

    def test_split_string_benign_allowed(self) -> None:
        assert CommandGuard().check("env -S 'ls -la'") is CommandVerdict.ALLOW


class TestSensitiveDotdirWholeTextScan:
    """敏感点目录必须**全文扫描**，不能只靠段级 argv（review R6-1）。

    `nice bash -c '…'`、`bash <<< '…'`、`echo '…' | env -i bash` 里的 `cp`
    既不段首、也不在 argv 通道可见的位置；段级判定看不见，master 靠全文正则
    能拦。移除非正则后这 9 条从 DENY 变 ALLOW（本 change 引入的回归）。
    """

    @pytest.mark.parametrize(
        "command",
        [
            "nice bash -c 'cp evil ~/.ssh/authorized_keys'",
            "setsid bash -c 'cp evil ~/.ssh/authorized_keys'",
            "xargs sh -c 'cp evil ~/.ssh/authorized_keys'",
            "busybox sh -c 'cp evil ~/.ssh/authorized_keys'",
            "stdbuf -o0 bash -c 'cp evil ~/.ssh/authorized_keys'",
            "find . -exec sh -c 'cp evil ~/.ssh/authorized_keys' ;",
            "bash -s <<< 'cp evil ~/.ssh/authorized_keys'",
            "bash <<< 'cp evil ~/.ssh/authorized_keys'",
            "echo 'cp evil ~/.ssh/authorized_keys' | env -i bash",
        ],
    )
    def test_launcher_and_pipe_forms_denied(self, command: str) -> None:
        assert CommandGuard().check(command) is CommandVerdict.DENY

    @pytest.mark.parametrize(
        "command",
        [
            # 否定前瞻必须挡住「点目录名后接 -/./词字符」的普通文件
            "cp x .env.example",
            "cp x .gitignore",
            "cp x .github/w.yml",
            "cp x .dockerignore",
            "cp x .environment",
            "cp x .netrc.example",
        ],
    )
    def test_dotdir_lookalikes_still_allowed(self, command: str) -> None:
        assert CommandGuard().check(command) is CommandVerdict.ALLOW


class TestDevWholeTextCoverage:
    """`/dev/` 目标的**全文覆盖**（review R7-1）。

    `_check_mv_cp` 的精确豁免只在 `mv`/`cp` 居段首时生效；launcher 前缀
    （`nice cp evil /dev/sda`）走不到它，故全文扫描必须也覆盖 `/dev/`。
    45 条 launcher×target 组合在 R7-1 时 master-DENY → head-ALLOW。
    """

    @pytest.mark.parametrize(
        "command",
        [
            "nice cp evil /dev/sda",
            "nice -n 10 cp evil /dev/sda",
            "setsid cp evil /dev/nvme0n1",
            "xargs cp evil /dev/sdb",
            "busybox cp evil /dev/mmcblk0",
            "find . -exec cp evil /dev/sda ;",
            "nice bash -c 'cp x /dev/sda'",
            "bash <<< 'cp x /dev/sda'",
            "echo 'cp x /dev/sda' | env -i bash",
        ],
    )
    def test_launcher_dev_target_denied(self, command: str) -> None:
        assert CommandGuard().check(command) is CommandVerdict.DENY

    @pytest.mark.parametrize(
        "command",
        [
            "cp x /dev/null",
            "nice cp x /dev/null",
            "echo hi > /dev/null",
            "ls -la 2>/dev/null",
            "cmd > /dev/null 2>&1",
            "cp x /dev/stdout",
        ],
    )
    def test_device_exempt_targets_still_allowed(self, command: str) -> None:
        assert CommandGuard().check(command) is CommandVerdict.ALLOW

    @pytest.mark.parametrize(
        "command",
        [
            # /dev/ 的 lookahead 必须按后继分隔符判定，不能退回 `\\b`。
            # 段首形态（`cp x /dev/null/sda`）会被 `_check_mv_cp` 的
            # `_within(dest, "/dev")` 兜住、**测不到**全文通道的 lookahead；
            # 必须用 launcher 前缀形态才能真锁住它（review R9-1）。
            "cp x /dev/null/sda",
            "cp x /dev/nullx",
            "cp x /dev/null.txt",
            "nice cp evil /dev/null/sda",
            "setsid cp evil /dev/null/sda",
            "echo hi && nice cp evil /dev/nullx",
            "busybox cp evil /dev/null.txt",
            "nice cp evil /dev/null/../sda",
        ],
    )
    def test_dev_null_prefixed_targets_not_exempt(self, command: str) -> None:
        assert CommandGuard().check(command) is CommandVerdict.DENY


class TestFullTextChannelScope:
    """全文扫描通道的**覆盖面边界**（review R8-1 / R7-2 的守护）。

    这条通道只匹配**带路径分隔符**的敏感名，两个方向都锁：
    - 引号内作为**数据**提及裸名（`grep -rn "cp x .env" docs/`）→ 放行；
    - launcher/herestring/pipe 里的**写命令**（带斜杠）→ 拒绝。

    没有这组测试，R7-2 的收窄是**无守护**的：将来若把斜杠要求放宽回去，
    CI 会全绿（review R8 明确指出）。
    """

    @pytest.mark.parametrize(
        "command",
        [
            'grep -rn "cp x .env" docs/',
            'rg -F "cp x .env" tests/',
            'git log --grep="mv x .git/config"',
            'sed -n "/cp x .env/p"',
            'printf "%s" "cp x .env"',
            'git commit -m "add cp x .env regression test"',
            'awk "/cp x .env/"',
            'echo "cp x .env"',
        ],
    )
    def test_quoted_mention_allowed(self, command: str) -> None:
        assert CommandGuard().check(command) is CommandVerdict.ALLOW

    @pytest.mark.parametrize(
        "command",
        [
            "nice cp x src/.ssh/id_rsa",
            "setsid cp x src/.git/config",
            "bash <<< 'cp x src/.env'",
            "echo 'cp x /var/log/f' | env -i bash",
            "nice cp evil /dev/sda",
        ],
    )
    def test_launcher_write_with_separator_denied(self, command: str) -> None:
        assert CommandGuard().check(command) is CommandVerdict.DENY

    def test_bare_name_at_segment_head_still_denied(self) -> None:
        """裸 `.env` 由**段级**通道负责 —— 这条锁住两通道的分工。"""
        assert CommandGuard().check("cp x .env") is CommandVerdict.DENY
