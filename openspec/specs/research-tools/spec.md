# research-tools 规格

## Purpose

定义当前联网研究工具。当前实现包含 WebSearch 和 WebFetch，均为 read-only 工具。

## Requirements

### Requirement: WebSearch 执行网页搜索

WebSearch SHALL 接收查询字符串和可选结果数量，向搜索端点发起请求并返回简化文本结果。

#### Scenario: 搜索无结果

- **GIVEN** 搜索请求执行成功但未提取到匹配结果
- **WHEN** WebSearch 返回
- **THEN** 工具 SHALL 返回“未找到结果”或等价提示

### Requirement: WebFetch 获取网页内容

WebFetch SHALL 接收 URL 和可选字符上限，获取网页正文并按上限截断。

#### Scenario: 内容超过 limit

- **GIVEN** 网页文本长度超过 limit
- **WHEN** WebFetch 返回内容
- **THEN** 工具 SHALL 返回前 limit 个字符
- **AND** 附加截断说明

### Requirement: research tools 只读

WebSearch 和 WebFetch SHALL 声明为 read-only，不得修改本地工作区。

#### Scenario: 联网请求失败

- **GIVEN** 网络请求抛出异常
- **WHEN** 工具捕获异常
- **THEN** 工具 SHALL 返回可读错误字符串
- **AND** 不修改本地文件

