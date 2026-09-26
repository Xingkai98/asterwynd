## ADDED Requirements

### Requirement: SSE 可观测性区分协议控制帧与坏行

Agent runtime 的 SSE 解析 SHALL 区分「协议规定的非 JSON 控制帧」与「真正无法解析的数据行」，SHALL NOT 把前者报告为后者。

具体地，OpenAI 协议的流结束哨兵 `data: [DONE]` 按约定不是 JSON 对象，SHALL 在进入 JSON 解析**之前**被识别并跳过；runtime SHALL NOT 因该哨兵产生「解析失败 / 丢弃坏行」类告警。真实无法解析的数据行 SHALL 仍然产生告警（不得以消除误报为由关闭可观测性）。

依据（issue #251）：issue #249 为让静默丢行可观测而新增了解析失败告警，但未特判 `[DONE]`，导致每次 OpenAI 请求结束都刷一条误导性「Dropping unparseable SSE data line」告警——文案与事实不符（该行本就不产生事件、无数据被丢）。修复须同时保住两个性质：哨兵不告警、坏行仍告警。

#### Scenario: 流结束哨兵不产生解析失败告警

- **GIVEN** SSE 流中出现 `data: [DONE]` 结束哨兵
- **WHEN** runtime 解析该流
- **THEN** runtime SHALL NOT 因该行产生「解析失败 / 丢弃坏行」类告警
- **AND** runtime SHALL NOT 因该行产生任何事件（与哨兵出现前的行为一致）
- **AND** 该流其余可解析行 SHALL 照常产生事件

#### Scenario: 真实坏行仍然告警

- **GIVEN** SSE 流中出现无法解析为 JSON 的数据行（非协议控制帧）
- **WHEN** runtime 解析该流
- **THEN** runtime SHALL 为该行产生一条可观测的告警
- **AND** runtime SHALL 继续处理该流其余可解析行，SHALL NOT 因该行中断整个流

#### Scenario: 含哨兵字面量的合法 JSON 不被误判

- **GIVEN** SSE 流中某数据行是合法 JSON，且其内容恰好包含 `[DONE]` 字面量（如 `{"text":"[DONE]"}`）
- **WHEN** runtime 解析该流
- **THEN** runtime SHALL 按正常 JSON 解析该行
- **AND** runtime SHALL NOT 因该行包含该字面量而把它当作流结束哨兵跳过
