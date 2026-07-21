# 本机实时录制流程 (路径E)

## 适用场景

当会议**不在**腾讯会议/飞书/钉钉平台上时，直接用电脑录制会议音频，录制完成后自动转写+总结。

| 场景 | 录制来源 | 说明 |
|------|----------|------|
| 线下面对面会议 | 麦克风 (`--source mic`) | 笔记本麦克风收录所有人发言 |
| 微信语音 / 电话会议 | 麦克风 (`--source mic`) | 外放声音会被麦克风收录 |
| Zoom / Teams / 网页会议 | 系统音频 (`--source system`) | 直接录电脑播放的声音，质量更好 |
| 临时讨论 / 头脑风暴 | 麦克风 (`--source mic`) | 快速录制，无需开任何会议软件 |
| 其他未连接平台的会议 | 麦克风或系统音频 | 灵活选择 |

## 前置条件

### 1. 一键安装（推荐）

首次使用前运行一键安装脚本，自动完成 Python venv 创建 + 全部依赖安装 + ffmpeg 配置：

```bash
# Windows（使用 WorkBuddy 托管 Python，推荐）
"C:/Users/<用户名>/.workbuddy/binaries/python/versions/3.13.12/python.exe" scripts/install.py

# Mac/Linux
python3 scripts/install.py
```

安装脚本会自动处理：
- ✅ Python 虚拟环境（优先复用 WorkBuddy 托管 venv）
- ✅ 全部 pip 依赖（sounddevice, soundfile, numpy, openai-whisper, torch 等）
- ✅ ffmpeg（Windows 自动下载到 `scripts/ffmpeg/`）
- ✅ 生成 `scripts/env.json` 环境信息文件

**判断是否已安装**：检查 `scripts/env.json` 是否存在。

### 2. Python 3.10+ 和 ffmpeg（手动安装）

如果不使用 install.py，需手动安装：

```bash
# ffmpeg 用于 Whisper 转写
# Windows: https://www.gyan.dev/ffmpeg/builds/ 下载并添加到 PATH
# Mac: brew install ffmpeg
# Linux: sudo apt install ffmpeg

# Python 依赖
cd <技能目录>/scripts
pip install -r requirements.txt
# 核心录制依赖: sounddevice, soundfile, numpy
# 转写总结依赖: openai, openai-whisper, torch
```

### 3. 配置 API Key（自动处理时需要）

```bash
# DeepSeek API Key（推荐，新用户送500万Token）
export DEEPSEEK_API_KEY="sk-你的key"
# 或 Windows PowerShell: setx DEEPSEEK_API_KEY "sk-你的key"
```

## 录制模式详解

### 模式1：麦克风录制 (`--source mic`)

录制电脑麦克风输入，适用于所有需要收录现场声音的场景。

```bash
python record_meeting.py record --source mic --auto-process
```

**特点**：
- 跨平台支持（Windows/Mac/Linux）
- 笔记本自带麦克风即可使用
- 外放的声音（微信语音、电话）也会被麦克风收录
- 远离噪音源，音质更好

**优化建议**：
- 用领夹麦克风（¥50-200）可大幅提升收音质量
- 录制时关闭其他应用的通知提示音
- 笔记本放在会议桌中央，尽量等距所有人

### 模式2：系统音频录制 (`--source system`)

直接录制电脑正在播放的音频，适用于在线会议（Zoom/Teams/网页会议）。

```bash
python record_meeting.py record --source system --auto-process
```

**特点**：
- Windows 使用 WASAPI Loopback 技术，直录系统音频，无环境噪音
- 录制的是电脑输出的声音，质量等于你听到的声音
- 不会录到麦克风输入（你的发言不会被录到）

**平台支持**：
| 平台 | 支持情况 | 说明 |
|------|----------|------|
| Windows | ✅ 原生支持 | WASAPI Loopback，零配置 |
| Mac | ⚠️ 需配置 | 安装 BlackHole 虚拟音频设备后用 `--device` 指定 |
| Linux | ⚠️ 需配置 | 使用 PulseAudio monitor source |

**Mac/Linux 替代方案**：
如果系统音频录制不可用，直接用 `--source mic` 录制麦克风——电脑外放的声音也会被麦克风收到，虽然质量稍差但完全可用。

### 模式3：指定设备录制 (`--device <索引>`)

```bash
# 先查看可用设备
python record_meeting.py --list-devices

# 用指定设备录制
python record_meeting.py record --device 3 --auto-process
```

适用于：有多个麦克风/音频接口，需要指定特定设备的场景。

