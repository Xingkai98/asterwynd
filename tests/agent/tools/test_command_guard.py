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
        g = CommandGuard()
        assert g.check("timeout 5 mv /tmp/x /etc-passwd/foo") is CommandVerdict.DENY
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
        # Target starts with a protected prefix but is not matched by the
        # denylist regex (which requires literal /etc/), so the argv check fires.
        g = CommandGuard()
        g.check("echo x > /etc-passwd/foo")
        assert g.last_reason == "protected_redirect"

    def test_reason_rm_target_escape(self) -> None:
        g = CommandGuard()
        g.check("rm -rf /")
        assert g.last_reason == "rm_target_escape"

    def test_reason_mv_cp_dest(self) -> None:
        # Target starts with a protected prefix but is not matched by the
        # denylist regex (which requires literal /etc/), so the argv check fires.
        g = CommandGuard()
        g.check("mv /tmp/x /etc-passwd/foo")
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
