"""platform-gate 实现单测（tasks 2.1-2.4）。

覆盖：--apply 的 GET-modify-PUT payload 构造（幂等、四必需字段、enabled→布尔、
restrictions:null、剔除只读派生字段、保留 reviews 可写子字段、任意深度
`_description` 不进 PUT body）；--verify 白名单归一化比对（一致 exit 0 /
漂移 exit 1 / null 缺失视为漂移不崩溃 / contexts 集合比对 / 忽略只读派生字段）；
错误处理 fail-closed（gh 缺失 / 认证失败 / API 非零 / schema 非法 / git remote
解析失败 → exit 2）；目标 JSON schema 校验。

隔离：所有 CLI 级测试强制 `--repo` 覆盖 + mock subprocess.run（gh 与 git 都
mock），避免意外命中真实仓（grill Q8 / design D9）。
"""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

import pytest

import scripts.platform_gate as pg

REPO_ROOT = Path(__file__).resolve().parents[1]
REAL_CONFIG = REPO_ROOT / "scripts" / "platform-gate.json"
REPO = "Xingkai98/asterwynd"


# ── mock 辅助 ─────────────────────────────────────────────────────────


def _cp(code: int, out: str, err: str) -> SimpleNamespace:
    return SimpleNamespace(returncode=code, stdout=out, stderr=err)


def _old_get() -> dict:
    """当前实况（apply 前）：benchmark-gate 未进 required、conversation 未开启。"""
    return {
        "url": "https://api.github.com/repos/Xingkai98/asterwynd/branches/master/protection",
        "required_status_checks": {
            "strict": True,
            "contexts": ["validate"],
            "checks": [{"context": "validate", "app_id": 15368}],
            "contexts_url": "https://api.github.com/repos/Xingkai98/asterwynd/branches/master/required_status_checks/contexts",
        },
        "required_pull_request_reviews": {
            "url": "https://api.github.com/repos/Xingkai98/asterwynd/branches/master/required_pull_request_reviews",
            "dismiss_stale_reviews": False,
            "require_code_owner_reviews": False,
            "required_approving_review_count": 0,
        },
        "required_conversation_resolution": {
            "enabled": False,
            "url": "https://api.github.com/repos/Xingkai98/asterwynd/branches/master/required_conversation_resolution",
        },
        "enforce_admins": {"enabled": True, "url": "https://api.github.com/repos/Xingkai98/asterwynd/branches/master/enforce_admins"},
    }


def _new_get() -> dict:
    """apply 后的实况：与目标状态一致。"""
    return {
        "url": "https://api.github.com/repos/Xingkai98/asterwynd/branches/master/protection",
        "required_status_checks": {
            "strict": True,
            "contexts": ["validate", "benchmark-gate"],
            "checks": [
                {"context": "validate", "app_id": 15368},
                {"context": "benchmark-gate", "app_id": 15368},
            ],
            "contexts_url": "https://api.github.com/repos/Xingkai98/asterwynd/branches/master/required_status_checks/contexts",
        },
        "required_pull_request_reviews": {
            "url": "https://api.github.com/repos/Xingkai98/asterwynd/branches/master/required_pull_request_reviews",
            "dismiss_stale_reviews": False,
            "require_code_owner_reviews": False,
            "required_approving_review_count": 0,
        },
        "required_conversation_resolution": {
            "enabled": True,
            "url": "https://api.github.com/repos/Xingkai98/asterwynd/branches/master/required_conversation_resolution",
        },
        "enforce_admins": {"enabled": True, "url": "https://api.github.com/repos/Xingkai98/asterwynd/branches/master/enforce_admins"},
    }


def _fake_run(
    get_obj: dict,
    *,
    put_capture: list | None = None,
    git_remote: str = "git@github.com:Xingkai98/asterwynd.git",
    git_code: int = 0,
    gh_code: int = 0,
    gh_stderr: str = "",
) -> mock.Mock:
    def fake(cmd, *args, **kwargs):
        if cmd[0] == "git":
            return _cp(git_code, git_remote or "", "")
        if cmd[0] == "gh":
            if "--method" in cmd:
                if put_capture is not None:
                    put_capture.append(json.loads(kwargs.get("input") or "{}"))
                return _cp(gh_code, "{}", gh_stderr)
            return _cp(gh_code, json.dumps(get_obj), gh_stderr)
        raise AssertionError(f"unexpected command: {cmd}")

    return mock.Mock(side_effect=fake)


def _run_cli(args: list[str], subprocess_mock: mock.Mock, capsys) -> int:
    with mock.patch.object(pg.subprocess, "run", subprocess_mock):
        code = pg.main(args)
    return code


