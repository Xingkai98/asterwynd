## 1. 规格

- [x] 1.1 新增 configuration 能力规格，定义 YAML、环境变量和 CLI 参数优先级。
- [x] 1.2 修改 agent-modes 规格，定义 mode deny override 来自统一配置。
- [x] 1.3 修改 workspace-safety / CLI / Web / benchmark 规格，定义配置接入边界。

## 2. 测试

- [x] 2.1 新增配置 loader 缺省值和 YAML 读取测试。
- [x] 2.2 新增环境变量覆盖 YAML 的测试，限定于 mode、benchmark 等仍支持环境变量的字段。
- [x] 2.3 新增 CLI 参数覆盖环境变量和 YAML 的测试。
- [x] 2.4 新增 mode `deny_tools` 过滤 schema 和执行拒绝测试。
- [x] 2.5 新增工具 ignore pattern / command denylist 从 YAML 生效测试，并移除旧工具策略环境变量测试。

## 3. 实现

- [x] 3.1 增加 typed config model 和 loader。
- [x] 3.1a 增加 `PyYAML` 运行依赖，loader 使用 `yaml.safe_load`。
- [x] 3.2 增加 `myagent.example.yaml`，并确保个人 `myagent.yaml` 默认不提交。
- [x] 3.3 将 CLI 构造路径接入统一配置对象。
- [x] 3.4 将 Web session 构造路径接入统一配置对象。
- [x] 3.5 将 benchmark runner 构造路径接入统一配置对象。
- [x] 3.6 将 ModePolicy deny override 接入配置对象。
- [x] 3.7 将 ignore patterns 和 command denylist 迁移到配置对象，不再支持旧工具策略环境变量。

## 4. 验证

- [x] 4.1 运行配置、mode policy 和 workspace safety 测试。
- [x] 4.2 运行 CLI/Web/benchmark 相关测试。
- [x] 4.3 运行全量测试。
- [x] 4.4 运行 OpenSpec strict validate 和项目 artifact checker。
- [x] 4.5 跑通至少一个 benchmark smoke。
