## MODIFIED Requirements

### Requirement: Read 工具支持图片文件

`Read` 工具 SHALL 根据文件扩展名（`.png`、`.jpg`、`.jpeg`、`.gif`、`.webp`）检测图片文件。检测到图片时 SHALL 读取文件字节、base64 编码、并填充 `ToolResult.content_blocks` 为 `ImageBlock`。

#### Scenario: 读取 PNG 图片

- **GIVEN** 路径指向一个有效的 PNG 文件
- **WHEN** agent 调用 Read 工具
- **THEN** ToolResult SHALL 包含 `[ImageBlock(url="data:image/png;base64,...")]`
- **AND** ToolResult.output SHALL 包含描述性文本（文件名、尺寸）

#### Scenario: 读取代码文件保持不变

- **GIVEN** 路径指向一个 .py 文件
- **WHEN** agent 调用 Read 工具
- **THEN** ToolResult SHALL 仅包含文本 output
- **AND** content_blocks SHALL 为 None

#### Scenario: 超大图片

- **GIVEN** 图片文件超过 20MB
- **WHEN** agent 调用 Read 工具
- **THEN** Read SHALL 返回错误，提示图片过大
