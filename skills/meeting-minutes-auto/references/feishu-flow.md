# 飞书纪要拉取流程 (feishu)

## 前置条件

- 已在 WorkBuddy 连接器管理页面启用「飞书 (feishu)」
- 已完成 OAuth 授权：`lark-cli auth login`（需要 vc、drive、minutes 多个 domain 权限）
- 会议已在飞书日历中创建，或妙记中已有记录

## 两条路径

飞书有两条获取纪要的路径，根据会议来源选择：

- **路径1：视频会议 (vc)** — 飞书开的会，从会议详情获取纪要 note
- **路径2：妙记 (minutes)** — 上传音视频生成转写，或搜索已有妙记

---

## 路径1：视频会议纪要

### Step 1: 搜索会议

```bash
lark-cli vc +search --start 2026-07-13 --end 2026-07-20 --format json --page-size 30
```

**输出**：会议列表，含 meeting_id、主题、时间、状态。

### Step 2: 获取会议详情

```bash
lark-cli vc +detail --meeting-ids <meeting_id>
```

**输出**：会议详情，含 `note_id`（纪要文档ID）。

**注意**：`note_display_type=unified` 表示是合并纪要，需用 `note +transcript` 单独拉转写。

### Step 3: 获取纪要内容

```bash
lark-cli note +detail --note-id <note_id>
```

**输出**：飞书云文档格式的纪要，含 AI 总结、待办、参会人。

---

## 路径2：妙记 (Minutes) — 推荐，功能最全

### 搜索已有妙记

```bash
lark-cli minutes +search --keyword "会议" --start 2026-07-13 --end 2026-07-20 --format json
```

**输出**：妙记列表，含 `minute_token`。

### 获取妙记详情（四维信息）

```bash
lark-cli minutes +detail --minute-tokens <minute_token> --summary --todo --transcript --chapter
```

**输出**（四维并行拉取）：
- `--summary`：AI 总结
- `--todo`：待办事项
- `--transcript`：逐字稿
- `--chapter`：章节分段

### 上传本地音视频生成妙记（处理本地音频文件）

```bash
# 1. 上传文件到云空间
lark-cli drive +upload --file /path/to/meeting.mp3

# 2. 用 file_token 生成妙记
lark-cli minutes +upload --file-token <file_token>

# 3. 等待转写完成（通常1-3分钟），再拉取详情
lark-cli minutes +detail --minute-tokens <new_minute_token> --summary --todo --transcript
```

**优势**：飞书妙记的转写质量高，且自动生成 AI 总结和待办，适合处理非飞书会议的录音。

### 下载妙记音视频（可选）

```bash
lark-cli minutes +download --minute-token <minute_token> --output ./audio/
```

### 替换发言人（可选）

```bash
lark-cli minutes +speaker-replace --minute-token <token> --speaker-id <id> --name "张三"
```

---

## 数据映射到统一模板

| 飞书输出 | 统一模板字段 |
|---------|-------------|
| 会议主题 + 时间 | 会议信息表 |
| minutes --summary | AI 摘要 |
| minutes --chapter | 议题与结论 |
| minutes --todo | 待办事项表 |
| minutes --transcript | 完整转写文本 |
| 参会人信息 | 会议信息表·参会人 |

## 常见问题

- **vc +detail 无 note_id**：会议未开启纪要录制，改用妙记上传音频
- **minutes +upload 长时间 pending**：大文件转写需5-10分钟，轮询状态
- **权限不足**：`lark-cli auth login --domain vc,drive,minutes` 重新授权对应 domain
- **note_display_type=unified**：合并纪要需用 `note +transcript --note-id <id>` 单独拉转写

## 会议纪要汇总工作流

飞书有专门的 `lark-workflow-meeting-summary` 技能，可汇总一段时间范围内的多个会议纪要：

```
时间范围 → vc +search → 会议列表 → vc +detail → note_id → note +detail → 纪要文档 → drive 元数据 → 结构化报告
```

适用于周报/月报场景，批量整理多场会议。
