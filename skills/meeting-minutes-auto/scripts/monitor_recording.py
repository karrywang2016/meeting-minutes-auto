#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
录制监控辅助脚本（供 AI 轮询，路径E 专用）

读取 record_meeting.py 写出的遥测 JSON，输出一行可被 AI 解析的状态：
  REC rms=..dB peak=..dB sil=..s spoken=Y/N alert=0|1 reason=..

用法（AI 在监控循环中调用）：
  python monitor_recording.py --status-file recordings/recording_status.json
  python monitor_recording.py --status-file X --interval 15   # 先等 15s 再读

出口：始终 0。alert=1 时额外打印一行 ">>> ALERT <reason>" 供 AI 识别。
"""

import argparse
import json
import os
import sys
import time


def main():
    parser = argparse.ArgumentParser(description="读取录制遥测 JSON，输出可被 AI 解析的状态行")
    parser.add_argument("--status-file", required=True, help="record_meeting.py 写出的遥测 JSON 路径")
    parser.add_argument("--interval", type=float, default=0.0,
                        help="读取前先等待的秒数（让一次调用完成「等待+读取」）")
    args = parser.parse_args()

    if args.interval and args.interval > 0:
        time.sleep(min(args.interval, 120.0))

    if not os.path.exists(args.status_file):
        print(">>> NO_STATUS_FILE")  # 录制尚未开始写遥测
        return 0

    try:
        with open(args.status_file, "r", encoding="utf-8") as f:
            st = json.load(f)
    except Exception as e:
        print(f">>> STATUS_PARSE_ERROR {e}")
        return 0

    elapsed = st.get("elapsed_sec", 0.0)
    rms = st.get("rms_db", -99.0)
    peak = st.get("peak_db", -99.0)
    sil = st.get("silence_sec", 0)
    spoken = "Y" if st.get("has_spoken") else "N"
    alert = int(st.get("alert", 0))
    reason = st.get("alert_reason", "")

    m, s = divmod(int(elapsed), 60)
    print(f"REC t={m:02d}:{s:02d} rms={rms:+.1f}dB peak={peak:+.1f}dB "
          f"sil={sil}s spoken={spoken} alert={alert}")

    if alert:
        print(f">>> ALERT {reason}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
