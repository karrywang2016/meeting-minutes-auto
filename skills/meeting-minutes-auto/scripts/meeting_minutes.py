#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
会议纪要自动化 CLI 工具
======================
EP01 · AI落地实战课程配套脚本

功能：
  1. 音频转文字（支持本地 Whisper / 通义听悟 API / 直接传入文本）
  2. 大模型结构化总结（议题 → 结论 → 待办 → 负责人）
  3. 输出 Markdown 格式会议纪要
  4. 费用统计（Token 消耗 + 人民币估算）

用法：
  # Demo 模式（无需音频和API，用内置示例文本演示）
  python meeting_minutes.py --demo

  # 本地 Whisper 转写 + DeepSeek 总结
  python meeting_minutes.py --audio meeting.mp3 --stt whisper --llm deepseek

  # 通义听悟 API 转写 + 通义千问总结
  python meeting_minutes.py --audio meeting.mp3 --stt dashscope --llm qwen

  # 直接传入文字稿
  python meeting_minutes.py --transcript transcript.txt --llm deepseek

依赖：
  pip install openai dashscope openai-whisper
"""

import argparse
import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path

# 转写预处理依赖（峰值归一化 / 能量 VAD 静音切除）
try:
    import numpy as np
except ImportError:
    np = None
try:
    import soundfile as sf
except ImportError:
    sf = None

# ============================================================
# 环境引导：自动读取 env.json，配置 ffmpeg 路径
# ============================================================

def _bootstrap_env():
    """读取 install.py 生成的 env.json，自动配置 ffmpeg PATH"""
    env_file = Path(__file__).parent / "env.json"
    if env_file.exists():
        try:
            with open(env_file, "r", encoding="utf-8") as f:
                env_info = json.load(f)
            ffmpeg_path = env_info.get("ffmpeg_path")
            if ffmpeg_path and os.path.exists(ffmpeg_path):
                ffmpeg_dir = os.path.dirname(ffmpeg_path)
                # 将 ffmpeg 目录加入 PATH（Whisper 内部通过 subprocess 调用 ffmpeg）
                if ffmpeg_dir not in os.environ.get("PATH", ""):
                    os.environ["PATH"] = ffmpeg_dir + os.pathsep + os.environ.get("PATH", "")
        except Exception:
            pass  # env.json 读取失败不影响主流程

_bootstrap_env()


# ============================================================
# 第一部分：语音转文字
# ============================================================

# 视频扩展名（需先抽取音轨再转写）
VIDEO_EXTS = {".mp4", ".mov", ".mkv", ".avi", ".webm", ".flv", ".m4v", ".wmv", ".ts"}


def _ffmpeg_bin():
    """从 env.json 读取 ffmpeg 路径，找不到则回退到 PATH 中的 ffmpeg。"""
    env_file = Path(__file__).parent / "env.json"
    if env_file.exists():
        try:
            with open(env_file, "r", encoding="utf-8") as f:
                p = json.load(f).get("ffmpeg_path")
                if p and os.path.exists(p):
                    return p
        except Exception:
            pass
    return "ffmpeg"


def _ensure_audio(path: str) -> str:
    """
    若传入的是视频文件，用 ffmpeg 抽取单声道 16k 音轨为临时 WAV 再返回路径；
    音频文件则原样返回。这样 Whisper 只需处理音频，兼容 mp4/mov/mkv 等。
    """
    ext = os.path.splitext(path)[1].lower()
    if ext not in VIDEO_EXTS:
        return path
    import tempfile
    import subprocess
    tmp_wav = tempfile.mktemp(suffix=".wav")
    cmd = [_ffmpeg_bin(), "-y", "-i", path, "-vn", "-ac", "1", "-ar", "16000", tmp_wav]
    print(f"🎞️  检测到视频文件，正在用 ffmpeg 提取音轨: {path}")
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        print(f"❌ ffmpeg 提取音频失败: {proc.stderr[:300]}")
        sys.exit(1)
    print(f"✅ 已提取音频: {tmp_wav}")
    return tmp_wav


# ============================================================
# 转写预处理：峰值归一化 + 能量 VAD 静音切除（依赖-free）
# 这是转写准确率提升的关键：长静音是 Whisper 幻觉（编造内容）的主因
# ============================================================

def _resample_linear(data: "np.ndarray", sr_in: int, sr_out: int) -> "np.ndarray":
    """简单线性重采样（语音 STT 足够用）。"""
    if sr_in == sr_out or np is None:
        return data
    n_out = int(round(len(data) * sr_out / sr_in))
    if n_out <= 1:
        return data
    idx = np.linspace(0, len(data) - 1, n_out)
    return np.interp(idx, np.arange(len(data)), data).astype(np.float32)


def _strip_silence(data: "np.ndarray", sr: int, top_db: float = 35.0,
                    min_speech_ms: int = 300, min_sil_ms: int = 500) -> "np.ndarray":
    """基于能量的 VAD：切除低于 (peak - top_db) 的静音段，仅保留语音。

    静音是 Whisper 幻觉（编造内容）的主要来源，切除后准确率显著提升。
    """
    if np is None or len(data) == 0:
        return data
    peak = float(np.max(np.abs(data))) or 1e-9
    peak_db = 20 * np.log10(peak)
    thr = 10 ** ((peak_db - top_db) / 20.0)  # 线性阈值

    frame = max(1, int(0.02 * sr))  # 20ms 帧
    n = len(data)
    n_frames = (n + frame - 1) // frame
    energy = np.array([
        float(np.sqrt(np.mean(data[i * frame:(i + 1) * frame] ** 2)))
        for i in range(n_frames)
    ])
    speech_mask = energy >= thr

    min_speech = max(1, int(min_speech_ms / 1000.0 * sr / frame))
    min_sil = max(1, int(min_sil_ms / 1000.0 * sr / frame))

    # 合并被短静音隔开的语音段
    segments = []
    i = 0
    while i < n_frames:
        if speech_mask[i]:
            j = i
            while j < n_frames and (speech_mask[j] or
                  (j + 1 < n_frames and speech_mask[j + 1])):
                j += 1
            if j - i >= min_speech:
                segments.append((i, j))
            i = j
        else:
            i += 1

    if not segments:
        return data  # 没切到任何语音，原样返回交由模型判断
    chunks = [data[s * frame:(e + 1) * frame] for s, e in segments]
    return np.concatenate(chunks)


def _preprocess_audio(path: str, norm_target_db: float = -3.0,
                      max_gain_db: float = 15.0):
    """读取音频 → 单声道 float32 → 重采样 16k → 峰值归一化(clip-safe) → 可选降噪。
    返回 (data_16k_float32, sr=16000)。
    """
    if np is None or sf is None:
        # 极端回退：直接返回路径，交给 whisper 自身处理
        return _ensure_audio(path), 16000
    audio_for_stt = _ensure_audio(path)  # 视频先抽音轨为 16k 单声道 wav
    data, sr = sf.read(audio_for_stt, dtype="float32", always_2d=False)
    if data.ndim > 1:
        data = data.mean(axis=1)
    data = _resample_linear(data, int(sr), 16000)
    sr = 16000

    # 峰值归一化到 -3dBFS（上限 +15dB 防止噪声爆音）
    peak = float(np.max(np.abs(data))) or 1e-9
    peak_db = 20 * np.log10(peak)
    gain = 10 ** ((norm_target_db - peak_db) / 20.0) if peak_db < norm_target_db else 1.0
    gain = min(gain, 10 ** (max_gain_db / 20.0))
    data = np.clip(data * gain, -1.0, 1.0)

    # 可选降噪（noisereduce 已安装时生效）
    try:
        import noisereduce as nr
        data = nr.reduce_noise(y=data, sr=sr, stationary=False, prop_decrease=0.75)
    except Exception:
        pass
    return data, sr


def _transcribe_faster_whisper(audio_data, model_size: str, language: str):
    """优先用 faster-whisper（CTranslate2，自带 VAD 滤静音、中文更准）。

    设备选择策略：
      1. 检测到 NVIDIA GPU → device='cuda', compute_type='float16'（速度最快）
      2. 无 GPU → device='cpu'，依次尝试 int8 → float32 → int8_float32
    某些 Windows 环境下 CTranslate2 的 CPU MKL 后端可能报 mkl_malloc 错误，
    有 GPU 时自动使用 CUDA 绕过此问题。
    """
    import os as _os
    # 预设 MKL/OpenMP 线程限制，提高 Windows CPU 兼容性
    _os.environ.setdefault("OMP_NUM_THREADS", "4")
    _os.environ.setdefault("MKL_NUM_THREADS", "4")
    _os.environ.setdefault("MKL_SERVICE_FORCE_INTEL", "1")

    from faster_whisper import WhisperModel
    from faster_whisper.vad import VadOptions
    import ctranslate2

    # 设备选择：优先 CUDA（GPU），回退 CPU
    cuda_count = ctranslate2.get_cuda_device_count()
    last_err = None

    if cuda_count > 0:
        # 有 NVIDIA GPU → 使用 CUDA
        device_configs = [("cuda", "float16"), ("cuda", "int8_float16")]
        print(f"🖥️ 检测到 NVIDIA GPU（{cuda_count}个），使用 CUDA 加速转写")
    else:
        # 无 GPU → 尝试 CPU 不同 compute_type
        device_configs = [("cpu", "int8"), ("cpu", "float32"), ("cpu", "int8_float32")]

    for dev, ct in device_configs:
        try:
            model = WhisperModel(model_size, device=dev, compute_type=ct)
            print(f"✅ 模型加载成功: device={dev}, compute_type={ct}")
            break
        except (RuntimeError, Exception) as e:
            last_err = e
            print(f"⚠️ faster-whisper device={dev} compute_type={ct} 失败: {e}")
    else:
        raise RuntimeError(f"所有设备/compute_type 均失败，最后错误: {last_err}")

    segments, info = model.transcribe(
        audio_data,
        language=language,
        beam_size=5,
        temperature=0.0,
        vad_filter=True,
        vad_parameters=VadOptions(
            threshold=0.5, min_speech_duration_ms=250,
            max_speech_duration_s=30, min_silence_duration_ms=1000,
        ),
    )
    parts = []
    segs = []
    for s in segments:
        parts.append(s.text)
        segs.append({"start": round(s.start, 2), "end": round(s.end, 2), "text": s.text})
    return "".join(parts).strip(), segs, getattr(info, "language", language)


def transcribe_with_whisper_local(audio_path: str, model_size: str = "small",
                                  language: str = "zh") -> dict:
    """
    本地 Whisper 转写（免费、离线、隐私好）。
    优化点（v1.1）：
      • 优先 faster-whisper（自带 VAD 滤静音、中文更准、CPU 更快）；
      • 回退 openai-whisper 时，先做「峰值归一化 + 能量 VAD 静音切除」预处理，
        从根本上消除长静音导致的幻觉（这是转写准确率差的主因）；
      • 强制中文 language=zh，并设抗幻觉阈值（compression_ratio / logprob / no_speech）。
    默认模型 small（比 base 准确率高很多；追求极致可用 medium/large-v3）。
    """
    print(f"🎙️  正在加载 Whisper 模型（{model_size}，语言={language}）...")
    start_time = time.time()
    audio_for_stt = _ensure_audio(audio_path)

    # —— 优先 faster-whisper ——
    try:
        data, sr = _preprocess_audio(audio_for_stt)
        text, segs, lang = _transcribe_faster_whisper(data, model_size, language)
        elapsed = time.time() - start_time
        print(f"✅ 转写完成！耗时 {elapsed:.1f}s，生成 {len(segs)} 个段落（faster-whisper）")
        print(f"   文本长度: {len(text)} 字符")
        return {
            "text": text,
            "segments": segs,
            "elapsed": elapsed,
            "method": f"faster-whisper-{model_size}",
            "cost": 0.0,
        }
    except ImportError:
        pass  # 没装 faster-whisper，回退 openai-whisper
    except Exception as e:
        print(f"⚠️ faster-whisper 转写异常，回退 openai-whisper：{e}")

    # —— 回退 openai-whisper ——
    try:
        import whisper
    except ImportError:
        print("❌ 本地转写引擎均不可用：")
        print("   • faster-whisper（CTranslate2）加载失败")
        print("   • openai-whisper 未安装或 torch 不可用")
        print("")
        print("💡 替代方案：")
        print("   1. 重新安装依赖：python scripts/install.py")
        print("   2. 使用平台原生方式（腾讯会议/飞书/钉钉）—— 不需要本地转写")
        print("   3. 使用飞书妙记上传音频 —— 不需要本地转写")
        print("   4. 如有 NVIDIA GPU，确保 CUDA 驱动已安装以启用 GPU 加速")
        sys.exit(1)

    data, sr = _preprocess_audio(audio_for_stt)
    # 能量 VAD 切除静音（双保险，进一步抑制幻觉）
    cleaned = _strip_silence(data, sr)
    model = whisper.load_model(model_size)
    print(f"📁 正在转写音频: {audio_path}")
    result = model.transcribe(
        cleaned,
        language=language,
        verbose=False,
        temperature=0.0,
        beam_size=5,
        condition_on_previous_text=True,
        compression_ratio_threshold=2.4,
        logprob_threshold=-1.0,
        no_speech_threshold=0.6,
    )
    elapsed = time.time() - start_time
    transcript = result["text"].strip()
    segments = result.get("segments", [])

    print(f"✅ 转写完成！耗时 {elapsed:.1f}s，生成 {len(segments)} 个段落（openai-whisper）")
    print(f"   文本长度: {len(transcript)} 字符")

    return {
        "text": transcript,
        "segments": segments,
        "elapsed": elapsed,
        "method": f"whisper-{model_size}",
        "cost": 0.0,  # 本地模型免费
    }


def transcribe_with_dashscope(audio_path: str, api_key: str) -> dict:
    """
    使用通义听悟（阿里云 Paraformer）API 转写音频
    优点：准确率高、支持标点、速度快
    缺点：需要API Key、按音频时长收费
    """
    try:
        import dashscope
    except ImportError:
        print("❌ 未安装 dashscope，请运行: pip install dashscope")
        sys.exit(1)

    if not api_key:
        api_key = os.environ.get("DASHSCOPE_API_KEY", "")
    if not api_key:
        print("❌ 未设置 DASHSCOPE_API_KEY")
        print("   获取地址: https://dashscope.console.aliyun.com/apiKey")
        sys.exit(1)

    dashscope.api_key = api_key

    # 读取音频文件并转Base64
    import base64
    with open(audio_path, "rb") as f:
        audio_b64 = base64.b64encode(f.read()).decode()

    print("🎙️  正在调用通义听悟 API 转写音频...")
    start_time = time.time()

    from dashscope.audio.asr import Transcription

    # 使用 Paraformer 模型
    task = Transcription.async_transcribe(
        model="paraformer-v2",
        file_urls=[audio_path],  # 实际使用需上传到OSS获取URL
        language_hints=["zh", "en"],
    )

    # 轮询任务状态
    result = Transcription.wait(task.output.task_id)
    elapsed = time.time() - start_time

    transcript = ""
    if result.status_code == 200:
        for t in result.output.get("results", []):
            transcript += t.get("text", "")

    print(f"✅ 转写完成！耗时 {elapsed:.1f}s")
    print(f"   文本长度: {len(transcript)} 字符")

    # 通义听悟定价：约 0.1-0.3 元/小时音频
    audio_duration_hours = elapsed / 3600  # 粗略估算
    cost = max(0.1, audio_duration_hours * 1.4)  # 最低0.1元

    return {
        "text": transcript,
        "segments": [],
        "elapsed": elapsed,
        "method": "dashscope-paraformer-v2",
        "cost": cost,
    }


def load_transcript_from_file(transcript_path: str) -> dict:
    """直接从文本文件加载会议文字稿"""
    print(f"📄 正在读取文字稿: {transcript_path}")
    with open(transcript_path, "r", encoding="utf-8") as f:
        text = f.read().strip()

    print(f"✅ 读取完成！文本长度: {len(text)} 字符")

    return {
        "text": text,
        "segments": [],
        "elapsed": 0.0,
        "method": "file-input",
        "cost": 0.0,
    }


# ============================================================
# 第二部分：大模型结构化总结
# ============================================================

SUMMARY_PROMPT = """你是一个专业的会议纪要助手。请根据以下会议录音转写文本，生成结构化的会议纪要。

