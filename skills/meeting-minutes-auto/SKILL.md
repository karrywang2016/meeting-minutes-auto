---
name: meeting-minutes-auto
description: "会议纪要自动化技能：触发后先检查 tmeet/feishu/dingtalk 连接器连接状态与大模型 API Key，未连接/未设置时先给出连接器配置指引（在哪里配置）与 API Key 设置指引，再向用户展示 5 种生成方式（1.腾讯会议方式录制 2.飞书方式录制 3.钉钉方式录制 4.本地录制 5.录制的视频）供选择，再按选择路由。腾讯会议/飞书/钉钉拉取平台原生AI纪要，本地音频/视频文件转写处理，本机实时录制（麦克风/系统音频）现场录音后自动转写总结。统一格式化为Markdown输出到腾讯文档。当用户说'会议纪要/整理纪要/会议总结/生成纪要/meeting minutes/整理会议/本机录制/线下会议/开始录制/录一下会议'时触发。本机录制支持麦克风(面对面/电话)和系统音频(Zoom/Teams/网页会议)，录制视频支持 mp4/mov/mkv 等直接转写。"
agent_created: true
---

# 会议纪要自动化 (Meeting Minutes Auto)

## Overview

多平台会议纪要一站式技能。触发后**先检查 tmeet/feishu/dingtalk 连接器连接状态与大模型 API Key**，若有平台连接器未连接或未设置 API Key，则先给出连接器配置指引（在哪里配置）与 API Key 设置指引，并提示可用的本地替代方案，再让用户选择会议平台/方式（腾讯会议 / 飞书 / 钉钉 / 本地录制 / 录制的视频），按选择路由：平台方式通过 WorkBuddy 连接器拉取原生 AI 纪要、转写全文、待办事项；本地方式用本机录制或已有音视频文件转写，统一格式化为 Markdown 后输出到腾讯文档「魔方泛化社区 > 课程编排」文件夹。

**核心价值**：零代码、三平台统一、利用平台原生 AI 能力（质量优于自建 Whisper+DeepSeek）。

## 前置条件

### 连接器（路径A/B/C必需）

需要启用以下 WorkBuddy 连接器（在 WorkBuddy 左侧"连接器"管理页面启用并完成 OAuth 授权）：

| 连接器 | 用途 | 优先级 |
|--------|------|--------|
| tencent-docs | 输出纪要到腾讯文档 | 必需（已启用）|
| tmeet (腾讯会议) | 拉取录制/智能纪要/转写 | 推荐 |
| feishu (飞书) | 妙记转写/AI总结/待办 + 本地音频上传 | 推荐 |
| dingtalk (钉钉) | 听记摘要/转写/待办/发言人 | 可选 |

### Python 环境（路径D/E必需）

路径D（本地音频转写）和路径E（本机录制）需要 Python 3.10+ + ffmpeg + 一系列 pip 包。

**首次使用时自动安装**（推荐）：

当用户触发路径D或路径E时，agent 应先运行一键安装脚本：

```bash
# 使用 WorkBuddy 托管 Python 运行（推荐）
# Windows: "<WorkBuddy安装目录>/.workbuddy/binaries/python/versions/3.13.12/python.exe" scripts/install.py
# Mac/Linux
python3 scripts/install.py
```

安装脚本会自动完成：
1. 检测/创建 Python 虚拟环境
2. 安装全部 pip 依赖（openai-whisper, torch, openai, sounddevice 等）
3. 检测 ffmpeg，Windows 下自动下载到技能目录
4. 验证关键模块可正常导入
5. 生成 `scripts/env.json` 环境信息文件

**判断是否已安装**：检查 `scripts/env.json` 是否存在。存在则跳过安装，直接使用其中记录的 `venv_python` 路径运行脚本。

**手动安装/检测**：

```bash
# 仅检测环境状态
python scripts/install.py --check

# 重新安装依赖
python scripts/install.py

# 跳过 ffmpeg 下载（已有 ffmpeg 时）
python scripts/install.py --no-ffmpeg

# 使用官方 PyPI（不走国内镜像）
python scripts/install.py --no-mirror
```

### API Key（路径D/E必需）

