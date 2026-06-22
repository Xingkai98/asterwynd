## 1. 规格

- [ ] 1.1 新增 configuration 能力规格，定义 YAML、环境变量和 CLI 参数优先级。
- [ ] 1.2 修改 agent-modes 规格，定义 mode deny override 来自统一配置。
- [ ] 1.3 修改 workspace-safety / CLI / Web / benchmark 规格，定义配置接入边界。

## 2. 测试

- [ ] 2.1 新增配置 loader 缺省值和 YAML 读取测试。
- [ ] 2.2 新增环境变量覆盖 YAML 的测试。
- [ ] 2.3 新增 CLI 参数覆盖环境变量和 YAML 的测试。
- [ ] 2.4 新增 mode `deny_tools` 过滤 schema 和执行拒绝测试。
- [ ] 2.5 新增工具 ignore pattern / command denylist 从 YAML 生效测试。

## 3. 实现

- [ ] 3.1 增加 typed config model 和 loader。
- [ ] 3.2 增加 `myagent.example.yaml`，并确保个人 `myagent.yaml` 默认不提交。
- [ ] 3.3 将 CLI 构造路径接入统一配置对象。
- [ ] 3.4 将 Web session 构造路径接入统一配置对象。
- [ ] 3.5 将 benchmark runner 构造路径接入统一配置对象。
- [ ] 3.6 将 ModePolicy deny override 接入配置对象。
- [ ] 3.7 将 ignore patterns 和 command denylist 迁移到配置对象，保留环境变量覆盖。

## 4. 验证

- [ ] 4.1 运行配置、mode policy 和 workspace safety 测试。
- [ ] 4.2 运行 CLI/Web/benchmark 相关测试。
- [ ] 4.3 运行全量测试。
- [ ] 4.4 运行 OpenSpec strict validate 和项目 artifact checker。