要求：
1. 提取会议的核心议题（2-5个）
2. 每个议题下列出：讨论要点、达成结论
3. 识别所有待办事项（Action Items），包含：任务内容、负责人、截止时间（如提到）
4. 记录会议基本信息（时间、参会人如能识别）
5. 转写文本由语音识别(Whisper)生成，可能存在同音错别字（如"路音"应为"录音"、"级录"应为"记录"），请结合上下文自动校正后再总结，不要保留明显错误的同音字
6. 输出格式为 Markdown

请按以下模板输出：

## 会议信息
- **主题**：（从内容推断）
- **时间**：（如能识别）
- **参会人**：（如能识别）

## 议题与结论

### 议题一：XXX
**讨论要点**：
- ...
**结论**：
- ...

### 议题二：XXX
**讨论要点**：
- ...
**结论**：
- ...

## 待办事项
| 序号 | 任务内容 | 负责人 | 截止时间 |
|------|----------|--------|----------|
| 1 | ... | ... | ... |

## 其他备注
- ...

---

会议录音转写文本：
{transcript}
"""


def summarize_with_deepseek(transcript: str, api_key: str) -> dict:
    """
    使用 DeepSeek-V3 生成结构化会议纪要
    优点：便宜（约0.1元/次）、中文能力强
    """
    try:
        from openai import OpenAI
    except ImportError:
        print("❌ 未安装 openai，请运行: pip install openai")
        sys.exit(1)

    if not api_key:
        api_key = os.environ.get("DEEPSEEK_API_KEY", "")
    if not api_key:
        print("❌ 未设置 DEEPSEEK_API_KEY")
        print("   获取地址: https://platform.deepseek.com/api_keys")
        sys.exit(1)

    client = OpenAI(api_key=api_key, base_url="https://api.deepseek.com")

    prompt = SUMMARY_PROMPT.format(transcript=transcript)

    print("🤖 正在调用 DeepSeek-V3 生成会议纪要...")
    start_time = time.time()

    response = client.chat.completions.create(
        model="deepseek-chat",
        messages=[
            {"role": "system", "content": "你是专业的会议纪要助手，擅长从口语化的转写文本中提取结构化信息。"},
            {"role": "user", "content": prompt},
        ],
        temperature=0.3,  # 低温度保证稳定性
        max_tokens=4096,
    )

    elapsed = time.time() - start_time
    content = response.choices[0].message.content
    usage = response.usage

    # DeepSeek 定价：输入 0.5元/百万token，输出 8元/百万token（缓存命中更便宜）
    input_cost = (usage.prompt_tokens / 1_000_000) * 0.5
    output_cost = (usage.completion_tokens / 1_000_000) * 8.0
    total_cost = input_cost + output_cost

    print(f"✅ 纪要生成完成！耗时 {elapsed:.1f}s")
    print(f"   Token 用量 - 输入: {usage.prompt_tokens}, 输出: {usage.completion_tokens}")
    print(f"   费用: ¥{total_cost:.4f}")

    return {
        "content": content,
        "elapsed": elapsed,
        "method": "deepseek-chat",
        "prompt_tokens": usage.prompt_tokens,
        "completion_tokens": usage.completion_tokens,
        "cost": total_cost,
    }


def summarize_with_qwen(transcript: str, api_key: str) -> dict:
    """
    使用通义千问（Qwen-Max）生成结构化会议纪要
    优点：阿里云生态、中文优化
    """
    try:
        from openai import OpenAI
    except ImportError:
        print("❌ 未安装 openai，请运行: pip install openai")
        sys.exit(1)

    if not api_key:
        api_key = os.environ.get("DASHSCOPE_API_KEY", "")
    if not api_key:
        print("❌ 未设置 DASHSCOPE_API_KEY")
        print("   获取地址: https://dashscope.console.aliyun.com/apiKey")
        sys.exit(1)

    # 通义千问兼容 OpenAI 接口
    client = OpenAI(api_key=api_key, base_url="https://dashscope.aliyuncs.com/compatible-mode/v1")

    prompt = SUMMARY_PROMPT.format(transcript=transcript)

    print("🤖 正在调用通义千问生成会议纪要...")
    start_time = time.time()

    response = client.chat.completions.create(
        model="qwen-max",
        messages=[
            {"role": "system", "content": "你是专业的会议纪要助手，擅长从口语化的转写文本中提取结构化信息。"},
            {"role": "user", "content": prompt},
        ],
        temperature=0.3,
        max_tokens=4096,
    )

    elapsed = time.time() - start_time
    content = response.choices[0].message.content
    usage = response.usage

    # 通义千问定价：输入 2元/百万token，输出 6元/百万token
    input_cost = (usage.prompt_tokens / 1_000_000) * 2.0
    output_cost = (usage.completion_tokens / 1_000_000) * 6.0
    total_cost = input_cost + output_cost

    print(f"✅ 纪要生成完成！耗时 {elapsed:.1f}s")
    print(f"   Token 用量 - 输入: {usage.prompt_tokens}, 输出: {usage.completion_tokens}")
    print(f"   费用: ¥{total_cost:.4f}")

    return {
        "content": content,
        "elapsed": elapsed,
        "method": "qwen-max",
        "prompt_tokens": usage.prompt_tokens,
        "completion_tokens": usage.completion_tokens,
        "cost": total_cost,
    }


def summarize_with_longcat(transcript: str, api_key: str) -> dict:
    """
    使用 LongCat-Flash-Chat（美团大模型）生成结构化会议纪要
    优点：公测期每天50万token免费、OpenAI兼容接口
    """
    try:
        from openai import OpenAI
    except ImportError:
        print("❌ 未安装 openai，请运行: pip install openai")
        sys.exit(1)

    if not api_key:
        api_key = os.environ.get("LONGCAT_API_KEY", "")
    if not api_key:
        print("❌ 未设置 LONGCAT_API_KEY")
        print("   获取地址: https://longcat.chat/platform")
        sys.exit(1)

    # LongCat 兼容 OpenAI 接口
    client = OpenAI(api_key=api_key, base_url="https://api.longcat.chat/openai")

    prompt = SUMMARY_PROMPT.format(transcript=transcript)

    print("🤖 正在调用 LongCat-2.0 生成会议纪要...")
    start_time = time.time()

    response = client.chat.completions.create(
        model="LongCat-2.0",
        messages=[
            {"role": "system", "content": "你是专业的会议纪要助手，擅长从口语化的转写文本中提取结构化信息。"},
            {"role": "user", "content": prompt},
        ],
        temperature=0.3,
        max_tokens=4096,
    )

    elapsed = time.time() - start_time
    content = response.choices[0].message.content
    usage = response.usage

    # LongCat 公测期免费，费用为 0
    total_cost = 0.0

    print(f"✅ 纪要生成完成！耗时 {elapsed:.1f}s")
    print(f"   Token 用量 - 输入: {usage.prompt_tokens}, 输出: {usage.completion_tokens}")
    print(f"   费用: ¥{total_cost:.4f}（公测期免费）")

    return {
        "content": content,
        "elapsed": elapsed,
        "method": "LongCat-2.0",
        "prompt_tokens": usage.prompt_tokens,
        "completion_tokens": usage.completion_tokens,
        "cost": total_cost,
    }


# ============================================================
# 第三部分：Demo 模式（无需API和音频）
# ============================================================

DEMO_TRANSCRIPT = """
张经理：好，我们开始今天的产品周会。首先讨论一下上周用户反馈的情况。

