#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
本机会议录制工具 (Meeting Recorder)
EP01 · AI落地实战 · 会议纪要自动化

功能：
  - 录制麦克风音频（面对面会议、电话外放、线下讨论）
  - 录制系统音频（Zoom/Teams/网页会议，Windows WASAPI Loopback）
  - 实时音量电平显示 + 录制时长
  - 按回车键停止录制
  - 录制完成自动调用 meeting_minutes.py 转写+总结

使用示例：
  # 录制麦克风 + 自动生成纪要（面对面会议）
  python record_meeting.py record --source mic --auto-process

  # 录制系统音频 + 自动生成纪要（在线会议）
  python record_meeting.py record --source system --auto-process

  # 仅录制，稍后手动处理
  python record_meeting.py record --output meeting.wav

  # 列出所有音频设备
  python record_meeting.py --list-devices

  # 演示模式（不实际录制）
  python record_meeting.py --demo

依赖安装：
  pip install sounddevice soundfile numpy
  （转写+总结还需 meeting_minutes.py 的依赖：openai / openai-whisper）
"""

import argparse
import os
import sys
import time
import threading
import subprocess
import signal
import json
from datetime import datetime
from pathlib import Path

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
                if ffmpeg_dir not in os.environ.get("PATH", ""):
                    os.environ["PATH"] = ffmpeg_dir + os.pathsep + os.environ.get("PATH", "")
        except Exception:
            pass

_bootstrap_env()

# 录制依赖（延迟检查，让 --help 在未安装依赖时也能用）
try:
    import sounddevice as sd
    import soundfile as sf
    import numpy as np
    RECORDING_AVAILABLE = True
except ImportError:
    RECORDING_AVAILABLE = False

SCRIPT_DIR = Path(__file__).parent
MEETING_MINUTES_SCRIPT = SCRIPT_DIR / "meeting_minutes.py"


def check_dependencies():
    """检查录制依赖是否已安装"""
    if not RECORDING_AVAILABLE:
        print("错误：录制依赖未安装。请运行：")
        print("  pip install sounddevice soundfile numpy")
        print()
        print("如果使用国内镜像：")
        print("  pip install sounddevice soundfile numpy -i https://pypi.tuna.tsinghua.edu.cn/simple")
        sys.exit(1)


def list_devices():
    """列出所有可用音频输入设备"""
    print("\n" + "=" * 60)
    print("  可用音频设备")
    print("=" * 60)
    devices = sd.query_devices()

    print("\n  📥 输入设备（麦克风等）：\n")
    input_count = 0
    for i, d in enumerate(devices):
        if d['max_input_channels'] > 0:
            input_count += 1
            default_mark = " ← 默认" if i == sd.default.device[0] else ""
            print(f"    [{i}] {d['name']}{default_mark}")
            print(f"        声道: {d['max_input_channels']} | 采样率: {int(d['default_samplerate'])}Hz")

    # Windows 上输出设备可用于 loopback 录制系统音频
    print("\n  🔊 输出设备（Windows可录制系统音频）：\n")
    output_count = 0
    for i, d in enumerate(devices):
        if d['max_output_channels'] > 0:
            output_count += 1
            default_mark = " ← 默认" if i == sd.default.device[1] else ""
            print(f"    [{i}] {d['name']}{default_mark}")

    if input_count == 0:
        print("\n  ⚠ 未找到任何输入设备，请检查麦克风连接")
    print(f"\n  提示：用 --device <索引> 指定录音设备")
    print(f"  提示：录系统音频用 --source system（Windows自动用WASAPI Loopback）\n")


class MeetingRecorder:
    """会议录制器"""

    def __init__(self, output_path, source='mic', device=None,
                 sample_rate=44100, channels=1, duration=None, stop_flag=None,
                 status_file=None, silence_guard=90, no_speech_guard=60):
        self.output_path = output_path
        self.source = source
        self.device = device
        self.sample_rate = sample_rate
        self.channels = channels
        self.duration = duration  # 定时录制（秒），None=交互式按回车停止
        self.stop_flag = stop_flag  # 标志文件路径，文件出现则停止（跨平台可靠）
        self.status_file = status_file  # 遥测 JSON 路径，供 AI 轮询（检测静音/会议结束）
        self.silence_guard = float(silence_guard)  # 有发言后静音超过此秒数 → 疑似会议结束告警
        self.no_speech_guard = float(no_speech_guard)  # 全程无任何声音超过此秒数 → 收音异常告警
        self.recording = []
        self.is_recording = False
        self.start_time = None
        self._loopback = False
        self._actual_samplerate = sample_rate
        self._current_volume = 0.0
        # 遥测运行时状态
        self._silence_sec = 0.0
        self._has_spoken = False
        self._alert = 0
        self._alert_reason = ""
        self._last_tick = None

    def _resolve_device(self):
        """根据 source 解析录音设备和参数"""
        if self.device is not None:
            info = sd.query_devices(self.device)
            if info['max_input_channels'] > 0:
                # 标准输入设备
                self._actual_samplerate = info['default_samplerate']
            elif sys.platform == 'win32' and info['max_output_channels'] > 0:
                # 输出设备 → Windows WASAPI Loopback 录制系统音频
                self._loopback = True
                self._actual_samplerate = info['default_samplerate']
                self.channels = min(info['max_output_channels'], 2)
            return

        if self.source == 'mic':
            # 默认麦克风
            try:
                info = sd.query_devices(kind='input')
                self.device = info['index']
                self._actual_samplerate = info['default_samplerate']
            except sd.PortAudioError:
                raise RuntimeError("未找到麦克风设备，请用 --list-devices 查看可用设备")

        elif self.source == 'system':
            # 系统音频（Windows WASAPI Loopback）
            if sys.platform != 'win32':
                raise RuntimeError(
                    f"系统音频录制在 {sys.platform} 上需要额外配置：\n"
                    f"  • Mac: 安装 BlackHole 虚拟音频设备后用 --device 指定\n"
                    f"  • Linux: 使用 PulseAudio monitor source\n"
                    f"  • 或直接用 --source mic 录制麦克风（外放声音也能录到）"
                )
            try:
                info = sd.query_devices(kind='output')
                self.device = info['index']
                self._loopback = True
                self._actual_samplerate = info['default_samplerate']
                self.channels = min(info['max_output_channels'], 2)
            except sd.PortAudioError:
                raise RuntimeError("未找到输出设备，无法录制系统音频")

    def _countdown(self, seconds=3):
        """录制前倒计时"""
        print()
        for i in range(seconds, 0, -1):
            print(f"\r  ⏳ 准备录制... {i} ", end='', flush=True)
            time.sleep(1)
        print("\r  ▶ 录制中！按 [回车] 停止          \n")

    def _audio_callback(self, indata, frames, time_info, status):
        """音频回调：收集数据 + 计算实时音量"""
        self.recording.append(indata.copy())
        # 计算 RMS 音量
        vol = float(np.sqrt(np.mean(indata ** 2)))
        self._current_volume = vol

    def _keyboard_listener(self):
        """监听回车键停止录制"""
        try:
            input()
        except (EOFError, OSError):
            pass
        self.is_recording = False

    def _volume_display(self):
        """实时显示音量条和录制时长"""
        bar_length = 28
        while self.is_recording:
            elapsed = time.time() - self.start_time
            mins = int(elapsed // 60)
            secs = int(elapsed % 60)

            vol = self._current_volume
            vol_norm = min(vol * 12, 1.0)  # 归一化
            bar_filled = int(vol_norm * bar_length)
            bar = '█' * bar_filled + '░' * (bar_length - bar_filled)

            if vol_norm < 0.05:
                level = '🔇静音'
            elif vol_norm < 0.2:
                level = '🔈 低  '
            elif vol_norm < 0.6:
                level = '🔊正常'
            else:
                level = '📢偏高'

            print(f"\r  ⏱ {mins:02d}:{secs:02d} │{bar}│ {level}   ", end='', flush=True)
            time.sleep(0.2)

    def _telemetry(self):
        """后台线程：每 1s 采样电平并写入 status JSON + 输出结构化 REC_STATUS 行。

        告警逻辑（置 alert=1，但**不自动停止**，交给 AI/用户决定）：
          • 已检测到发言后，连续静音 ≥ silence_guard 秒  → 疑似「会议已结束」
          • 全程始终未检测到任何声音，且已录制 ≥ no_speech_guard 秒 → 「收音异常」
        一旦重新检测到发言，alert 自动复位，避免反复打扰。
        """
        import json as _json
        self._silence_sec = 0.0
        self._has_spoken = False
        self._alert = 0
        self._alert_reason = ""
        self._last_tick = time.time()
        speech_thresh = 0.05  # 与音量条「🔇静音」边界一致（vol_norm < 0.05 视为静音）

        while self.is_recording:
            time.sleep(1.0)
            now = time.time()
            # vol_norm 与 _volume_display 中一致：min(vol*12, 1.0)
            vol_norm = min(self._current_volume * 12.0, 1.0)
            is_speech = vol_norm >= speech_thresh
            dt = now - self._last_tick
            self._last_tick = now

            if is_speech:
                self._has_spoken = True
                self._silence_sec = 0.0
                self._alert = 0
                self._alert_reason = ""
            else:
                self._silence_sec += dt

            elapsed = now - self.start_time if self.start_time else 0.0
            rms_db = 20 * np.log10(self._current_volume + 1e-9)
            peak_db = 20 * np.log10(max(self._current_volume, 1e-9))

            # 触发告警（仅置位，不停止）
            if self._has_spoken and self._silence_sec >= self.silence_guard:
                self._alert = 1
                self._alert_reason = (f"会议可能已结束（已静音 {int(self._silence_sec)} 秒，"
                                           f"此前检测到发言）")
            elif (not self._has_spoken) and elapsed >= self.no_speech_guard:
                self._alert = 1
                self._alert_reason = (f"已录制 {int(elapsed)} 秒但未检测到任何声音，"
                                           f"请检查收音/麦克风设备")

            line = (f"REC_STATUS rms={rms_db:+.1f}dB peak={peak_db:+.1f}dB "
                    f"sil={int(self._silence_sec)}s spoken={'Y' if self._has_spoken else 'N'} "
                    f"alert={self._alert}")
            if self._alert:
                line += f" REASON={self._alert_reason}"
            print(line, flush=True)

            if self.status_file:
                try:
                    _json.dump({
                        "elapsed_sec": round(elapsed, 1),
                        "rms_db": round(rms_db, 1),
                        "peak_db": round(peak_db, 1),
                        "silence_sec": int(self._silence_sec),
                        "has_spoken": self._has_spoken,
                        "alert": self._alert,
                        "alert_reason": self._alert_reason,
                        "output": self.output_path,
                    }, open(self.status_file, "w", encoding="utf-8"),
                        ensure_ascii=False, indent=2)
                except Exception:
                    pass

    def record(self):
        """执行录制流程"""
        self._resolve_device()

        # 构建流参数
        stream_kwargs = {
            'samplerate': int(self._actual_samplerate),
            'channels': self.channels,
            'dtype': 'float32',
            'callback': self._audio_callback,
        }

        if self._loopback and sys.platform == 'win32':
            stream_kwargs['device'] = self.device
            stream_kwargs['extra_settings'] = sd.WasapiSettings(loopback=True)
        else:
            stream_kwargs['device'] = self.device

        # 显示录制信息
        device_name = "默认"
        try:
            device_name = sd.query_devices(self.device)['name']
        except Exception:
            pass

        src_label = {'mic': '🎤 麦克风', 'system': '🖥 系统音频'}.get(self.source, self.source)
        loopback_tag = " (WASAPI Loopback)" if self._loopback else ""
        print(f"  录音设备: {device_name}")
        print(f"  录音来源: {src_label}{loopback_tag}")
        print(f"  采样率: {int(self._actual_samplerate)}Hz | 声道: {self.channels}")

        self._countdown(3)

        self.is_recording = True
        self.start_time = time.time()

        # 注册信号处理：agent 通过 kill -SIGTERM/SIGINT 优雅停止录制
        self._orig_sigint = signal.getsignal(signal.SIGINT)
        self._orig_sigterm = signal.getsignal(signal.SIGTERM)

        def _graceful_stop(signum, frame):
            sig_name = signal.Signals(signum).name
            print(f"\n  📨 收到 {sig_name} 信号，正在停止录制并保存...")
            self.is_recording = False

        signal.signal(signal.SIGINT, _graceful_stop)
        signal.signal(signal.SIGTERM, _graceful_stop)

        # 启动停止监听：定时模式 vs 交互模式
        if self.duration is not None:
            # 定时模式：到时间自动停止（适合 agent 自动化调用）
            def _auto_stop():
                time.sleep(self.duration)
                self.is_recording = False
            stop_thread = threading.Thread(target=_auto_stop, daemon=True)
            stop_thread.start()
            print(f"  ⏱ 定时录制: {self.duration} 秒后自动停止")
        else:
            # 交互模式：按回车停止（需要终端）
            kb_thread = threading.Thread(target=self._keyboard_listener, daemon=True)
            kb_thread.start()

        # 启动音量显示线程
        vol_thread = threading.Thread(target=self._volume_display, daemon=True)
        vol_thread.start()

        # 启动遥测线程（写 JSON 供 AI 轮询 + 静音/结束告警）
        self._last_tick = time.time()
        self._alert = 0
        self._alert_reason = ""
        self._has_spoken = False
        self._silence_sec = 0.0
        if self.status_file:
            try:
                import json as _j
                _j.dump({
                    "elapsed_sec": 0.0, "rms_db": -99.0, "peak_db": -99.0,
                    "silence_sec": 0, "has_spoken": False, "alert": 0,
                    "alert_reason": "", "output": self.output_path,
                }, open(self.status_file, "w", encoding="utf-8"),
                    ensure_ascii=False, indent=2)
            except Exception:
                pass
        tel_thread = threading.Thread(target=self._telemetry, daemon=True)
        tel_thread.start()

        # 开始录制
        try:
            with sd.InputStream(**stream_kwargs):
                while self.is_recording:
                    time.sleep(0.1)
                    # 跨平台停止机制：检测标志文件（Windows下信号不可靠）
                    if self.stop_flag and os.path.exists(self.stop_flag):
                        print(f"\n  🏁 检测到停止标志文件，正在停止录制并保存...")
                        try:
                            os.remove(self.stop_flag)
                        except OSError:
                            pass
                        self.is_recording = False
        except Exception as e:
            print(f"\n  ❌ 录制出错: {e}")
            print(f"     提示: 用 --list-devices 查看可用设备，或用 --device 指定其他设备")
            signal.signal(signal.SIGINT, self._orig_sigint)
            signal.signal(signal.SIGTERM, self._orig_sigterm)
            return False

        # 恢复原始信号处理
        signal.signal(signal.SIGINT, self._orig_sigint)
        signal.signal(signal.SIGTERM, self._orig_sigterm)

        elapsed = time.time() - self.start_time
        mins = int(elapsed // 60)
        secs = int(elapsed % 60)
        print(f"\n\n  ⏹ 录制结束 | 总时长: {mins:02d}:{secs:02d}\n")
        return True

    def save(self):
        """保存录音文件为 WAV"""
        if not self.recording:
            print("  ⚠ 没有录制到音频数据（可能设备未正常工作）")
            return False

        audio_data = np.concatenate(self.recording, axis=0)
        Path(self.output_path).parent.mkdir(parents=True, exist_ok=True)

        sf.write(self.output_path, audio_data, int(self._actual_samplerate))

        file_size = os.path.getsize(self.output_path) / 1024  # KB
        duration = len(audio_data) / int(self._actual_samplerate)
        print(f"  💾 已保存: {self.output_path}")
        print(f"     时长: {duration:.1f}s | 大小: {file_size:.1f}KB | 格式: WAV")
        return True

    def auto_process(self, llm='deepseek', stt='whisper'):
        """录制完成后自动调用 meeting_minutes.py 转写+总结"""
        if not MEETING_MINUTES_SCRIPT.exists():
            print(f"  ⚠ 未找到转写脚本: {MEETING_MINUTES_SCRIPT}")
            print(f"     音频已保存，请手动处理")
            return False

        print(f"\n  🔄 自动转写 + 结构化总结中...")
        print(f"     引擎: STT={stt}, LLM={llm}")
        print(f"     较长录音处理需要时间，请耐心等待...\n")

        cmd = [
            sys.executable, str(MEETING_MINUTES_SCRIPT),
            '--audio', self.output_path,
            '--stt', stt,
            '--llm', llm,
        ]

        try:
            result = subprocess.run(cmd, cwd=str(SCRIPT_DIR))
            if result.returncode == 0:
                print("\n  ✅ 会议纪要生成完成！")
                return True
            else:
                print(f"\n  ⚠ 转写脚本返回错误码: {result.returncode}")
                print(f"     音频文件已保存，可手动重试: python meeting_minutes.py --audio \"{self.output_path}\"")
                return False
        except Exception as e:
            print(f"\n  ❌ 调用转写脚本失败: {e}")
            return False


def demo_mode():
    """演示模式：展示使用流程，不实际录制"""
    print("\n" + "=" * 56)
    print("  本机会议录制工具 · 演示模式")
    print("=" * 56)
    print()
    print("  此模式不实际录制，仅展示功能和使用方法。\n")

    print("  适用场景：")
    print("    • 线下面对面会议（麦克风录制）")
    print("    • 微信语音 / 电话会议（外放录制）")
    print("    • Zoom / Teams / 网页会议（系统音频录制）")
    print("    • 临时讨论、头脑风暴\n")

    print("  使用示例：\n")
    print("    # 1. 录麦克风 + 自动出纪要（面对面会议）")
    print("    python record_meeting.py record --source mic --auto-process\n")
    print("    # 2. 录系统音频 + 自动出纪要（在线会议）")
    print("    python record_meeting.py record --source system --auto-process\n")
    print("    # 3. 仅录制，稍后手动处理")
    print("    python record_meeting.py record --output meeting.wav\n")
    print("    # 4. 列出可用音频设备")
    print("    python record_meeting.py --list-devices\n")
    print("    # 5. 指定设备录制")
    print("    python record_meeting.py record --device 2 --auto-process\n")

    print("  录制流程：")
    print("    3秒倒计时 → 实时音量条 → 按回车停止 → 保存WAV → 自动转写+总结\n")

    print("  录制界面预览：")
    print("  ┌──────────────────────────────────────────────┐")
    print("  │ ⏱ 05:23 │████████████░░░░░░░░░░░░│ 🔊正常    │")
    print("  │                                                │")
    print("  │            按 [回车] 停止录制                  │")
    print("  └──────────────────────────────────────────────┘")
    print()
    print("  ✅ 演示结束。去掉 --demo 即可实际录制。\n")


def main():
    parser = argparse.ArgumentParser(
        description='本机会议录制工具 - 录制会议音频并自动生成纪要',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
使用示例:
  %(prog)s record --source mic --auto-process      录麦克风+自动出纪要
  %(prog)s record --source system --auto-process   录系统音频+自动出纪要
  %(prog)s record --output my.wav                  录制到指定文件
  %(prog)s --list-devices                          列出音频设备
  %(prog)s --demo                                  演示模式
        """
    )

    parser.add_argument('command', nargs='?', default=None,
                        choices=['record'],
                        help='record: 开始录制')
    parser.add_argument('--source', default='mic', choices=['mic', 'system'],
                        help='录音来源: mic=麦克风(默认), system=系统音频')
    parser.add_argument('--device', type=int, default=None,
                        help='指定音频设备索引（用 --list-devices 查看）')
    parser.add_argument('--output', '-o', default=None,
                        help='输出音频文件路径（默认: recordings/会议_时间戳.wav）')
    parser.add_argument('--sample-rate', type=int, default=44100,
                        help='采样率（默认: 44100，系统音频会自动适配）')
    parser.add_argument('--channels', type=int, default=1,
                        help='声道数（默认: 1 单声道，系统音频自动为2）')
    parser.add_argument('--auto-process', action='store_true',
                        help='录制完成后自动调用转写+总结')
    parser.add_argument('--stt', default='whisper', choices=['whisper', 'dashscope'],
                        help='语音转文字引擎（auto-process时使用，默认whisper）')
    parser.add_argument('--llm', default='deepseek', choices=['deepseek', 'qwen', 'longcat'],
                        help='大模型引擎（auto-process时使用，默认deepseek）')
    parser.add_argument('--list-devices', action='store_true',
                        help='列出所有可用音频设备')
    parser.add_argument('--demo', action='store_true',
                        help='演示模式（不实际录制）')
    parser.add_argument('--duration', type=float, default=None,
                        help='定时录制秒数（不指定则按回车停止，适合agent自动化调用）')
    parser.add_argument('--stop-flag', default=None,
                        help='停止标志文件路径：该文件出现时录制优雅保存并退出（跨平台可靠，Windows推荐）')
    parser.add_argument('--status-file', default=None,
                        help='遥测 JSON 输出路径：每 1s 写入 elapsed/rms/silence_sec/has_spoken/alert，供 AI 轮询检测静音与会议结束')
    parser.add_argument('--silence-guard', type=float, default=90,
                        help='有发言后连续静音达到该秒数 → 触发「会议可能已结束」告警（默认 90，不自动停止）')
    parser.add_argument('--no-speech-guard', type=float, default=60,
                        help='全程未检测到任何声音达到该秒数 → 触发「收音异常」告警（默认 60）')

    args = parser.parse_args()

    if args.demo:
        demo_mode()
        return

    if args.list_devices:
        check_dependencies()
        list_devices()
        return

    if args.command != 'record':
        parser.print_help()
        return

    check_dependencies()

    # 生成默认输出路径
    if args.output is None:
        recordings_dir = SCRIPT_DIR / 'recordings'
        recordings_dir.mkdir(exist_ok=True)
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        args.output = str(recordings_dir / f'会议_{timestamp}.wav')

    # 创建录制器并执行
    recorder = MeetingRecorder(
        output_path=args.output,
        source=args.source,
        device=args.device,
        sample_rate=args.sample_rate,
        channels=args.channels,
        duration=args.duration,
        stop_flag=args.stop_flag,
        status_file=args.status_file,
        silence_guard=args.silence_guard,
        no_speech_guard=args.no_speech_guard,
    )

    # 录制
    if not recorder.record():
        sys.exit(1)

    # 保存
    if not recorder.save():
        sys.exit(1)

    # 自动处理
    if args.auto_process:
        recorder.auto_process(llm=args.llm, stt=args.stt)
    else:
        print(f"\n  💡 提示: 加 --auto-process 可自动转写+生成纪要")
        print(f"     或手动运行:")
        print(f"     python meeting_minutes.py --audio \"{args.output}\" --stt whisper --llm deepseek\n")


if __name__ == '__main__':
    main()