## 完整使用流程

### 标准流程（录制+自动出纪要）

```bash
# 一步到位：录制 → 停止 → 自动转写 → 自动总结 → 生成Markdown纪要
python record_meeting.py record --source mic --auto-process --llm deepseek
```

**定时模式（agent 自动化调用必用）**：

```bash
# 定时录制3600秒（1小时），到时间自动停止，无需终端交互
python record_meeting.py record --source mic --duration 3600 --auto-process
```

**标志文件模式（推荐 agent 使用，跨平台可靠停止）**：

```bash
# 启动录制（带标志文件停止机制）
python record_meeting.py record --source mic --duration 3600 --stop-flag recordings/stop.flag

# 停止录制：创建标志文件，脚本检测到后优雅保存WAV退出
touch recordings/stop.flag
```

> ⚠️ **agent 调用必须用 `--duration` 或 `--stop-flag`**：
> - `input()` 在 subprocess/管道下会立即抛 `EOFError` 导致录制瞬间停止
> - **Windows 下不要用 SIGTERM/SIGINT 信号停止**：Windows 不支持向后台进程发 SIGINT，`psutil.terminate()` 是强杀进程，不触发信号 handler，**录制数据全部丢失**。必须用 `--stop-flag` 标志文件方案。

**交互过程**：
```
  录音设备: 麦克风 (Realtek Audio)
  录音来源: 🎤 麦克风
  采样率: 44100Hz | 声道: 1

  ⏳ 准备录制... 3
  ▶ 录制中！按 [回车] 停止

  ⏱ 05:23 │████████████░░░░░░░░░░░░│ 🔊正常

  ⏹ 录制结束 | 总时长: 05:23

  💾 已保存: recordings/会议_20260720_153000.wav
     时长: 323.0s | 大小: 5672.3KB | 格式: WAV

  🔄 自动转写 + 结构化总结中...
  ✅ 会议纪要生成完成！
```

### 分步流程（先录制，后处理）

```bash
# 第1步：仅录制
python record_meeting.py record --output my_meeting.wav

# 第2步：手动转写+总结（可调整参数）
python meeting_minutes.py --audio my_meeting.wav --stt whisper --llm deepseek
```

适用于：录制时不想等待处理，或需要调整转写/总结参数的场景。

### 演示模式（课程录制用）

```bash
python record_meeting.py --demo
```

不实际录制，只展示功能和使用方法。适合课程录制时先给观众看界面预览。

## 录制监控与交互按钮（v1.1 新增）

路径E 录制是后台长任务，开会时用户不在对话里。v1.1 起录制脚本会实时写出**遥测 JSON** 并在静音/疑似结束时给信号，agent 据此用 `AskUserQuestion` 弹出 **【结束会议】【继续录制】【调整收音】** 按钮。

### 启动录制（带遥测）

```bash
DIR=recordings
OUT="$DIR/meeting_$(date +%Y%m%d_%H%M%S).wav"
echo "$OUT" > "$DIR/.current_output"
python record_meeting.py record \
  --source mic --output "$OUT" \
  --stop-flag "$DIR/stop.flag" \
  --status-file "$DIR/recording_status.json" \
  --silence-guard 90 --no-speech-guard 60
```

### agent 监控循环（启动录制后立刻进入）

1. 每约 15 秒运行：`python monitor_recording.py --status-file recordings/recording_status.json --interval 15`
   输出示例：`REC t=05:23 rms=-22.1dB peak=-9.3dB sil=12s spoken=Y alert=0`
2. 若见到 `>>> ALERT <原因>`（即 `alert=1`），**立即调用 `AskUserQuestion`** 弹按钮：
   - **结束会议（停止并生成纪要）** → `touch recordings/stop.flag`，等进程退出后转写+总结+上传
   - **继续录制** → 不做任何事，回到第 1 步继续监控（重新检测到发言后 alert 自动复位）
   - **调整收音/换设备** → 指导用户检查麦克风/外放，再回到第 1 步
3. 若 `alert=0` 但 `spoken=N`（全程没声音），持续监控并提醒用户确认收音。

> ⚠️ 兜底：除监控按钮外，仍保留 `touch recordings/stop.flag` 与「用户说『停/结束』→ agent 碰 stop.flag」两条停止路径。即使监控循环超时退出，用户说「停」依然能优雅停录。

