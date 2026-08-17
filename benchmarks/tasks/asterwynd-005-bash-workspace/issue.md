# 阻止 mv/cp 将文件移出工作区边界

`agent/tools/command_guard.py` 的 `CommandGuard` 是沙箱命令守卫（默认放行 + denylist + argv 语义校验）。它的 `rm` 语义检查（`_check_rm`）已经拒绝 `-rf` 删除工作区外的路径（目标为绝对路径且不在工作区内时判定 `rm_target_escape`）；但 `mv`/`cp` 语义检查（`_check_mv_cp`）只拒绝目标写入受保护路径（`/etc`、`/proc`、`/sys` 等），**允许把工作区内文件移动到工作区外的任意绝对路径**——例如 `mv secret.txt /tmp/leak.txt` 或 `cp app.py /home/user/out.py`。这与 `_check_rm` 的工作区边界纪律不对称。

## Task

修复 `CommandGuard._check_mv_cp`：当守卫配置了工作区（构造参数 `workspace`）时，`mv`/`cp` 的目标若是绝对路径且不在工作区内，应判定为 `DENY`（`last_reason="mv_cp_dest"`）。相对路径目标在工作区内是构造上成立的，保持放行；未配置 `workspace` 时保持既有默认放行行为不变。

## Requirements

- `mv app.py /tmp/leak.py`、`cp app.py /home/user/out.py`（配置 workspace 时）→ DENY
- `mv app.py backup.py`、`mv app.py /repo/ws/backup.py`（配置 workspace 且目标在工作区内）→ ALLOW
- `CommandGuard()`（未配置 workspace）对 `mv app.py /tmp/leak.py` → ALLOW（向后兼容）
- 现有命令守卫测试不得回归