路径D/E 使用 Whisper 本地转写 + DeepSeek/通义千问结构化总结。需要至少一个大模型 API Key：

```bash
# DeepSeek（推荐，新用户送500万Token）
# 获取: https://platform.deepseek.com/api_keys
# Windows PowerShell
setx DEEPSEEK_API_KEY "sk-你的key"
# Mac/Linux
echo 'export DEEPSEEK_API_KEY="sk-你的key"' >> ~/.zshrc

# 通义千问（可选）
# 获取: https://dashscope.console.aliyun.com/apiKey
```

> **注意**：如果未配置 API Key，agent 可以用 Whisper 完成本地转写后，直接由 AI 助手自身生成结构化纪要（不调用外部 LLM API），实现零成本方案。

## 触发交互流程（必须首先执行）

用户触发本技能后，**第一步先检查连接器连接状态与大模型 API Key，再决定是否/如何弹出选项菜单**，不要凭关键词猜测平台、也不要直接开始录音。

### 第 1 步：检查连接器状态

读取本次会话上下文中的 `connector-status`，判断以下三个**平台连接器**是否已连接（状态为 `connected`）：

- `tmeet`（腾讯会议）
- `feishu`（飞书）
- `dingtalk`（钉钉）

> 说明：上下文的 `connector-status` 由 WorkBuddy 注入，直接据此判断即可，不要向用户追问"你连了没有"。

### 第 2 步：检查大模型 API Key

本地转写（路径D/E）需要大模型 API Key 做结构化总结。运行以下命令检查是否已设置（三者任一非空即可）：

```bash
python3 -c "import os; k=os.environ.get('DEEPSEEK_API_KEY') or os.environ.get('DASHSCOPE_API_KEY') or os.environ.get('OPENAI_API_KEY'); print('API_KEY_OK' if k else 'API_KEY_MISSING')"
```

- 输出 `API_KEY_OK` → 已设置，可跳过本步。
- 输出 `API_KEY_MISSING` → 未设置，进入第 3 步先给出设置指引。

> 说明：平台原生方式（1/2/3）由会议平台自带 AI 生成纪要，**不依赖**此 Key；此 Key 仅用于 4️⃣/5️⃣ 本地方式的「Whisper 转写 + 大模型总结」。技能内置**零成本模式**（不配 Key 时由 AI 助手直接生成结构化纪要），但首次使用前仍建议先配置 Key 以获得更稳定的总结质量。

### 第 3 步：若有连接器未连接 或 API Key 未设置 → 先给出指引，暂不弹出选项菜单

只要存在以下任一情况，就**先向用户展示对应的【配置/设置指引】，此时不要弹出 5 选项菜单**：

- 有平台连接器状态为 `disconnected`
- 第 2 步命令输出为 `API_KEY_MISSING`

**【连接器配置指引】**（仅列出实际未连接的）：

```
⚠️ 检测到以下平台连接器尚未启用，请先配置后再使用对应的纪要方式：
- 腾讯会议（tmeet）：未连接
- 飞书（feishu）：未连接
- 钉钉（dingtalk）：未连接
（只列出实际未连接的连接器；已连接的无需提示）

📍 在哪里配置：
打开 WorkBuddy 左侧边栏的「连接器」（Connectors）入口，
在列表中找到对应的连接器卡片 → 点击「连接」/「启用」→ 按提示完成 OAuth 授权登录。
配置完成后，回到对话告诉我「会议纪要」即可继续。
```

**【大模型 API Key 设置指引】**（仅当 Key 缺失时）：

```
⚠️ 未检测到大模型 API Key（用于本地转写后的结构化总结）。请先设置好再使用 4️⃣/5️⃣ 本地方式：

推荐 DeepSeek（新用户送 500 万 Token）：
  • 获取地址：https://platform.deepseek.com/api_keys
  • Mac/Linux 终端：
      echo 'export DEEPSEEK_API_KEY="sk-你的key"' >> ~/.zshrc
      source ~/.zshrc
  • Windows PowerShell：
      setx DEEPSEEK_API_KEY "sk-你的key"

可选 通义千问（Qwen）：
  • 获取地址：https://dashscope.console.aliyun.com/apiKey
  • 设置：export DASHSCOPE_API_KEY="sk-你的key"

设置完成后，回到对话告诉我「会议纪要」即可继续。
💡 替代方案：即使不配置 Key，4️⃣/5️⃣ 也能以「零成本模式」运行（Whisper 本地转写 + AI 助手直接生成纪要），平台方式(1/2/3)本身不依赖此 Key。
```