小李：上周我们收到了35条用户反馈，其中关于搜索功能的投诉最多，有12条。用户反映搜索结果不准确，特别是一些长尾词。

张经理：搜索准确率这个问题，技术这边什么情况？

小王：我看了下日志，主要问题是我们的分词器对一些专业术语处理不好。我建议这周先优化分词词典，预计能解决60%的投诉。

张经理：行，那这个分词优化小王你负责，周五前完成。

小王：好的，周五前完成分词词典优化。

张经理：第二个议题，新版本下周的发布计划。UI改版验收了吗？

小李：UI改版昨天已经验收通过了，设计师那边确认没问题。但是支付模块还差一个联调，需要跟后端确认接口。

小王：支付接口我来对接，明天之前给前端联调文档。

张经理：好，那发布时间定在下周三晚上10点，避开高峰期。小李你负责发公告。

小李：收到，我周一就准备好发布公告和更新日志。

张经理：第三个议题，下季度的OKR。我们这个季度DAU增长了15%，但留存率下降了3个百分点。下季度重点要抓留存。

小李：留存下降主要在新用户次日留存，可能是新手引导做得不够好。

张经理：那下季度OKR这样定：第一，7日留存率提升到40%以上；第二，新手引导优化上线；第三，搜索满意度达到90%。大家有没有意见？

