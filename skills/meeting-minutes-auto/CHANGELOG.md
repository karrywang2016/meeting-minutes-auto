# 变更日志 (Changelog)

## v1.1 · 2026-07-20

> 针对真实使用反馈的两个痛点优化：① 录制过程没有提示/无法判断会议是否结束；② 音频转写文字不准确（含幻觉乱码）。

### 1. 录制过程提示 + 交互按钮（路径E）

**新增**
- `record_meeting.py` 新增遥测能力：
  - `--status-file <path>`：每 1 秒写出 JSON 遥测（`elapsed_sec` / `rms_db` / `peak_db` / `silence_sec` / `has_spoken` / `alert` / `alert_reason` / `output`），供 AI 轮询。
  - `--silence-guard <秒>`（默认 90）：检测到发言后连续静音达到该秒数 → 置 `alert=1`，原因「会议可能已结束」。
  - `--no-speech-guard <秒>`（默认 60）：全程未检测到任何声音达到该秒数 → 置 `alert=1`，原因「收音异常」。
  - 同时向 stdout 输出结构化一行 `REC_STATUS rms=.. peak=.. sil=.. spoken=Y/N alert=0|1 [REASON=..]`，便于解析。
  - **关键行为**：告警只置位、**不自动停止**，最终由用户/AI 决定（重新检测到发言后 `alert` 自动复位）。
- 新增 `monitor_recording.py` 辅助脚本：读取遥测 JSON，输出可被 AI 解析的状态行；支持 `--interval <秒>` 内置等待，让一次 Bash 调用即可完成「等待 + 读取」。
- `SKILL.md` / `references/local-record-flow.md` 新增「录制监控与交互按钮」章节：启动录制必须带遥测参数，AI 进入轮询循环，在 `alert=1` 时用 `AskUserQuestion` 弹出 **【结束会议（停止并生成纪要）】【继续录制】【调整收音/换设备】** 按钮。保留 `touch stop.flag` 与「用户说『停』」两条兜底停止路径。

### 2. 音频转写准确率优化（路径D/E 共用）

**`meeting_minutes.py`**
- `transcribe_with_whisper_local` 重写：
  - **优先 `faster-whisper`**（CTranslate2，CPU int8 推理更快，自带 VAD 滤静音，中文更准）；未安装时自动回退 `openai-whisper`。
  - 回退路径增加**预处理**：`_preprocess_audio`（峰值归一化到 -3dBFS，clip-safe，弥补 USB 等设备系统音量调不动的低电平）+ `_strip_silence`（基于能量的 VAD 静音切除，仅保留语音段）。
  - `--whisper-model` **默认值由 `base` 改为 `small`**（中文准确率显著提升；`medium`/`large-v3` 可追求极致）。
  - 新增 `--whisper-language`（默认 `zh` 强制中文）。
  - 强制 `language=zh`，并设抗幻觉阈值（`compression_ratio_threshold=2.4` / `logprob_threshold=-1.0` / `no_speech_threshold=0.6`）。
- `SUMMARY_PROMPT` 增加要求：转写文本由语音识别生成，可能存在同音错别字（如「路音」应为「录音」、「级录」应为「记录」），请结合上下文自动校正后再总结。

**`requirements.txt`**
- 新增 `faster-whisper>=1.0.0`（优先引擎，回退 openai-whisper 仍保留）。

### 3. 文档
- `README.md`：补充 `monitor_recording.py`、更新技术栈与「v1.1 更新亮点」。
- `SKILL.md` / `references/local-record-flow.md`：新增监控按钮章节与参数表。

### 修复
- 长静音导致的 Whisper 幻觉乱码（270 字无意义文本）根因已通过 VAD 静音切除 + 强制中文 + 峰值归一化解决。

---

## v1.0 · 2026-07-20

- 五条路径：腾讯会议(tmeet) / 飞书(feishu) / 钉钉(dingtalk) 平台原生纪要拉取 + 本地音频文件转写 + 本机实时录制。
- 本地转写：Whisper + DeepSeek/通义千问/LongCat 结构化总结。
- 统一输出到腾讯文档「魔方泛化社区 > 课程编排」智能文档。
