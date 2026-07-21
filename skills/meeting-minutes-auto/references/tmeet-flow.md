# 腾讯会议纪要拉取流程 (tmeet)

## 前置条件

- 已在 WorkBuddy 连接器管理页面启用「腾讯会议 (tmeet)」
- 已完成 OAuth 授权：`tmeet auth login`（浏览器授权）
- 会议已开启云录制

## 完整流程

### Step 1: 查询已结束会议

```bash
tmeet meeting list-ended --start 2026-07-13T00:00:00+08:00 --end 2026-07-20T23:59:59+08:00 --compact
```

**输出**：会议列表，包含 meeting_id、主题、开始/结束时间、参会人数。

**筛选技巧**：
- `--compact` 精简输出
- 按时间范围筛选（ISO 8601 格式，带时区）
- 从列表中找到目标会议的 `meeting_id`

### Step 2: 查询会议录制列表

```bash
tmeet record list --meeting-id <meeting_id> --compact
```

**输出**：录制列表，包含 `meeting_record_id`。

**注意**：如果列表为空，说明该会议未开启云录制，无法获取 AI 纪要。需提示用户下次开启录制。

### Step 3: 获取录制文件地址

```bash
tmeet record address --meeting-record-id <meeting_record_id>
```

**输出**：录制文件信息，包含 `record_file_id` 和下载地址。

### Step 4: 获取 AI 智能纪要（核心）

```bash
tmeet record smart-minutes --record-file-id <record_file_id>
```

**输出**：AI 智能纪要，支持中/英/日三种语言。包含：
- 会议摘要
- 讨论议题
- 关键结论
- 行动项

**这是最关键的一步**——腾讯会议的 AI 纪要质量很高，通常可直接使用。

### Step 5: 获取转写全文（可选，用于核对）

```bash
tmeet record transcript-get --record-file-id <record_file_id>
```

**输出**：完整转写文本，带时间戳和发言人标注。

**用途**：附在纪要末尾供人工核对；当 AI 纪要遗漏关键信息时可回溯原文。

### Step 6: 获取转写段落（可选）

```bash
tmeet record transcript-paragraphs --record-file-id <record_file_id>
```

**输出**：按段落切分的转写内容，适合精确定位某段发言。

### Step 7: 获取参会人列表（可选）

```bash
tmeet report participants --meeting-id <meeting_id>
```

**输出**：参会人列表，包含姓名、入会/离会时间、参会时长。

## 数据映射到统一模板

| tmeet 输出 | 统一模板字段 |
|-----------|-------------|
| 会议主题 + 时间 | 会议信息表 |
| smart-minutes 摘要 | AI 摘要 |
| smart-minutes 议题/结论 | 议题与结论 |
| smart-minutes 行动项 | 待办事项表 |
| transcript-get 全文 | 完整转写文本 |
| report participants | 会议信息表·参会人 |

## 常见问题

- **smart-minutes 返回空**：录制时长过短（<5分钟）可能不生成 AI 纪要，改用 transcript-get
- **权限不足**：确认授权账号是会议主持人或 Co-Host
- **会议ID无效**：确认使用的是 `meeting_id` 而非 `meeting_code`（9位数字）