小王：没问题，搜索满意度90%可以做到。

小李：新手引导我下周出方案。

张经理：好，今天就到这里。总结一下待办：小王负责分词优化周五前完成、支付接口明天前给文档；小李负责发布公告和更新日志、新手引导方案下周出。散会。
"""


def run_demo() -> dict:
    """Demo模式：用内置示例文本演示完整流程，无需任何API"""
    print("\n" + "=" * 60)
    print("🎬 Demo 模式：使用内置示例会议文本演示")
    print("=" * 60)

    # 模拟转写结果
    stt_result = {
        "text": DEMO_TRANSCRIPT.strip(),
        "segments": [],
        "elapsed": 0.0,
        "method": "demo-builtin",
        "cost": 0.0,
    }

    print(f"\n📄 模拟会议文本（{len(stt_result['text'])} 字符）")
    print("-" * 40)
    print(stt_result["text"][:200] + "...")
    print("-" * 40)

    # 模拟大模型总结（本地生成，不调用API）
    print("\n🤖 正在生成结构化会议纪要（本地模拟）...")

    summary_content = """## 会议信息
- **主题**：产品周会
- **时间**：无法从文本识别具体日期
- **参会人**：张经理、小李、小王

## 议题与结论

### 议题一：用户反馈与搜索优化
**讨论要点**：
- 上周收到35条用户反馈，其中12条关于搜索功能不准确
- 主要问题：分词器对专业术语处理不好，长尾词搜索结果差
**结论**：
- 优化分词词典，预计解决60%的投诉
- 由小王负责，周五前完成