**【无需连接器的替代方案】**（连接器未连接时一并提示）：

```
💡 即使平台连接器未连接，你也可以现在就直接使用：
  4️⃣ 本地录制（本机麦克风/系统音频，自动转写）
  5️⃣ 录制的视频（已有 mp4/mov/mkv/mp3/wav/m4a 文件，直接转写）
这两个方式不依赖任何平台连接器，可立即使用。
```

> 注意：第 3 步只给出「配置/设置指引 + 可用替代方案」，**不弹出选项菜单**；等用户配置好连接器与 API Key（或选择 4/5 零成本）后再进入第 4 步。

### 第 4 步：弹出 5 选项菜单（展示完指引后再给）

在展示完第 3 步的指引（若有）之后，再向用户展示以下 5 个选项并等待其选择：

> 请选择会议纪要用哪种方式生成？
> 1️⃣ 腾讯会议方式录制 —— 拉取腾讯会议云录制 + AI 智能纪要（需 tmeet 连接器已启用并授权）
> 2️⃣ 飞书方式录制 —— 拉取飞书妙记 / 视频会议 AI 纪要（需 feishu 连接器已启用并授权）
> 3️⃣ 钉钉方式录制 —— 拉取钉钉听记摘要 / 转写 / 待办（需 dingtalk 连接器已启用并授权）
> 4️⃣ 本地录制 —— 本机实时录制麦克风或系统音频，自动转写+总结（无需连接器；建议先设 API Key，或用零成本模式）
> 5️⃣ 录制的视频 —— 你已有会议视频/音频文件，我帮你转写+总结（支持 mp4/mov/mkv/mp3/wav/m4a；建议先设 API Key，或用零成本模式）
>
> 标注「需先配置连接器」的选项（1/2/3 中未连接者），请先完成上方第 3 步的配置后再选；标注「建议先设置 API Key」的 4/5，可在设置 Key 后获得更高质量，或直接以零成本模式运行。

路由：
- 选 1 → 路径A（详见 `references/tmeet-flow.md`）
- 选 2 → 路径B（详见 `references/feishu-flow.md`）
- 选 3 → 路径C（详见 `references/dingtalk-flow.md`）
- 选 4 → 路径E（详见 `references/local-record-flow.md`）
- 选 5 → 路径D 扩展（详见 `references/local-audio-flow.md`，已支持视频文件）

> 说明：若用户消息已明确指定某平台/方式（例如"整理昨天腾讯会议的纪要"），且对应连接器已连接，可在展示菜单的同时标注推荐项，仍由用户最终确认；若指定的连接器未连接或 API Key 缺失，则按第 3 步先给对应指引。其余情况一律按本流程先查状态、再给指引/菜单。

## 工作流决策树

```
用户选择后:
   ├─ 1. 腾讯会议(tmeet)   → 路径A: tmeet 连接器
   ├─ 2. 飞书(lark/feishu) → 路径B: feishu 连接器
   ├─ 3. 钉钉(dingtalk)    → 路径C: dingtalk 连接器
   ├─ 4. 本机录制          → 路径E: 本机实时录制
   ├─ 5. 视频/音频文件      → 路径D: 本地转写（支持视频）
   │
   ├─ 2. 拉取纪要（按平台执行，详见 references）
   │
   ├─ 3. 统一格式化（按 output-template.md 模板）
   │
   └─ 4. 输出到腾讯文档
       ├─ create_smartcanvas_by_mdx (content_format="markdown")
       └─ manage.move_file → 文件夹 ID: DkAAOfovZrtf
```

## 路径A：腾讯会议 (tmeet)

详见 `references/tmeet-flow.md`。核心步骤：

