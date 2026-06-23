# research-tools 规格

## Purpose

定义当前联网研究工具。当前实现包含 WebSearch 和 WebFetch，均为 read-only 工具。

## Requirements

### Requirement: WebSearch 执行网页搜索

WebSearch SHALL 接收查询字符串和可选结果数量，通过当前搜索 provider 发起请求并返回稳定文本结果。当前默认 provider 为 DuckDuckGo HTML；完整 provider registry、多 provider fallback 和优先级由后续 change 定义。

#### Scenario: 搜索结果包含来源和字段

- **GIVEN** 搜索 provider 返回多个结果
- **WHEN** WebSearch 返回
- **THEN** 工具结果 SHALL 包含 provider 名称
- **AND** 每个结果 SHALL 包含序号、标题、URL 和摘要字段

#### Scenario: 搜索无结果

- **GIVEN** 搜索请求执行成功但未提取到匹配结果
- **WHEN** WebSearch 返回
- **THEN** 工具 SHALL 返回“未找到结果”或等价提示

#### Scenario: 搜索 provider 失败

- **GIVEN** provider 请求失败或响应无法解析
- **WHEN** WebSearch 捕获异常
- **THEN** 工具 SHALL 返回包含 provider 名称的可读错误字符串

### Requirement: WebFetch 获取网页内容

WebFetch SHALL 接收 URL 和可选字符上限，获取网页正文并按上限截断。返回内容 SHALL 包含 fetched URL、最终 URL、HTTP 状态、content type 和是否截断等诊断信息。

#### Scenario: 内容超过 limit

- **GIVEN** 网页文本长度超过 limit
- **WHEN** WebFetch 返回内容
- **THEN** 工具 SHALL 返回前 limit 个字符
- **AND** 附加截断说明

#### Scenario: 非成功 HTTP 状态

- **GIVEN** 服务端返回非 2xx 状态
- **WHEN** WebFetch 返回
- **THEN** 工具 SHALL 返回包含状态码、URL 和响应摘要的可读错误字符串

#### Scenario: 不支持的内容类型

- **GIVEN** 服务端返回非文本内容类型
- **WHEN** WebFetch 返回
- **THEN** 工具 SHALL 返回包含 content type 和 URL 的可读错误字符串

### Requirement: research tools 只读

WebSearch 和 WebFetch SHALL 声明为 read-only，不得修改本地工作区。

#### Scenario: 联网请求失败

- **GIVEN** 网络请求抛出异常
- **WHEN** 工具捕获异常
- **THEN** 工具 SHALL 返回可读错误字符串
- **AND** 不修改本地文件
