from __future__ import annotations

import fnmatch
import re
import subprocess
from pathlib import Path


DEFAULT_DENIED_PATTERNS = (
    ".git",
    ".git/**",
    "*.pem",
    "*.key",
    "*.p12",
    "*.pfx",
    "id_rsa",
    "id_ed25519",
    "id_ecdsa",
    "**/id_rsa",
    "**/id_ed25519",
    "**/id_ecdsa",
    "__pycache__",
    "__pycache__/**",
    "**/__pycache__/**",
    "*.pyc",
    "node_modules",
    "node_modules/**",
    "**/node_modules/**",
    ".venv",
    ".venv/**",
    "venv",
    "venv/**",
    ".mypy_cache",
    ".mypy_cache/**",
    ".pytest_cache",
    ".pytest_cache/**",
    ".ruff_cache",
    ".ruff_cache/**",
    "benchmarks/runs",
    "benchmarks/runs/**",
    # 工具创建的隔离 worktree（add-worktree-tool）：主模式工具不可直接读写
    ".asterwynd/worktrees/**",
)

# --- Sensitive dot names: the single shared predicate (design D12) ------------
#
# "What counts as a sensitive dot name" used to be defined in three unrelated
# places -- this module's globs, this module's `\b(mv|cp)\s+<src>` regexes, and
# `command_guard`'s frozensets -- and they had drifted (`.env.local` was denied
# by the read/write tools but allowed by the Bash guard). It is defined here
# once, and every consumer imports it.
#
# The predicate is deliberately **code, not a glob**: Python's `fnmatch` has no
# extglob support, so `.env.!(example|...)` silently matches nothing (verified:
# it returns False for both `.env.local` and `.env.example`), which would open
# the denial in both directions.

#: Suffix words marking a `.env.<...>` file as a committed TEMPLATE rather than
#: a credential file. `.env.example` is the de-facto standard; the rest are
#: recognized synonyms.
ENV_TEMPLATE_WORDS = frozenset({"example", "sample", "template", "dist", "defaults", "tpl"})

#: Dot-directories carrying credentials or repo metadata. Compared per path
#: **segment**, so `.gitignore` / `.github/` pass while `.git/config` and
#: `src/.git/hooks/x` are caught.
SENSITIVE_DOTDIRS = frozenset(
    {".git", ".ssh", ".aws", ".gnupg", ".kube", ".docker", ".netrc", ".npmrc", ".pypirc"}
)
#: Dot-files carrying credentials. The `.env` family is judged by
#: `is_env_sensitive_name` instead (it has the template exemption).
SENSITIVE_DOTFILES = frozenset({".netrc", ".npmrc", ".pypirc", ".gitconfig", ".git-credentials"})


def is_env_template_name(name: str) -> bool:
    """True when ``name`` is a ``.env``-family TEMPLATE (committed, no real values).

    ``.env.example`` / ``.env.sample`` / ``.env.template`` / ``.env.dist`` /
    ``.env.defaults`` / ``.env.tpl`` are templates. ``.env`` itself is not, and
    neither is any variant whose suffix carries a credential word --
    ``.env.example.local`` resolves to a credential because a suffix segment is
    not a template word.
    """
    if not name.startswith(".env."):
        return False
    rest = name[len(".env."):]
    if not rest:
        return False
    return all(part in ENV_TEMPLATE_WORDS for part in rest.split("."))


def is_env_sensitive_name(name: str) -> bool:
    """True when ``name`` is a ``.env``-family file that may carry real credentials.

    ``.env`` is the credential; ``.env.<suffix...>`` is a credential unless every
    suffix segment is a template word. Non-``.env`` names (``.envrc``,
    ``.environment``, ``app.env``, ``.env2``) are not this predicate's business.
    """
    if name == ".env":
        return True
    if not name.startswith(".env."):
        return False
    return not is_env_template_name(name)


def is_sensitive_dot_name(part: str) -> bool:
    """True when a single path **segment** names a sensitive dot file/dir."""
    if is_env_sensitive_name(part):
        return True
    return part in SENSITIVE_DOTDIRS or part in SENSITIVE_DOTFILES