### 议题二：新版本发布计划
**讨论要点**：
- UI改版已验收通过
- 支付模块需与后端联调，缺少接口文档
**结论**：
- 发布时间定于下周三晚上10点
- 小王明天前提供支付接口联调文档
- 小李负责准备发布公告和更新日志

### 议题三：下季度OKR制定
**讨论要点**：
- 本季度DAU增长15%，但留存率下降3个百分点
- 留存下降主要在新用户次日留存，新手引导需优化
**结论**：
- 下季度三大OKR：7日留存率≥40%、新手引导优化上线、搜索满意度≥90%

## 待办事项
| 序号 | 任务内容 | 负责人 | 截止时间 |
|------|----------|--------|----------|
| 1 | 优化搜索分词词典 | 小王 | 本周五前 |
| 2 | 提供支付接口联调文档 | 小王 | 明天前 |
| 3 | 准备版本发布公告和更新日志 | 小李 | 下周一前 |
| 4 | 输出新手引导优化方案 | 小李 | 下周内 |

## 其他备注
- 新版本发布时间：下周三晚10点（避开高峰期）
- 下季度重点方向：用户留存提升
"""

    llm_result = {
        "content": summary_content,
        "elapsed": 0.5,
        "method": "demo-local",
        "prompt_tokens": len(DEMO_TRANSCRIPT) // 2,  # 粗略估算
        "completion_tokens": len(summary_content) // 2,
        "cost": 0.0,
    }

    print(f"✅ 纪要生成完成！（本地模拟）")
    print(f"   模拟Token - 输入: {llm_result['prompt_tokens']}, 输出: {llm_result['completion_tokens']}")

    return {"stt": stt_result, "llm": llm_result}


# ============================================================
# 第四部分：主流程与输出
# ============================================================

def generate_final_document(stt_result: dict, llm_result: dict, output_path: str):
    """生成最终 Markdown 会议纪要文档"""

    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    total_cost = stt_result["cost"] + llm_result["cost"]

    header = f"""# 📋 会议纪要