1. **查会议列表**：`tmeet meeting list-ended` 获取最近已结束会议
2. **查录制列表**：`tmeet record list --meeting-id <id>` 获取 meeting_record_id
3. **获取录制文件**：`tmeet record address --meeting-record-id <id>` 获取 record_file_id
4. **拉取 AI 智能纪要**：`tmeet record smart-minutes --record-file-id <id>`（支持中/英/日）
5. **拉取转写全文**：`tmeet record transcript-get --record-file-id <id>`
6. **拉取参会人**：`tmeet report participants --meeting-id <id>`

**优势**：腾讯会议自带 AI 智能纪要，质量高，直出可用。

## 路径B：飞书 (feishu)

详见 `references/feishu-flow.md`。核心步骤：

1. **搜索会议**：`lark-cli vc +search --start <日期> --end <日期>` 获取会议 ID
2. **会议详情**：`lark-cli vc +detail --meeting-ids <id>` 获取 note_id
3. **获取纪要**：`lark-cli note +detail --note-id <id>` 或妙记 `lark-cli minutes +detail`
4. **妙记四维信息**：`--summary --todo --transcript --chapter` 并行拉取

**优势**：妙记支持上传本地音视频生成转写；有专门的会议纪要汇总工作流 (`lark-workflow-meeting-summary`)。

## 路径C：钉钉 (dingtalk)

详见 `references/dingtalk-flow.md`。核心步骤：

1. **查听记列表**：`dws minutes list mine --limit 10` 获取 taskUuid
2. **拉取 AI 摘要**：`dws minutes get summary --id <taskUuid>`
3. **拉取转写**：`dws minutes get transcription --id <taskUuid>`
4. **拉取待办**：`dws minutes get todos --id <taskUuid>`
5. **拉取关键词**：`dws minutes get keywords --id <taskUuid>`
6. **发言人替换**：`dws minutes speaker replace`（可选）

**优势**：四维信息（摘要/关键词/待办/转写）可并行拉取；发言人声纹识别能力强。

## 路径D：本地音频/视频转写

详见 `references/local-audio-flow.md`。两种方案：

**方案1（优先）：飞书妙记上传**
- `lark-cli drive +upload` 上传音频到云空间
- `lark-cli minutes +upload` 生成妙记
- `lark-cli minutes +detail` 拉取转写和AI总结

**方案2（兜底）：Python 脚本**
- 运行 `scripts/meeting_minutes.py --audio <文件> --stt whisper --llm deepseek`
  - `<文件>` 支持音频（mp3/wav/m4a）**和视频（mp4/mov/mkv/avi/webm 等）**；视频会自动用 ffmpeg 抽取音轨后再转写
- Whisper 本地转写（免费）+ DeepSeek 结构化总结（约0.05-0.2元/次）
- **首次使用前必须运行**：`python scripts/install.py`（自动安装 Whisper + 全部依赖）
- 已安装标志：`scripts/env.json` 存在；运行脚本时使用 `env.json` 中的 `venv_python` 路径

> **零成本方案**：不配置 DeepSeek API Key 时，agent 可用 Whisper 完成转写后，直接由 AI 助手自身生成结构化纪要（无需外部 LLM），全程 ¥0。

## 路径E：本机实时录制

详见 `references/local-record-flow.md`。当会议不在任何已连接平台上时，直接用电脑录制。

**前置条件**：首次使用前必须运行 `python scripts/install.py`（自动安装 sounddevice + soundfile + whisper 全部依赖）。

**两种录制模式**：

| 模式 | 命令 | 适用场景 |
|------|------|----------|
| 麦克风录制 | `--source mic` | 线下会议、微信语音外放、面对面讨论 |
| 系统音频录制 | `--source system` | Zoom/Teams/网页会议（Windows WASAPI Loopback） |

**使用方式**：
```bash
# 录麦克风 + 自动出纪要（面对面会议）
python scripts/record_meeting.py record --source mic --auto-process

# 录系统音频 + 自动出纪要（在线会议）
python scripts/record_meeting.py record --source system --auto-process

# 仅录制，稍后手动处理
python scripts/record_meeting.py record --output meeting.wav

# 定时录制（agent自动化调用，无需终端交互）
python scripts/record_meeting.py record --source mic --duration 3600 --auto-process

# 标志文件停止（推荐 agent 使用，跨平台可靠）
python scripts/record_meeting.py record --source mic --duration 3600 --stop-flag recordings/stop.flag
# 停止时：touch recordings/stop.flag → 脚本检测到后优雅保存WAV退出
```