#: `mv`/`cp` whose SOURCE is a credential path. The source is a positional
#: argument here rather than an IR field, and the `.env` family needs the
#: template exemption, so it goes through the shared predicate instead of a
#: regex alternation that would re-spell the template words.
_ENV_SOURCE = re.compile(r"\b(?:mv|cp)\s+(\S+)")


def _env_source_is_credential(command: str) -> bool:
    match = _ENV_SOURCE.search(command)
    if match is None:
        return False
    source = match.group(1).strip("'\"")
    # Every segment matters, not just the basename: `.git/config` is sensitive
    # because of the `.git` segment, not because `config` is.
    segments = [part for part in source.split("/") if part not in ("", ".")]
    return any(is_sensitive_dot_name(part) for part in segments)


def _match_allowlist(command: str) -> bool:
    """检查命令是否匹配允许列表前缀。支持子命令匹配。"""
    safe_prefixes = [
        # 版本控制 — 只允许读操作
        "git status", "git log", "git diff", "git show", "git branch",
        "git stash list", "git stash show",
        # 测试和构建
        "pytest", "python -m pytest", "python3 -m pytest",
        "uv run pytest", "uv run python -m pytest", "uv run python3 -m pytest",
        "uv", "pip",
        "npm test", "npm run", "npx", "yarn", "cargo", "make",
        # 文件查看
        "cat", "head", "tail", "wc", "sort", "uniq", "ls", "tree",
        "find", "fd", "rg", "grep",
        # 基本工具
        "echo", "pwd", "which", "env", "df", "du", "ps",
        # 文件操作（只允许低风险操作）
        "mkdir", "touch",
        # 包管理
        "pip install", "pip list", "pip show", "pip freeze",
    ]
    cmd_stripped = command.strip()
    for prefix in safe_prefixes:
        if cmd_stripped.startswith(prefix):
            return True
    return False

DEFAULT_DENYLIST = (
    r"rm\s+-rf\s+/",
    r"rm\s+-r[f]?\s+/",
    r"rm\s+--recursive\s+/",
    r"del\s+/[fF]\s+/",
    r"rmdir\s+/[sS]\s+/",
    r"format\s",
    r"mkfs\.",
    r"dd\s+if=",
    r">\s*/dev/sd[a-z]",
    r"dd\s+of=/dev/",
    r"shutdown",
    r"reboot",
    r"halt",
    r"poweroff",
    r"init\s+[06]",
    r"systemctl\s+(stop|restart|disable)\s",
    r"service\s+\w+\s+(stop|restart)",
    r"kill\s+-9\s",
    r"killall\s",
    r"pkill\s",
    r":\(\)\s*\{",  # fork bomb
    r"perl\s+-e\s",
    r"ruby\s+-e\s",
    r"php\s+-r\s",
    r"python3?\s+-c\b",
    r"python3?\s+-\s*<<",
    r"curl.*\|\s*(ba)?sh",
    r"wget.*\|\s*(ba)?sh",
    r"curl.*\|\s*(ba)?sh",
    r"find\s+.*-exec\s+rm\s",
    r"find\s+.*-delete\b",
    r"xargs\s+rm\s",
    r"git\s+reset\s+--hard",
    r"git\s+push\s+--force",
    r"git\s+branch\s+-D",
    r"chmod\s+777\s+/",
    r"chmod\s+-R\s+777",
    r"chown\s+-R\s+root",
    r">\s*/etc/",
    r">\s*/proc/",
    r">\s*/sys/",
    r"tee\s+/etc/",
    r"tee\s+/proc/",
    r"sed\s+-i.*/(etc|proc|sys)/",
    # The two `(mv|cp)\s+<source>` patterns used to live here. They matched on
    # the SOURCE token and could not tell a template from a credential, so
    # `cp .env.example /tmp/backup.txt` was denied. "Which argument is the
    # source" is expressible in the IR, so the guard's evaluator owns this now
    # (design D9); this module still covers the path-shaped sources that do not
    # depend on `.env` naming.
    # Source-position guard for sensitive sources. `.env.example` and friends
    # are templates (allowed); the credential forms are not. The `.env` family
    # is checked by `_env_source_is_credential` (below) so the template words
    # stay in one place rather than being re-spelled as a regex alternation.
    r"\b(mv|cp)\s+(/etc/|/proc/|/sys/)\S*",
    r"\b(mv|cp)\s+\S*/\.(?:git|ssh|aws|gnupg|kube|docker|netrc|npmrc|pypirc)(?![\w.-])",
    r"sudo\s",
    r"su\s+-",
    r"mount\s",
    r"umount\s",
    r"iptables\s",
    r"nft\s",
    r"docker\s+rm\s",
    r"docker\s+system\s+prune",
    r"kubectl\s+delete\s",
    r"DROP\s+(TABLE|DATABASE)",
    r"DELETE\s+FROM\s+\w+\s*;",  # no WHERE
    r"\$\(.*\)",          # command substitution: $(cmd)
    r"`[^`]*`",           # backtick command substitution: `cmd`
)


