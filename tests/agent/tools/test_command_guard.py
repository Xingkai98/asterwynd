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
    """设备豁免是**精确匹配**，不是前缀（review I2 回归）。

    早期实现把 `/dev/` 留在 `_EXTRA_DENYLIST` 的正则里，用一个 lookahead 排
    除豁免目标；但 `\\b` 不是 `/` 感知的，`/dev/null/sda` 里 `null` 后接 `/`
    同样满足 `\\b`，于是该目标被误判为「设备豁免」。现在 `/dev/` 不在这条
    正则里，豁免由 `_DEVICE_EXEMPT` 的精确相等判断唯一决定。
    """

    def test_denylist_mv_cp_branch_does_not_claim_dev(self) -> None:
        from agent.tools.command_guard import _EXTRA_DENYLIST

        for pattern in _EXTRA_DENYLIST:
            if "mv|cp" in pattern:
                assert "/dev/" not in pattern, (
                    "mv/cp 的 denylist 分支不应包含 /dev/：设备豁免是精确匹配，"
                    "正则无法表达 `\\b` 的 `/` 边界"
                )

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