**三种停止模式**：
- **交互模式**（默认）：3秒倒计时 → 实时音量条 → 按回车停止 → 保存WAV
- **定时模式**（`--duration N`）：3秒倒计时 → 实时音量条 → N秒后自动停止 → 保存WAV
- **标志文件模式**（`--stop-flag PATH`，**推荐 agent 使用**）：录制中轮询标志文件，文件出现即优雅保存WAV退出

> ⚠️ **agent 自动化调用注意**：
> - **必须用 `--duration` 或 `--stop-flag`**，因为 `input()` 在非交互环境下会立即抛 EOFError 导致录制失败
> - **Windows 下不要用信号（SIGTERM/SIGINT）停止**：Windows 不支持向后台进程发 SIGINT，`psutil.terminate()` 等于强杀进程，**不会触发信号 handler，录制数据会丢失**。必须用 `--stop-flag` 标志文件方案。

**优势**：
- 覆盖所有非平台会议场景（线下/电话/Zoom/Teams）
- 麦克风模式跨平台，系统音频模式 Windows 原生支持
- 录制+转写+总结一条命令完成
- 几乎零成本（Whisper本地 + DeepSeek 约¥0.1/小时）

**降级关系**：路径E录制完成后生成的WAV文件，自动交给路径D的流程处理（`--auto-process` 自动完成）。

### 录制监控与交互按钮（v1.1 新增，强烈推荐 agent 使用）

路径E 录制是**后台长任务**，用户开会时不在对话里。为解决「不知道有没有在录 / 会议结束了不知道」的问题，录制脚本会实时写出**遥测 JSON** 并在静音/疑似结束时给出信号，agent 据此用 `AskUserQuestion` 向用户弹出 **【结束会议】【继续录制】【调整收音】** 按钮。

**启动录制时必须带遥测参数**：
```bash
DIR=recordings
OUT="$DIR/meeting_$(date +%Y%m%d_%H%M%S).wav"
echo "$OUT" > "$DIR/.current_output"
python scripts/record_meeting.py record \
  --source mic --output "$OUT" \
  --stop-flag "$DIR/stop.flag" \
  --status-file "$DIR/recording_status.json" \
  --silence-guard 90 --no-speech-guard 60
```

**agent 监控循环（启动录制后应立即进入）**：
1. 每隔约 15 秒，运行 `python scripts/monitor_recording.py --status-file recordings/recording_status.json --interval 15`，读取一行状态：
   `REC t=05:23 rms=-22.1dB peak=-9.3dB sil=12s spoken=Y alert=0`
2. 若输出出现 `>>> ALERT <原因>`（即 `alert=1`），**立刻调用 `AskUserQuestion`** 弹出按钮：
   - **结束会议（停止并生成纪要）** → 执行 `touch recordings/stop.flag`，等进程退出后走转写+总结+上传
   - **继续录制** → 什么也不做，回到第 1 步继续监控（重新检测到发言后 alert 会自动复位）
   - **调整收音/换设备** → 指导用户检查麦克风/外放，再回到第 1 步
3. 若 `alert=0` 且 `spoken=N`（全程没声音），持续监控，并提醒用户确认收音。

**告警触发条件（脚本内置，不自动停止，交用户/AI 决定）**：
- 已检测到发言后，连续静音 ≥ `--silence-guard`（默认 90 秒）→ 疑似「会议已结束」
- 全程始终未检测到任何声音，且已录制 ≥ `--no-speech-guard`（默认 60 秒）→ 「收音异常，请检查设备」

> ⚠️ **兜底**：除监控按钮外，仍保留 `touch recordings/stop.flag` 与「用户说『停/结束』→ agent 碰 stop.flag」两条停止路径。即使监控循环因超时退出，用户说「停」依然能优雅停录。


## 统一输出格式

纪要统一按 `references/output-template.md` 模板格式化，包含：