# 比较对象必须是规范化后的真实路径：macOS 上 /etc 是 /private/etc 的符号链接，
# 用未规范化的字面量比较会永不命中（等于敏感目录守卫可被符号链接绕过）。
_DENY_ROOTS = {Path(p).resolve() for p in ("/etc", "/proc", "/sys", "/dev", "/root", "/boot")}


class WorkspacePolicy:
    def __init__(
        self,
        workspace_root: str | Path | None = None,
        denied_patterns: tuple[str, ...] | list[str] | None = None,
        command_denylist: tuple[str, ...] | list[str] | None = None,
    ):
        self.workspace_root = Path(workspace_root or Path.cwd()).resolve()
        self.additional_roots: set[Path] = set()
        self.denied_patterns = tuple(denied_patterns or DEFAULT_DENIED_PATTERNS)

        denylist = list(DEFAULT_DENYLIST)
        if command_denylist:
            denylist.extend(command_denylist)
        self._denylist = tuple(denylist)

    @staticmethod
    def _is_within(parent: Path, child: Path) -> bool:
        try:
            child.relative_to(parent)
            return True
        except ValueError:
            return False

    def is_within_workspace(self, path: Path) -> bool:
        resolved = self.resolve(path)
        if self._is_within(self.workspace_root, resolved):
            return True
        return any(self._is_within(r, resolved) for r in self.additional_roots)

    def add_root(self, path: str, *, create: bool = False) -> Path:
        resolved = Path(path).expanduser().resolve()
        if self._is_within(self.workspace_root, resolved):
            raise ValueError(f"此路径已在主 workspace 范围内: {resolved}")
        if self._is_within(resolved, self.workspace_root):
            raise ValueError(f"不能添加主 workspace 的祖先目录，这会开放主 workspace 外的所有文件访问: {resolved}")
        if is_sensitive_root(resolved):
            raise ValueError(f"禁止添加系统敏感目录: {resolved}")
        if not resolved.exists():
            if create:
                try:
                    resolved.mkdir(parents=True, exist_ok=True)
                except OSError as exc:
                    raise ValueError(f"无法创建目录: {resolved} ({exc})") from exc
            else:
                raise ValueError(f"路径不存在: {resolved}")
        if resolved in self.additional_roots:
            return resolved
        self.additional_roots.add(resolved)
        return resolved

    def remove_root(self, path: str) -> None:
        resolved = Path(path).expanduser().resolve()
        if resolved == self.workspace_root:
            return
        self.additional_roots.discard(resolved)

    def list_roots(self) -> list[Path]:
        return [self.workspace_root, *sorted(self.additional_roots)]

    def resolve(self, path: str | Path) -> Path:
        raw_path = Path(path)
        if raw_path.is_absolute():
            return raw_path.resolve()
        return (self.workspace_root / raw_path).resolve()

    def assert_within_workspace(self, path: str | Path) -> Path:
        resolved = self.resolve(path)
        if self.is_within_workspace(resolved):
            return resolved
        raise PermissionError(f"Path is outside workspace: {path} -> {resolved}")

    def relative_path(self, path: str | Path) -> str:
        resolved = self.assert_within_workspace(path)
        if self._is_within(self.workspace_root, resolved):
            return resolved.relative_to(self.workspace_root).as_posix()
        for root in self.additional_roots:
            if self._is_within(root, resolved):
                return resolved.relative_to(root).as_posix()
        return resolved.as_posix()

    def is_denied(self, path: str | Path) -> bool:
        resolved = self.assert_within_workspace(path)
        # Sensitive dot names are judged by the shared predicate (design D12),
        # segment-wise, so both the bare (`cp x .env`) and nested
        # (`src/.git/hooks/x`) forms are covered. Template `.env` files are
        # deliberately NOT sensitive -- `.env.example` is committed so people
        # (and the agent) can see which variables a project needs.
        if not self._is_within(self.workspace_root, resolved):
            return self._deny_by_name(resolved.name)
        rel = resolved.relative_to(self.workspace_root).as_posix()
        parts = [part for part in rel.split("/") if part not in ("", ".")]
        if any(is_sensitive_dot_name(part) for part in parts):
            return True
        if is_sensitive_dot_name(resolved.name):
            return True
        candidates = {rel, resolved.name, *parts}
        for pattern in self.denied_patterns:
            normalized = pattern.strip("/")
            if any(fnmatch.fnmatchcase(candidate, normalized) for candidate in candidates):
                return True
            if fnmatch.fnmatchcase(rel, normalized):
                return True
        return False

    def _deny_by_name(self, name: str) -> bool:
        """Deny check for a path outside the workspace, where only the basename
        is meaningful (relative paths in the deny list do not apply)."""
        if is_sensitive_dot_name(name):
            return True
        for pattern in self.denied_patterns:
            if fnmatch.fnmatchcase(name, pattern.strip("/")):
                return True
        return False

    def assert_read_allowed(self, path: str | Path) -> Path:
        resolved = self.assert_within_workspace(path)
        if self.is_denied(resolved):
            raise PermissionError(f"Read denied by workspace policy: {resolved.as_posix()}")
        return resolved

    def assert_write_allowed(self, path: str | Path) -> Path:
        resolved = self.assert_within_workspace(path)
        if self.is_denied(resolved):
            raise PermissionError(f"Write denied by workspace policy: {resolved.as_posix()}")
        return resolved

    def assert_command_allowed(self, command: str) -> None:
        cmd_stripped = command.strip()
        for pattern in self._denylist:
            if re.search(pattern, cmd_stripped):
                raise PermissionError("Command denied by workspace policy")
        if _env_source_is_credential(cmd_stripped):
            raise PermissionError("Command denied by workspace policy")
        if _match_allowlist(cmd_stripped):
            return

    def snapshot_git_diff(self, stat: bool = False, timeout: float = 10.0) -> str:
        args = ["git", "diff", "--stat"] if stat else ["git", "diff"]
        result = subprocess.run(
            args,
            cwd=self.workspace_root,
            capture_output=True,
            text=True,
            timeout=timeout, errors="replace",
        )
        output = (result.stdout or result.stderr).strip()
        return output or "(no changes)"


def is_sensitive_root(path: str | Path) -> bool:
    """路径是否不允许作为 workspace 根：文件系统根 ``/`` 或 ``_DENY_ROOTS`` 及其子路径。

    以它们为根等于把整个文件系统（或系统敏感目录）交给该 workspace 的工具。
    CLI ``/workspace add``（``WorkspacePolicy.add_root``）与 Web hub「+ 添加」
    （``SessionManager.register_workspace``）共用本判定，避免两处守卫漂移。
    """
    resolved = Path(path).expanduser().resolve()
    if resolved == Path(resolved.anchor):
        return True
    return any(
        resolved == deny_root or WorkspacePolicy._is_within(deny_root, resolved)
        for deny_root in _DENY_ROOTS
    )
