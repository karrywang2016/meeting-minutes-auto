# meeting-minutes-auto · 会议纪要自动化技能

> WorkBuddy 自定义技能 · 五条路径覆盖所有会议场景
> 作者：流风@魔方泛化社区

## 技能简介

多平台会议纪要一站式技能。自动识别会议平台（腾讯会议/飞书/钉钉），通过连接器拉取原生 AI 纪要；支持本地音频文件转写；支持本机实时录制（麦克风/系统音频）。统一格式化为 Markdown 输出。

## 安装方法

### 方式一：直接复制到技能目录

```bash
# 解压后将 meeting-minutes-auto 文件夹放到技能目录
# 用户级（跨项目，推荐）：
#   Windows: %USERPROFILE%\.workbuddy\skills\meeting-minutes-auto\
#   Mac/Linux: ~/.workbuddy/skills/meeting-minutes-auto/
#
# 项目级（仅当前项目）：
#   <项目根目录>/.workbuddy/skills/meeting-minutes-auto/
```

### 方式二：通过 WorkBuddy 安装

将压缩包放入 WorkBuddy 技能导入入口，或通过技能管理界面导入。

### 安装 Python 依赖（路径D/E必需）

路径A/B/C（平台纪要拉取）**无需安装任何 Python 依赖**，开箱即用。

路径D（本地音频转写）和路径E（本机录制）需要 Python 环境 + Whisper + ffmpeg。一键安装：

```bash
# 进入技能目录
cd ~/.workbuddy/skills/meeting-minutes-auto

# Windows（使用 WorkBuddy 托管 Python）
"C:/Users/<用户名>/.workbuddy/binaries/python/versions/3.13.12/python.exe" scripts/install.py

# Mac/Linux
python3 scripts/install.py
```

安装脚本会自动完成：
1. ✅ 检测/创建 Python 虚拟环境（优先复用 WorkBuddy 托管 venv）
2. ✅ 安装全部 pip 依赖（openai-whisper, torch, openai, sounddevice, soundfile 等）
3. ✅ 检测 ffmpeg，Windows 下自动下载到 `scripts/ffmpeg/`
4. ✅ 验证关键模块可正常导入
5. ✅ 生成 `scripts/env.json` 环境信息文件

安装选项：
```bash
python scripts/install.py --check      # 仅检测环境，不安装
python scripts/install.py --no-ffmpeg  # 跳过 ffmpeg 下载
python scripts/install.py --no-mirror  # 使用官方 PyPI（不走国内镜像）
```

## 目录结构

```
meeting-minutes-auto/
├── SKILL.md                      # 技能入口（平台路由+输出逻辑）
├── README.md                     # 本文件
├── references/
│   ├── tmeet-flow.md             # 路径A: 腾讯会议7步拉取流程
│   ├── feishu-flow.md            # 路径B: 飞书双路径(vc会议+妙记上传)
│   ├── dingtalk-flow.md          # 路径C: 钉钉四维并行拉取
│   ├── local-audio-flow.md       # 路径D: 本地音频文件降级流程
│   ├── local-record-flow.md      # 路径E: 本机实时录制流程
│   └── output-template.md        # 统一纪要Markdown输出模板
└── scripts/
    ├── install.py                # 一键安装脚本（自动安装全部依赖）
    ├── record_meeting.py         # 本机录制脚本(麦克风/系统音频) + 遥测/告警
    ├── monitor_recording.py       # v1.1 新增：录制监控辅助（供 AI 弹按钮）
    ├── meeting_minutes.py        # 转写+总结脚本(Whisper+DeepSeek/LongCat)
    ├── requirements.txt          # Python依赖清单（含传递依赖）
    ├── config.example.json       # API Key配置模板
    ├── env.json                  # 安装后自动生成（venv路径/ffmpeg路径）
    ├── ffmpeg/                   # 自动下载的ffmpeg（Windows）
    └── venv/                     # 本地venv（如未使用WorkBuddy托管venv）
```

## 五条路径