## 录制参数调优

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `--sample-rate` | 44100 | 采样率，系统音频会自动适配设备默认值 |
| `--channels` | 1 | 声道数（1=单声道省空间，2=立体声，系统音频自动为2） |
| `--stt` | whisper | 语音转文字引擎（whisper=本地免费，dashscope=通义听悟） |
| `--llm` | deepseek | 大模型引擎（deepseek=便宜，qwen=通义千问，longcat=美团） |
| `--status-file` | 无 | **v1.1 遥测 JSON 路径**：每 1s 写 elapsed/rms/silence_sec/has_spoken/alert，供 AI 轮询检测静音与会议结束 |
| `--silence-guard` | 90 | 有发言后连续静音达此秒数 → 「会议可能已结束」告警（不自动停，交 AI 弹按钮） |
| `--no-speech-guard` | 60 | 全程未检测到任何声音达此秒数 → 「收音异常」告警 |
| `--whisper-model` | **small** | Whisper 模型：tiny/base/small/medium/large-v3（**v1.1 默认 small**，比 base 准确率高很多） |
| `--whisper-language` | zh | 强制转写语言（默认中文；设 auto 自动检测） |

**建议**：
- 日常会议：单声道 + `--whisper-model small`（v1.1 默认，准确率与速度平衡最佳）
- 高质量需求：单声道 + `--whisper-model medium` 或 `large-v3`
- 极致准确：用 `--stt dashscope` 调通义听悟API（收费但准确率更高）
- **转写准确率关键（v1.1）**：脚本已内置「峰值归一化 + VAD 静音切除 + 强制中文」，从根本上消除长静音导致的 Whisper 幻觉（乱码）；优先使用自动启用的 `faster-whisper` 引擎（CPU int8 更快、自带 VAD 滤静音）

## 费用估算

| 录制时长 | Whisper本地转写 | DeepSeek总结 | 合计 |
|----------|----------------|-------------|------|
| 15分钟 | ¥0 | ¥0.03 | **¥0.03** |
| 30分钟 | ¥0 | ¥0.05 | **¥0.05** |
| 1小时 | ¥0 | ¥0.1 | **¥0.1** |
| 2小时 | ¥0 | ¥0.2 | **¥0.2** |

> 本机录制 + Whisper + DeepSeek 是最省钱的方案，几乎零成本。

## 翻车点与解决方案

### 1. 录制没声音 / 音量条一直是静音

**原因**：麦克风未连接、被静音、或设备选错。

**解决**：
```bash
# 查看可用设备
python record_meeting.py --list-devices
# 用 --device 指定正确的设备
python record_meeting.py record --device <正确索引> --auto-process
```

### 2. 系统音频录制报错（非 Windows）

**原因**：Mac/Linux 不支持 WASAPI Loopback。

**解决**：
- Mac：安装 [BlackHole](https://existential.audio/blackhole/) 虚拟音频设备，用 `--device` 指定
- Linux：用 PulseAudio monitor source
- **最简单**：改用 `--source mic`，麦克风也能录到外放声音

### 3. 录制的文件是空的 / 只有噪音

**原因**：设备被其他应用占用，或采样率不匹配。

**解决**：
- 关闭其他正在使用麦克风的软件（微信、QQ、会议软件）
- 不要手动指定 `--sample-rate`，让脚本自动适配设备默认值

### 4. Whisper 转写很慢

**原因**：首次使用需下载模型；无 GPU 时 CPU 推理慢。

**解决**：
- 首次运行会自动下载模型（base 约74MB），之后从缓存加载
- 用更小的模型：在 `meeting_minutes.py` 中设置 `--whisper-model tiny`
- 长会议（>1小时）建议分段录制处理

### 5. 录制时不知道有没有在录

**解决**：观察音量条——说话时应该有跳动。如果一直是静音标记 🔇，说明没收到声音，按回车停止后检查设备。

## 与其他路径的关系

```
会议纪要自动化决策树
  ├─ 路径A: 腾讯会议 (平台已有录制+AI纪要)
  ├─ 路径B: 飞书 (平台已有录制+AI纪要)
  ├─ 路径C: 钉钉 (平台已有录制+AI纪要)
  ├─ 路径D: 本地音频文件 (已有录音文件，处理它)
  └─ 路径E: 本机实时录制 (没有录音，现场录一个) ← 本文档
```

**路径D vs 路径E**：
- 路径D：用户**已经有**音频文件（手机录的、别人发的），只需转写+总结
- 路径E：用户**还没有**录音，需要现场用电脑录制

路径E录制完成后，生成的 WAV 文件可以直接交给路径D的流程处理（`--auto-process` 自动完成这一步）。