1. **会议信息表**：主题/时间/平台/参会人/时长
2. **AI 摘要**：平台原生 AI 生成的会议总结
3. **议题与结论**：分条列出讨论议题和对应结论
4. **待办事项表**：任务/负责人/截止时间/状态
5. **关键关键词**：会议核心关键词
6. **完整转写文本**：附在末尾供核对

## 输出到腾讯文档

格式化完成后，调用腾讯文档 MCP：

1. **创建智能文档**：
   - 工具：`create_smartcanvas_by_mdx`
   - 参数：`title="<会议主题>·会议纪要"`, `content_format="markdown"`, `mdx=<格式化后的Markdown>`
   - 注意：直接传入 Markdown 文本，**不要用 base64 编码**（长内容会解码失败）

2. **移动到目标文件夹**：
   - 工具：`manage.move_file`
   - 参数：`file_id=<新文档ID>`, `target_folder_id="DkAAOfovZrtf"`
   - 目标路径：魔方泛化社区 > 课程编排

3. **返回文档链接**给用户

## 翻车点与降级方案

| 翻车点 | 降级方案 |
|--------|---------|
| 会议无录制/无 AI 纪要 | 提示用户该会议未开启录制，建议下次开启云录制 |
| OAuth 过期/权限不足 | 提醒用户重新 `auth login`，标注哪个 domain 缺权限 |
| 钉钉听记为空 | 回退到手动上传音频或用 Python 脚本 |
| 飞书纪要 note_display_type=unified | 用 `note +transcript` 拉取转写 |
| 本地音频太大无法上传飞书 | 降级到 Python Whisper 脚本 |
| 腾讯文档写入失败 | 先输出 Markdown 到本地文件，手动粘贴 |
| 连接器未启用 | 引导用户去 WorkBuddy 连接器管理页面启用 |

## 资源文件

### scripts/
- `install.py` — **一键安装脚本**（首次使用路径D/E前必须运行，自动安装全部依赖）
- `meeting_minutes.py` — 本地音频转写+总结脚本（Whisper+DeepSeek/LongCat），路径D和路径E共用；**v1.1 起默认 `small` 模型 + 强制中文 + VAD 静音切除，转写准确率大幅提升**
- `record_meeting.py` — 本机实时录制脚本（麦克风/系统音频），路径E专用；**v1.1 起支持 `--status-file` 遥测 + `--silence-guard`/`--no-speech-guard` 静音/结束告警（交 AI 弹按钮，不自动停）**
- `monitor_recording.py` — **v1.1 新增**：录制监控辅助脚本，读取遥测 JSON 输出可被 AI 解析的状态行（配合 `AskUserQuestion` 弹【结束/继续/调整收音】按钮）
- `requirements.txt` — Python 依赖清单（含录制+转写全部依赖，install.py 会读取此文件）
- `config.example.json` — API Key 配置模板
- `env.json` — 安装后自动生成的环境信息文件（记录 venv 路径、ffmpeg 路径等，agent 据此判断是否已安装）

### references/
- `tmeet-flow.md` — 腾讯会议纪要拉取详细流程（路径A）
- `feishu-flow.md` — 飞书纪要拉取详细流程（路径B）
- `dingtalk-flow.md` — 钉钉纪要拉取详细流程（路径C）
- `local-audio-flow.md` — 本地音频文件处理流程（路径D）
- `local-record-flow.md` — 本机实时录制流程（路径E）
- `output-template.md` — 统一纪要 Markdown 输出模板

## 课程录制说明

本技能是「AI落地实战 · EP01 会议纪要自动化」的课程配套内容。录制建议：

- **对比叙事**：先展示 Python 方案（自建 Whisper+DeepSeek），再展示 WorkBuddy 方案（原生连接器），强调"零代码、平台原生AI、三平台统一"
- **演示动线**：Python demo(3min) → 本机录制(3min) → tmeet 拉取(3min) → 飞书妙记(3min) → 钉钉听记(2min) → 技能一键触发(2min) → 对比总结(2min)
- **观众可复现**：Python 方案人人可用；WorkBuddy 方案需安装 WorkBuddy 但门槛更低