| 路径 | 场景 | 触发方式 | 依赖 |
|------|------|----------|------|
| A 腾讯会议 | 平台会议 | "腾讯会议纪要" | tmeet连接器 |
| B 飞书 | 平台会议 | "飞书会议纪要" | feishu连接器 |
| C 钉钉 | 平台会议 | "钉钉会议纪要" | dingtalk连接器 |
| D 本地音频/视频文件 | 已有录音/录像 | "处理这个mp3/视频" | Python+Whisper（视频自动提取音轨） |
| E 本机实时录制 | 线下/电话/Zoom | "本机录制/开始录制" | Python+sounddevice |

## 前置条件

### 连接器（路径A/B/C必需）

在 WorkBuddy 左侧「连接器」管理页面启用并 OAuth 授权：

| 连接器 | 用途 | 优先级 |
|--------|------|--------|
| tencent-docs | 输出纪要到腾讯文档 | 必需 |
| tmeet (腾讯会议) | 拉取AI纪要/转写 | 推荐 |
| feishu (飞书) | 妙记转写/AI总结 + 本地音频上传 | 推荐 |
| dingtalk (钉钉) | 听记摘要/转写/待办 | 可选 |

### Python环境（路径D/E必需）

- Python 3.10+
- ffmpeg（Whisper转写依赖，`install.py` 会自动下载配置）
- 一键安装：`python scripts/install.py`（自动创建venv + 安装全部pip依赖 + 下载ffmpeg）

### API Key（路径D/E必需）

- DeepSeek API Key（推荐）：https://platform.deepseek.com/
- 或通义千问 API Key：https://dashscope.console.aliyun.com/

## 配置说明

### 修改输出目标

SKILL.md 中默认输出到腾讯文档「魔方泛化社区 > 课程编排」文件夹。
如需修改，编辑 SKILL.md 中的 `target_folder_id` 和文件夹路径说明。

### 配置 API Key

```bash
# 方式一：环境变量（推荐）
# Windows PowerShell
setx DEEPSEEK_API_KEY "sk-你的key"
# Mac/Linux
echo 'export DEEPSEEK_API_KEY="sk-你的key"' >> ~/.zshrc

# 方式二：配置文件
cp scripts/config.example.json scripts/config.json
# 编辑 config.json 填入真实 API Key
```

## 使用方式

在 WorkBuddy 对话中直接说：

- "帮我整理昨天腾讯会议的纪要"
- "飞书站会纪要整理一下"
- "钉钉周会的会议纪要"
- "这个音频文件帮我生成会议纪要"
- "本机录制一段会议"

## 技术栈

- 语音转文字：**faster-whisper（CTranslate2，CPU int8，自带 VAD 滤静音，中文更准，优先）** / openai-whisper（回退，配合峰值归一化 + 能量 VAD 静音切除）/ 通义听悟（API）
- 结构化总结：DeepSeek-V3 / 通义千问 / LongCat-2.0
- 本机录制：sounddevice + soundfile（WASAPI Loopback）
- 录制监控：record_meeting.py 实时遥测 JSON + monitor_recording.py 供 AI 弹出【结束/继续/调整收音】按钮
- 输出：Markdown → 腾讯文档智能文档

## v1.1 更新亮点（2026-07-20）

针对实际使用的两个痛点做了优化：

1. **录制过程可视化 + 交互按钮**：录制脚本实时写出遥测 JSON（电平/静音时长/是否说过话/告警），当
   - 检测到发言后长时间静音（默认 90s）→ 疑似「会议已结束」
   - 全程无声音（默认 60s）→ 「收音异常」
   
   agent 据此用 `AskUserQuestion` 弹出 **【结束会议（停止并生成纪要）】【继续录制】【调整收音/换设备】** 按钮，不再需要猜会议有没有结束。脚本**只告警、不自动停**，最终由用户决定。
2. **转写准确率大幅提升**：
   - 默认模型由 `base` 升级为 `small`（中文准确率显著提高）；
   - 强制中文 `language=zh`；
   - **内置 VAD 静音切除**（faster-whisper 自带 / openai-whisper 回退时用能量 VAD），从根本上消除长静音导致的 Whisper 幻觉乱码（这是之前 270 字乱码的根因）；
   - 前置**峰值归一化**（弥补 USB 等设备系统音量调不动的低电平）；
   - 总结 Prompt 增加「自动校正同音错别字（如路音→录音、级录→记录）」要求。

## 版本

v1.1 · 2026-07-20（录制监控按钮 + 转写准确率优化）
v1.0 · 2026-07-20