> 由 AI 会议纪要助手自动生成
> 生成时间：{now}

---

## 技术信息

| 环节 | 方法 | 耗时 | 费用 |
|------|------|------|------|
| 语音转文字 | {stt_result['method']} | {stt_result['elapsed']:.1f}s | ¥{stt_result['cost']:.4f} |
| 结构化总结 | {llm_result['method']} | {llm_result['elapsed']:.1f}s | ¥{llm_result['cost']:.4f} |
| **合计** | - | **{stt_result['elapsed'] + llm_result['elapsed']:.1f}s** | **¥{total_cost:.4f}** |

---

"""

    # 完整转写文本（附在末尾供参考）
    transcript_section = f"""

---

## 附：完整转写文本

<details>
<summary>点击展开完整会议录音转写文本</summary>

{stt_result['text']}

</details>

---

> 本纪要由 AI 自动生成，重要决策请人工复核确认。
> 工具版本：EP01 会议纪要自动化 CLI v1.0
"""

    final_doc = header + llm_result["content"] + transcript_section

    with open(output_path, "w", encoding="utf-8") as f:
        f.write(final_doc)

    print(f"\n📝 会议纪要已保存: {output_path}")
    print(f"   总费用: ¥{total_cost:.4f}")

    return output_path


def main():
    parser = argparse.ArgumentParser(
        description="会议纪要自动化 CLI - EP01 AI落地实战课程配套工具",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例：
  # Demo 模式（无需API，推荐首次体验）
  python meeting_minutes.py --demo

  # 本地Whisper转写 + DeepSeek总结
  python meeting_minutes.py --audio meeting.mp3 --stt whisper --llm deepseek

  # 通义听悟 + 通义千问
  python meeting_minutes.py --audio meeting.mp3 --stt dashscope --llm qwen

  # 直接传入文字稿
  python meeting_minutes.py --transcript text.txt --llm deepseek
        """,
    )

    parser.add_argument("--demo", action="store_true", help="Demo模式，使用内置示例文本，无需API")
    parser.add_argument("--audio", type=str, help="音频或视频文件路径（mp3/wav/m4a/mp4/mov/mkv 等）")
    parser.add_argument("--transcript", type=str, help="直接传入文字稿文件路径")
    parser.add_argument("--stt", choices=["whisper", "dashscope"], default="whisper", help="语音转文字方式")
    parser.add_argument("--llm", choices=["deepseek", "qwen", "longcat"], default="deepseek", help="大模型选择")
    parser.add_argument("--whisper-model", default="small",
                        help="Whisper模型大小：tiny/base/small/medium/large-v3（默认 small，比 base 准确率高很多）")
    parser.add_argument("--whisper-language", default="zh",
                        help="强制转写语言（默认 zh 中文；设为 auto 自动检测）")
    parser.add_argument("--output", "-o", default="meeting_minutes.md", help="输出文件路径")
    parser.add_argument("--deepseek-key", default="", help="DeepSeek API Key")
    parser.add_argument("--dashscope-key", default="", help="通义听悟/千问 API Key")
    parser.add_argument("--longcat-key", default="", help="LongCat API Key（美团大模型）")

    args = parser.parse_args()

    print("\n" + "=" * 60)
    print("📋 会议纪要自动化 CLI 工具")
    print("   EP01 · AI落地实战课程配套")
    print("=" * 60)

    # Demo 模式
    if args.demo:
        results = run_demo()
        generate_final_document(results["stt"], results["llm"], args.output)
        print("\n✅ Demo 完成！打开生成的文件查看效果。")
        return

    # 正常模式
    if not args.audio and not args.transcript:
        print("❌ 请指定 --audio 或 --transcript，或使用 --demo 模式")
        parser.print_help()
        sys.exit(1)

    # 第一步：语音转文字
    print("\n📥 第一步：语音转文字")
    print("-" * 40)

    if args.transcript:
        stt_result = load_transcript_from_file(args.transcript)
    elif args.stt == "whisper":
        stt_result = transcribe_with_whisper_local(
            args.audio, args.whisper_model, args.whisper_language)
    elif args.stt == "dashscope":
        stt_result = transcribe_with_dashscope(args.audio, args.dashscope_key)

    # 第二步：大模型总结
    print("\n📥 第二步：大模型结构化总结")
    print("-" * 40)

    if args.llm == "deepseek":
        llm_result = summarize_with_deepseek(stt_result["text"], args.deepseek_key)
    elif args.llm == "qwen":
        llm_result = summarize_with_qwen(stt_result["text"], args.dashscope_key)
    elif args.llm == "longcat":
        llm_result = summarize_with_longcat(stt_result["text"], args.longcat_key)

    # 第三步：生成最终文档
    print("\n📥 第三步：生成会议纪要")
    print("-" * 40)

    generate_final_document(stt_result, llm_result, args.output)

    print("\n" + "=" * 60)
    print("✅ 全部完成！")
    print(f"   输出文件: {args.output}")
    print(f"   总耗时: {stt_result['elapsed'] + llm_result['elapsed']:.1f}s")
    print(f"   总费用: ¥{stt_result['cost'] + llm_result['cost']:.4f}")
    print("=" * 60)


if __name__ == "__main__":
    main()
