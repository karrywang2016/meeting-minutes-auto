# 钉钉纪要拉取流程 (dingtalk)

## 前置条件

- 已在 WorkBuddy 连接器管理页面启用「钉钉 (dingtalk)」
- 已完成 OAuth 授权（通过 WorkBuddy 连接器启用流程）
- 会议已在钉钉中开启「听记」（钉钉的会议录制+转写功能）

## 完整流程

### Step 1: 查询听记列表

```bash
dws minutes list mine --limit 10 --format json
```

**输出**：听记列表，含 `taskUuid`（听记任务ID）、标题、时间、状态。

**筛选参数**：
- `mine`：我创建的听记
- `shared`：分享给我的
- `all`：全部
- `--keyword "关键词"`：按标题筛选
- `--start/--end`：按时间筛选

### Step 2: 四维信息并行拉取

钉钉听记支持四个维度信息，可并行拉取：

#### 2a. AI 摘要

```bash
dws minutes get summary --id <taskUuid> --format json
```

**输出**：AI 生成的会议摘要，含主要讨论点、结论。

#### 2b. 转写全文

```bash
dws minutes get transcription --id <taskUuid> --format json
```

**输出**：完整转写文本，带发言人标注和时间戳。

#### 2c. 待办事项

```bash
dws minutes get todos --id <taskUuid> --format json
```

**输出**：AI 提取的待办/行动项，含负责人、截止时间。

#### 2d. 关键词

```bash
dws minutes get keywords --id <taskUuid> --format json
```

**输出**：会议核心关键词列表。

### Step 3: 发言人处理（可选）

#### 获取基础信息

```bash
dws minutes get info --id <taskUuid> --format json
```

**输出**：听记基础信息，含发言人列表。

#### 替换发言人标注

```bash
dws minutes speaker replace --id <taskUuid> --speaker-id <id> --name "张三"
```

**用途**：钉钉默认用"发言人1/2/3"标注，替换为真实姓名让纪要更易读。

#### 发言人声纹匹配（高级）

参考 `references/best_practices/11-minutes-speaker-correct.md`，用声纹识别自动匹配发言人身份。

### Step 4: 批量获取（可选）

```bash
dws minutes get batch --ids <uuid1,uuid2,uuid3> --format json
```

**用途**：一次拉取多个听记的摘要，适合批量整理。

---

## 数据映射到统一模板

| 钉钉输出 | 统一模板字段 |
|---------|-------------|
| 听记标题 + 时间 | 会议信息表 |
| get summary | AI 摘要 |
| get summary 讨论点 | 议题与结论 |
| get todos | 待办事项表 |
| get keywords | 关键关键词 |
| get transcription | 完整转写文本 |
| get info 发言人 | 会议信息表·参会人 |

## Recipe 速查

钉钉听记有5个预置 Recipe（参考 `references/best_practices/07-minutes.md`）：

| Recipe | 用途 |
|--------|------|
| `meeting-followup` | 会后跟进：提取待办 → 创建任务 → 通知 |
| `share-minutes` | 分享纪要：拉摘要 → 发消息 |
| `browse-minutes` | 浏览纪要：列表 + 详情 + 汇总 |
| `minutes-detail` | 纪要详情：四维信息并行拉取 |
| `minutes-speaker-summarize` | 发言人总结：声纹标注 → 身份推断 → 结构化输出 |

**本技能默认使用 `minutes-detail` Recipe**（四维并行拉取）。

## 常见问题

- **听记列表为空**：会议未开启听记功能，需在钉钉会议设置中开启
- **get summary 返回空**：听记仍在处理中，等待1-2分钟后重试
- **发言人全是"发言人1/2"**：用 `speaker replace` 手动替换，或用声纹匹配
- **权限不足**：确认钉钉账号有听记查看权限