def _load_real_target() -> dict:
    return pg.load_target(str(REAL_CONFIG))


# ── 2.1 payload 构造 ──────────────────────────────────────────────────


def test_apply_constructs_put_payload_with_all_required_fields(capsys):
    """--apply 构造的 payload 符合 GitHub PUT 形状：四必需字段 + restrictions:null、
    enabled 对象→布尔、剔除只读派生字段、reviews 保留 GET 可写子字段仅覆盖 count。"""
    put_capture: list[dict] = []
    fake = _fake_run(_old_get(), put_capture=put_capture)
    code = _run_cli(["--apply", "--repo", REPO], fake, capsys)

    assert code == 0
    assert len(put_capture) == 1
    payload = put_capture[0]

    # 四必需字段
    assert set(payload) == {
        "enforce_admins",
        "required_pull_request_reviews",
        "required_status_checks",
        "restrictions",
        "required_conversation_resolution",
    }
    # enabled 对象 → 布尔
    assert payload["enforce_admins"] is True
    assert payload["required_conversation_resolution"] is True
    # restrictions 显式 null
    assert payload["restrictions"] is None
    # required_status_checks：strict + contexts，无派生 checks/contexts_url
    assert payload["required_status_checks"] == {
        "strict": True,
        "contexts": ["validate", "benchmark-gate"],
    }
    # reviews：保留 GET 可写子字段，仅覆盖 count
    reviews = payload["required_pull_request_reviews"]
    assert reviews["required_approving_review_count"] == 0
    assert reviews["dismiss_stale_reviews"] is False
    assert reviews["require_code_owner_reviews"] is False
    assert "url" not in reviews
    # 无只读派生字段、无 _description
    assert not pg.contains_key(payload, "url")
    assert not pg.contains_key(payload, "checks")
    assert not pg.contains_key(payload, "contexts_url")
    assert not pg.contains_key(payload, "_description")
    # stdout 是合法 JSON，diff 走 stderr
    captured = capsys.readouterr()
    result = json.loads(captured.out)
    assert result["ok"] is True
    assert result["action"] == "apply"
    assert result["repo"] == REPO
    assert result["diff"]["required_status_checks.contexts"]["match"] is False
    assert "apply 预检" in captured.err and "存在漂移" in captured.err


def test_apply_idempotent_same_payload_twice(capsys):
    """幂等：目标状态已是当前状态时，两次 apply 构造同一 payload、无副作用。"""
    put_capture: list[dict] = []
    fake = _fake_run(_new_get(), put_capture=put_capture)
    code = _run_cli(["--apply", "--repo", REPO], fake, capsys)

    assert code == 0
    assert len(put_capture) == 1
    payload = put_capture[0]
    # 与目标一致时 pre-check diff 全部 match
    out = json.loads(capsys.readouterr().out)
    assert all(entry["match"] for entry in out["diff"].values())
    # 构造出的 payload == 目标状态（transform 后）
    assert payload["required_status_checks"]["contexts"] == ["validate", "benchmark-gate"]
    assert payload["required_conversation_resolution"] is True


def test_apply_idempotent_first_and_second_payload_equal():
    """幂等：GET 返回旧实况 vs 新实况构造的 PUT payload 相同。"""
    target = _load_real_target()
    payload_old = pg.build_put_payload(target, _old_get())
    payload_new = pg.build_put_payload(target, _new_get())
    assert payload_old == payload_new


def test_apply_strips_nested_description_from_put_body(tmp_path, capsys):
    """任意深度 `_description` 不进 PUT body（嵌套场景：顶层 + 两层嵌套）。"""
    config = tmp_path / "platform-gate.json"
    config.write_text(
        json.dumps(
            {
                "schema": "1.0",
                "_description": "顶层注释",
                "required_status_checks": {
                    "strict": True,
                    "contexts": ["validate", "benchmark-gate"],
                    "_description": "status checks 注释",
                },
                "required_conversation_resolution": {
                    "enabled": True,
                    "_description": "conversation 注释",
                },
                "required_pull_request_reviews": {
                    "required_approving_review_count": 0,
                    "nested": {"_description": "深层注释"},
                    "_description": "reviews 注释",
                },
                "enforce_admins": {"enabled": True},
            }
        ),
        encoding="utf-8",
    )
    put_capture: list[dict] = []
    fake = _fake_run(_old_get(), put_capture=put_capture)
    code = _run_cli(["--apply", "--repo", REPO, "--config", str(config)], fake, capsys)

    assert code == 0
    payload = put_capture[0]
    assert not pg.contains_key(payload, "_description")
    assert "nested" not in payload["required_pull_request_reviews"]  # 未声明字段不 merge


