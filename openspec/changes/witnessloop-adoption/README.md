# witnessloop-adoption

把本仓的开发流程门禁分阶段切换到「接入 witnessloop」——本 change 是**第一阶段（影子接入）**：接入产物只跑不拦，用真实小需求验证后再单独一步真打开。

- 跟踪 issue：[#305](https://github.com/Xingkai98/asterwynd/issues/305)
- 上游工具仓：[`Xingkai98/witnessloop`](https://github.com/Xingkai98/witnessloop)（caller 钉 `@v1`）
- 阶段：**A 影子接入**（本 change）→ B 真实需求验证 → C 真打开（不在本 change 内）
- 状态：立项文档，未开始实现；**七条 Open Question 已于 2026-10-13 由用户停轮拍板、全部按推荐值裁定**（见 `design.md` 的 `## User Rulings`），待 tasks 0.4「设计阶段审阅闭环复跑确认」后开工
