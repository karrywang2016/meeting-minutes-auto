# meeting-minutes-auto · 会议纪要自动化技能

> WorkBuddy Custom Skill · Five Paths Cover All Meeting Scenarios
>
> WorkBuddy 自定义技能 · 五条路径覆盖所有会议场景
> 作者：流风@魔方泛化社区

---

## 目录 / Table of Contents

- [简介 / Overview](#简介--overview)
- [功能特性 / Features](#功能特性--features)
- [五条路径 / Five Paths](#五条路径--five-paths)
- [安装指南 / Installation](#安装指南--installation)
  - [方式一：直接复制 / Method 1: Copy to Skills Directory](#方式一直接复制--method-1-copy-to-skills-directory)
  - [方式二：通过 WorkBuddy 安装 / Method 2: Install via WorkBuddy](#方式二通过-workbuddy-安装--method-2-install-via-workbuddy)
  - [安装 Python 依赖 / Install Python Dependencies](#安装-python-依赖--install-python-dependencies)
- [前置条件 / Prerequisites](#前置条件--prerequisites)
- [使用方式 / Usage](#使用方式--usage)
- [配置说明 / Configuration](#配置说明--configuration)
- [目录结构 / Directory Structure](#目录结构--directory-structure)
- [技术栈 / Tech Stack](#技术栈--tech-stack)
- [更新日志 / Changelog](#更新日志--changelog)
- [许可证 / License](#许可证--license)

---

## 简介 / Overview

**中文**：

`meeting-minutes-auto` 是一个多平台会议纪要一站式自动化技能。自动识别会议平台（腾讯会议 / 飞书 / 钉钉），通过 WorkBuddy 连接器拉取原生 AI 纪要；支持本地音频/视频文件转写；支持本机实时录制（麦克风 / 系统音频）。所有路径统一格式化为 Markdown 后输出到腾讯文档。

**核心价值**：零代码、三平台统一、利用平台原生 AI 能力（质量优于自建 Whisper+DeepSeek）。

**English**:

`meeting-minutes-auto` is a multi-platform, all-in-one meeting minutes automation skill. It auto-detects the meeting platform (Tencent Meeting / Feishu / DingTalk), pulls native AI minutes via WorkBuddy connectors, supports local audio/video file transcription, and enables real-time local recording (microphone / system audio). All paths are uniformly formatted as Markdown and exported to Tencent Docs.

**Core Value**: Zero-code, unified across three platforms, leverages platform-native AI capabilities (better quality than self-built Whisper+DeepSeek).

---

## 功能特性 / Features

| 特性 / Feature | 说明 / Description |
|---|---|
| 🎯 五条路径覆盖 / Five Paths Coverage | 腾讯会议 / 飞书 / 钉钉 / 本地录制 / 本地音视频文件 |
| 🤖 平台原生 AI / Platform-native AI | 直接拉取平台自带 AI 智能纪要，质量更高 |
| 🎙️ 本机实时录制 / Real-time Recording | 支持麦克风（线下/电话）和系统音频（Zoom/Teams/网页会议） |
| 📁 本地文件转写 / Local File Transcription | 支持 mp4/mov/mkv/mp3/wav/m4a 等格式，视频自动提取音轨 |
| 🔔 录制监控与交互 / Recording Monitoring | 实时遥测 + AI 弹出【结束/继续/调整收音】按钮 |
| 📝 统一输出格式 / Unified Output | Markdown 模板化，含摘要/议题/待办/转写全文 |
| 📤 腾讯文档集成 / Tencent Docs Integration | 自动创建智能文档并归档到指定文件夹 |
| 💰 几乎零成本 / Near-zero Cost | Whisper 本地转写 + DeepSeek 约 ¥0.1/小时 |

---

## 五条路径 / Five Paths

| 路径 / Path | 场景 / Scenario | 触发方式 / Trigger | 依赖 / Dependencies |
|---|---|---|---|
| **A** 腾讯会议 / Tencent Meeting | 平台会议 / Platform meeting | "腾讯会议纪要" | tmeet 连接器 / connector |
| **B** 飞书 / Feishu | 平台会议 / Platform meeting | "飞书会议纪要" | feishu 连接器 / connector |
| **C** 钉钉 / DingTalk | 平台会议 / Platform meeting | "钉钉会议纪要" | dingtalk 连接器 / connector |
| **D** 本地音频/视频 / Local Audio-Video | 已有录音/录像 / Existing recording | "处理这个mp3/视频" | Python + Whisper（视频自动提取音轨 / auto extract audio） |
| **E** 本机实时录制 / Real-time Recording | 线下/电话/Zoom / Offline/Phone/Zoom | "本机录制/开始录制" | Python + sounddevice |

---

## 安装指南 / Installation

### 方式一：直接复制 / Method 1: Copy to Skills Directory

**中文**：

```bash
# 解压后将 meeting-minutes-auto 文件夹放到技能目录
# 用户级（跨项目，推荐）：
#   Windows: %USERPROFILE%\.workbuddy\skills\meeting-minutes-auto\
#   Mac/Linux: ~/.workbuddy/skills/meeting-minutes-auto/
#
# 项目级（仅当前项目）：
#   <项目根目录>/.workbuddy/skills/meeting-minutes-auto/
```

**English**:

```bash
# After extracting, place the meeting-minutes-auto folder into the skills directory
# User-level (cross-project, recommended):
#   Windows: %USERPROFILE%\.workbuddy\skills\meeting-minutes-auto\
#   Mac/Linux: ~/.workbuddy/skills/meeting-minutes-auto/
#
# Project-level (current project only):
#   <project-root>/.workbuddy/skills/meeting-minutes-auto/
```

---

### 方式二：通过 WorkBuddy 安装 / Method 2: Install via WorkBuddy

**中文**：将压缩包放入 WorkBuddy 技能导入入口，或通过技能管理界面导入。

**English**: Place the zip file into the WorkBuddy skill import entry, or import via the skill management interface.

---

### 安装 Python 依赖 / Install Python Dependencies

**中文**：

路径A/B/C（平台纪要拉取）**无需安装任何 Python 依赖**，开箱即用。

路径D（本地音频转写）和路径E（本机录制）需要 Python 环境 + Whisper + ffmpeg。一键安装：

**English**:

Paths A/B/C (platform minutes pulling) **require no Python dependencies**, ready to use out of the box.

Paths D (local audio transcription) and E (real-time recording) require Python environment + Whisper + ffmpeg. One-click install:

```bash
# 进入技能目录 / Enter the skills directory
cd ~/.workbuddy/skills/meeting-minutes-auto

# Windows（使用 WorkBuddy 托管 Python）
"C:/Users/<用户名>/.workbuddy/binaries/python/versions/3.13.12/python.exe" scripts/install.py

# Mac/Linux
python3 scripts/install.py
```

**安装脚本会自动完成 / The install script automatically**:

1. ✅ 检测/创建 Python 虚拟环境（优先复用 WorkBuddy 托管 venv）
2. ✅ 安装全部 pip 依赖（openai-whisper, torch, openai, sounddevice, soundfile 等）
3. ✅ 检测 ffmpeg，Windows 下自动下载到 `scripts/ffmpeg/`
4. ✅ 验证关键模块可正常导入
5. ✅ 生成 `scripts/env.json` 环境信息文件

**安装选项 / Install Options**：

```bash
python scripts/install.py --check      # 仅检测环境，不安装 / Check only, no install
python scripts/install.py --no-ffmpeg  # 跳过 ffmpeg 下载 / Skip ffmpeg download
python scripts/install.py --no-mirror  # 使用官方 PyPI（不走国内镜像）/ Use official PyPI
```

---

## 前置条件 / Prerequisites

### 连接器（路径A/B/C必需）/ Connectors (required for Paths A/B/C)

**中文**：在 WorkBuddy 左侧「连接器」管理页面启用并 OAuth 授权。

**English**: Enable and OAuth-authorize in the WorkBuddy left sidebar "Connectors" management page.

| 连接器 / Connector | 用途 / Purpose | 优先级 / Priority |
|---|---|---|
| tencent-docs | 输出纪要到腾讯文档 / Export minutes to Tencent Docs | 必需 / Required |
| tmeet (腾讯会议 / Tencent Meeting) | 拉取AI纪要/转写 / Pull AI minutes/transcription | 推荐 / Recommended |
| feishu (飞书 / Feishu) | 妙记转写/AI总结 + 本地音频上传 / Minutes transcription/AI summary + local audio upload | 推荐 / Recommended |
| dingtalk (钉钉 / DingTalk) | 听记摘要/转写/待办 / Listen summary/transcription/todos | 可选 / Optional |

### Python 环境（路径D/E必需）/ Python Environment (required for Paths D/E)

- Python 3.10+
- ffmpeg（Whisper 转写依赖，`install.py` 会自动下载配置）
- 一键安装：`python scripts/install.py`

### API Key（路径D/E必需）/ API Key (required for Paths D/E)

**中文**：

- **DeepSeek API Key（推荐）**：https://platform.deepseek.com/
- 或通义千问 API Key：https://dashscope.console.aliyun.com/

**English**:

- **DeepSeek API Key (recommended)**: https://platform.deepseek.com/
- Or Tongyi Qianwen API Key: https://dashscope.console.aliyun.com/

> 💡 **零成本方案 / Zero-cost option**: 即使不配置 API Key，路径D/E 也能以「零成本模式」运行（Whisper 本地转写 + AI 助手直接生成纪要），全程 ¥0。
>
> Even without an API Key, Paths D/E can run in "zero-cost mode" (Whisper local transcription + AI assistant generates minutes directly), completely free.

---

## 使用方式 / Usage

**中文**：在 WorkBuddy 对话中直接说：

**English**: Simply say in the WorkBuddy chat:

| 中文触发词 / Chinese Trigger | English Trigger |
|---|---|
| "帮我整理昨天腾讯会议的纪要" | "Help me organize yesterday's Tencent Meeting minutes" |
| "飞书站会纪要整理一下" | "Organize the Feishu standup meeting minutes" |
| "钉钉周会的会议纪要" | "The DingTalk weekly meeting minutes" |
| "这个音频文件帮我生成会议纪要" | "Generate minutes from this audio file" |
| "本机录制一段会议" | "Record a meeting locally" |
| "开始录一下会议" | "Start recording the meeting" |

### 路径E：本机录制命令示例 / Path E: Local Recording Command Examples

```bash
# 录麦克风 + 自动出纪要（面对面会议）
# Record microphone + auto-generate minutes (in-person meeting)
python scripts/record_meeting.py record --source mic --auto-process

# 录系统音频 + 自动出纪要（在线会议）
# Record system audio + auto-generate minutes (online meeting)
python scripts/record_meeting.py record --source system --auto-process

# 仅录制，稍后手动处理
# Record only, process manually later
python scripts/record_meeting.py record --output meeting.wav

# 定时录制（agent自动化调用，无需终端交互）
# Timed recording (agent automation, no terminal interaction)
python scripts/record_meeting.py record --source mic --duration 3600 --auto-process

# 标志文件停止（推荐 agent 使用，跨平台可靠）
# Flag-file stop (recommended for agent, cross-platform reliable)
python scripts/record_meeting.py record --source mic --duration 3600 --stop-flag recordings/stop.flag
# 停止时 / To stop: touch recordings/stop.flag → 脚本检测到后优雅保存WAV退出
```

### 路径D：本地文件转写命令示例 / Path D: Local File Transcription Command Examples

```bash
# 转写音频文件 + 生成纪要
# Transcribe audio file + generate minutes
python scripts/meeting_minutes.py --audio meeting.mp3 --stt whisper --llm deepseek

# 转写视频文件（自动提取音轨）
# Transcribe video file (auto-extract audio track)
python scripts/meeting_minutes.py --audio meeting.mp4 --stt whisper --llm deepseek

# 指定 Whisper 模型和语言
# Specify Whisper model and language
python scripts/meeting_minutes.py --audio meeting.wav --whisper-model medium --whisper-language zh
```

---

## 配置说明 / Configuration

### 修改输出目标 / Modify Output Target

**中文**：SKILL.md 中默认输出到腾讯文档「魔方泛化社区 > 课程编排」文件夹。如需修改，编辑 SKILL.md 中的 `target_folder_id` 和文件夹路径说明。

**English**: By default, SKILL.md exports to the Tencent Docs "魔方泛化社区 > 课程编排" folder. To modify, edit the `target_folder_id` and folder path description in SKILL.md.

### 配置 API Key / Configure API Key

```bash
# 方式一：环境变量（推荐）/ Method 1: Environment variable (recommended)
# Windows PowerShell
setx DEEPSEEK_API_KEY "sk-你的key"
# Mac/Linux
echo 'export DEEPSEEK_API_KEY="sk-你的key"' >> ~/.zshrc

# 方式二：配置文件 / Method 2: Config file
cp scripts/config.example.json scripts/config.json
# 编辑 config.json 填入真实 API Key / Edit config.json with your real API Key
```

---

## 目录结构 / Directory Structure

```
meeting-minutes-auto/
├── SKILL.md                      # 技能入口（平台路由+输出逻辑）/ Skill entry (platform routing + output logic)
├── README.md                     # 中文说明 / Chinese documentation
├── README_bilingual.md           # 中英双语说明 / Bilingual documentation (this file)
├── CHANGELOG.md                  # 变更日志 / Changelog
├── references/
│   ├── tmeet-flow.md             # 路径A: 腾讯会议拉取流程 / Path A: Tencent Meeting pull flow
│   ├── feishu-flow.md            # 路径B: 飞书拉取流程 / Path B: Feishu pull flow
│   ├── dingtalk-flow.md          # 路径C: 钉钉拉取流程 / Path C: DingTalk pull flow
│   ├── local-audio-flow.md       # 路径D: 本地文件处理流程 / Path D: Local file processing flow
│   ├── local-record-flow.md      # 路径E: 本机录制流程 / Path E: Local recording flow
│   └── output-template.md        # 统一输出模板 / Unified output template
└── scripts/
    ├── install.py                # 一键安装脚本 / One-click install script
    ├── record_meeting.py         # 本机录制脚本 / Local recording script
    ├── monitor_recording.py       # 录制监控辅助 / Recording monitor assistant
    ├── meeting_minutes.py        # 转写+总结脚本 / Transcription + summary script
    ├── requirements.txt          # Python依赖清单 / Python dependencies
    ├── config.example.json       # API Key配置模板 / API Key config template
    ├── env.json                  # 安装后自动生成 / Auto-generated after install
    ├── ffmpeg/                   # 自动下载的ffmpeg / Auto-downloaded ffmpeg
    └── venv/                     # 本地venv / Local venv
```

---

## 技术栈 / Tech Stack

| 组件 / Component | 技术 / Technology |
|---|---|
| 语音转文字 / Speech-to-Text | **faster-whisper**（CTranslate2，CPU int8，自带 VAD，中文更准，优先）/ priority; openai-whisper（回退 / fallback） |
| 结构化总结 / Structured Summary | DeepSeek-V3 / 通义千问 / LongCat-2.0 |
| 本机录制 / Local Recording | sounddevice + soundfile（WASAPI Loopback） |
| 录制监控 / Recording Monitoring | record_meeting.py 实时遥测 JSON + monitor_recording.py 供 AI 弹出按钮 |
| 输出 / Output | Markdown → 腾讯文档智能文档 / Tencent Docs smart document |

---

## 更新日志 / Changelog

### v1.1 · 2026-07-20

**中文**：

1. **录制过程可视化 + 交互按钮**：录制脚本实时写出遥测 JSON，当检测到发言后长时间静音（默认 90s）或全程无声音（默认 60s）时，agent 用 `AskUserQuestion` 弹出 **【结束会议】【继续录制】【调整收音】** 按钮。
2. **转写准确率大幅提升**：默认模型由 `base` 升级为 `small`；强制中文 `language=zh`；内置 VAD 静音切除；前置峰值归一化；总结 Prompt 增加自动校正同音错别字要求。

**English**:

1. **Recording Visualization + Interactive Buttons**: Recording script writes real-time telemetry JSON. When prolonged silence after speech (default 90s) or no sound at all (default 60s) is detected, the agent uses `AskUserQuestion` to pop up **【End Meeting】【Continue Recording】【Adjust Mic】** buttons.
2. **Transcription Accuracy Significantly Improved**: Default model upgraded from `base` to `small`; forced Chinese `language=zh`; built-in VAD silence removal; pre-peak normalization; summary prompt includes auto-correction of homophone typos.

### v1.0 · 2026-07-20

- 五条路径：腾讯会议 / 飞书 / 钉钉 平台原生纪要拉取 + 本地音频文件转写 + 本机实时录制
- 本地转写：Whisper + DeepSeek/通义千问/LongCat 结构化总结
- 统一输出到腾讯文档智能文档

---

## 许可证 / License

MIT License

Copyright (c) 2026 meeting-minutes-auto Contributors

---

<p align="center">
  <sub>Built with ❤️ · Powered by <a href="https://www.codebuddy.cn">WorkBuddy</a></sub>
</p>
