## MODIFIED Requirements

### Requirement: Read 工具支持图片文件

`Read` 工具 SHALL 根据文件扩展名（`.png`、`.jpg`、`.jpeg`、`.gif`、`.webp`）检测图片文件。检测到图片时 SHALL 读取文件字节、base64 编码、获取尺寸，并返回 `[TextBlock(描述文本), ImageBlock(base64 data URL, file_path=原始路径)]`。非图片文件 SHALL 保持现有 `str` 返回行为。

#### Scenario: 读取 PNG 图片

- **GIVEN** 路径指向一个有效的 PNG 文件
- **WHEN** agent 调用 Read 工具
- **THEN** `execute()` SHALL 返回 `[TextBlock("[image: file.png, 1024x768]"), ImageBlock(url="data:image/png;base64,...", file_path="/path/to/file.png")]`
- **AND** TextBlock 包含文件名和尺寸
- **AND** ImageBlock 包含 base64 data URL 和原始文件路径

#### Scenario: 读取代码文件保持不变

- **GIVEN** 路径指向一个 .py 文件
- **WHEN** agent 调用 Read 工具
- **THEN** `execute()` SHALL 返回 `str` 类型的文件内容
- **AND** 行为与改动前完全一致

#### Scenario: 超大图片

- **GIVEN** 图片文件超过 20MB
- **WHEN** agent 调用 Read 工具
- **THEN** `execute()` SHALL 返回错误字符串 `"[Error: 图片文件过大，超过 20MB 限制]"`