# ── 2.2 verify 比对 ───────────────────────────────────────────────────


def test_verify_consistent_exit_0(capsys):
    """mock GET 返回目标实况 → 白名单比对全部一致 → exit 0 + {"ok": true}。"""
    fake = _fake_run(_new_get())
    code = _run_cli(["--verify", "--repo", REPO], fake, capsys)

    assert code == 0
    out = capsys.readouterr().out
    result = json.loads(out)
    assert result["ok"] is True
    assert all(entry["match"] for entry in result["diff"].values())


def test_verify_drift_exit_1(capsys):
    """benchmark-gate 未进 required → 漂移 exit 1，diff 含 contexts 漂移。"""
    fake = _fake_run(_old_get())
    code = _run_cli(["--verify", "--repo", REPO], fake, capsys)

    assert code == 1
    captured = capsys.readouterr()
    result = json.loads(captured.out)
    assert result["ok"] is False
    assert result["diff"]["required_status_checks.contexts"]["match"] is False
    assert result["diff"]["required_conversation_resolution.enabled"]["match"] is False
    # 一致字段不受影响
    assert result["diff"]["required_status_checks.strict"]["match"] is True
    assert result["diff"]["enforce_admins.enabled"]["match"] is True
    assert "verify" in captured.err and "存在漂移" in captured.err


def test_verify_ignores_readonly_derived_fields(capsys):
    """GET 含 checks/url/contexts_url 等只读派生字段 → 白名单比对忽略，不误报漂移。"""
    get_obj = _new_get()
    get_obj["required_status_checks"]["checks"] = [
        {"context": "validate", "app_id": 15368},
        {"context": "benchmark-gate", "app_id": 15368},
    ]
    fake = _fake_run(get_obj)
    code = _run_cli(["--verify", "--repo", REPO], fake, capsys)
    assert code == 0


def test_verify_contexts_order_insensitive(capsys):
    """contexts 按排序集合比对（顺序无关）。"""
    get_obj = _new_get()
    get_obj["required_status_checks"]["contexts"] = ["benchmark-gate", "validate"]
    fake = _fake_run(get_obj)
    code = _run_cli(["--verify", "--repo", REPO], fake, capsys)
    assert code == 0


def test_verify_null_declared_field_is_drift_not_crash(capsys):
    """GET 声明字段 null/缺失 → 漂移 exit 1（不崩溃）。"""
    get_obj = _old_get()
    get_obj["required_pull_request_reviews"] = None
    get_obj["required_conversation_resolution"] = None
    fake = _fake_run(get_obj)
    code = _run_cli(["--verify", "--repo", REPO], fake, capsys)

    assert code == 1  # 漂移而非 exit 2 崩溃
    result = json.loads(capsys.readouterr().out)
    assert result["ok"] is False
    assert result["diff"]["required_pull_request_reviews.required_approving_review_count"]["match"] is False
    assert result["diff"]["required_conversation_resolution.enabled"]["match"] is False


def test_verify_missing_field_is_drift_not_crash(capsys):
    """GET 完全缺失某个声明字段（键不存在）→ 漂移 exit 1 不崩溃。"""
    get_obj = _old_get()
    del get_obj["required_status_checks"]
    fake = _fake_run(get_obj)
    code = _run_cli(["--verify", "--repo", REPO], fake, capsys)
    assert code == 1


# ── 2.3 错误处理 fail-closed ──────────────────────────────────────────


def test_error_gh_missing_exit_2(capsys):
    """gh CLI 不可用 → exit 2 fail-closed，不写。"""
    with mock.patch.object(pg.shutil, "which", return_value=None):
        code = pg.main(["--apply", "--repo", REPO])
    assert code == 2
    assert "gh CLI 不可用" in capsys.readouterr().err


def test_error_auth_failure_exit_2(capsys):
    """gh 认证失败 / API 非零退出 → exit 2 fail-closed。"""
    fake = _fake_run(_old_get(), gh_code=1, gh_stderr="Bad credentials")
    code = _run_cli(["--verify", "--repo", REPO], fake, capsys)
    assert code == 2
    assert "gh api GET 失败" in capsys.readouterr().err


def test_error_api_put_failure_exit_2(capsys):
    """PUT API 非零退出 → exit 2 fail-closed。"""
    fake = _fake_run(_old_get(), gh_code=1, gh_stderr="422: weren't supplied")
    code = _run_cli(["--apply", "--repo", REPO], fake, capsys)
    assert code == 2
    assert "gh api" in capsys.readouterr().err


