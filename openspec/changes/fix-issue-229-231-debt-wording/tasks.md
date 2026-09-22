# Tasks — fix-issue-229-231-debt-wording

## 实现

- [x] 改写 `docs/known-debt.md` #229 条目（机械加固不可行 + 三条路径实测排除 + 黑盒复现表）
- [x] 复核并改写 #231 条目（`..` 现被锚点兜底拦下，非专门规则）
- [x] 配 `protected_artifact_explained` 事件（受保护路径）

## 验证

- [x] spec delta：`specs/change-documentation/spec.md`（ADDED「机械门禁的信任边界」）

- [x] `check_openspec_artifacts.py --base-ref <base> --require-base` 通过
- [x] OpenSpec strict validate 通过
- [ ] 收尾：关闭 issue #229 与 #231（记录即处置）