def test_error_schema_invalid_exit_2(tmp_path, capsys):
    """目标 JSON schema 非法 → exit 2，不调用 gh。"""
    config = tmp_path / "bad.json"
    config.write_text(
        json.dumps({"required_status_checks": {"strict": "yes", "contexts": []}}),
        encoding="utf-8",
    )
    fake = _fake_run(_old_get())
    code = _run_cli(["--verify", "--repo", REPO, "--config", str(config)], fake, capsys)
    assert code == 2
    err = capsys.readouterr().err
    assert "schema 非法" in err
    fake.assert_not_called()  # 不执行任何 gh/git 调用


def test_error_git_remote_missing_exit_2(capsys):
    """git remote 缺失（无 --repo）→ exit 2。"""
    fake = _fake_run(_old_get(), git_code=1, git_remote="")
    code = _run_cli(["--verify"], fake, capsys)
    assert code == 2
    assert "git remote get-url origin 失败" in capsys.readouterr().err


def test_error_git_remote_non_github_format_exit_2(capsys):
    """git remote 非 GitHub 格式（无 --repo）→ exit 2。"""
    fake = _fake_run(_old_get(), git_remote="git@gitlab.com:foo/bar.git")
    code = _run_cli(["--verify"], fake, capsys)
    assert code == 2
    assert "GitHub" in capsys.readouterr().err


# ── 2.4 JSON schema 校验 ──────────────────────────────────────────────


def test_real_config_schema_valid():
    """checked-in scripts/platform-gate.json 满足脚本期望结构。"""
    target = _load_real_target()
    assert target["required_status_checks"]["strict"] is True
    assert target["required_status_checks"]["contexts"] == ["validate", "benchmark-gate"]
    assert target["required_conversation_resolution"]["enabled"] is True
    assert target["required_pull_request_reviews"]["required_approving_review_count"] == 0
    assert target["enforce_admins"]["enabled"] is True
    assert "_description" not in target  # 注释字段被剥离


def test_description_fields_do_not_affect_schema(tmp_path):
    """`_description` 注释字段不影响解析/校验（任意深度）。"""
    config = tmp_path / "with-desc.json"
    config.write_text(
        json.dumps(
            {
                "schema": "1.0",
                "_description": "顶层",
                "required_status_checks": {
                    "strict": True,
                    "contexts": ["validate", "benchmark-gate"],
                    "_description": "嵌套",
                },
                "required_conversation_resolution": {"enabled": True},
                "required_pull_request_reviews": {"required_approving_review_count": 0},
                "enforce_admins": {"enabled": True},
            }
        ),
        encoding="utf-8",
    )
    target = pg.load_target(str(config))
    assert target["required_status_checks"]["contexts"] == ["validate", "benchmark-gate"]


def test_schema_rejects_unknown_top_level_key(tmp_path):
    """未知顶层字段 → schema 非法。"""
    config = tmp_path / "bad-key.json"
    config.write_text(
        json.dumps(
            {
                "required_status_checks": {"strict": True, "contexts": ["validate"]},
                "required_conversation_resolution": {"enabled": True},
                "required_pull_request_reviews": {"required_approving_review_count": 0},
                "enforce_admins": {"enabled": True},
                "required_linear_history": True,  # 本 JSON 不声明保持现状字段
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(pg.PlatformGateError) as exc:
        pg.load_target(str(config))
    assert "未知顶层字段" in str(exc.value)


# ── D9 测试隔离 ───────────────────────────────────────────────────────


def test_repo_flag_shortcircuits_git(capsys):
    """提供 --repo 时完全不调用 git remote subprocess。"""
    calls: list[list[str]] = []
    real = _fake_run(_new_get(), git_remote="SHOULD_NOT_BE_READ")

    def recorder(cmd, *args, **kwargs):
        calls.append(cmd)
        return real(cmd, *args, **kwargs)

    with mock.patch.object(pg.subprocess, "run", mock.Mock(side_effect=recorder)):
        code = pg.main(["--verify", "--repo", REPO])
    assert code == 0
    assert not any(cmd[0] == "git" for cmd in calls)


def test_verify_stdout_is_json_only(capsys):
    """stdout 只输出 JSON；diff 与提示走 stderr。"""
    fake = _fake_run(_old_get())
    code = _run_cli(["--verify", "--repo", REPO], fake, capsys)
    captured = capsys.readouterr()
    json.loads(captured.out)  # stdout 必须是合法 JSON
    assert "platform-gate:" in captured.err  # stderr 有 diff 提示
