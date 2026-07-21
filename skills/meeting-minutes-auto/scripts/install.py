#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
会议纪要自动化技能 · 一键安装脚本
================================

功能：
  1. 检测/创建 Python 虚拟环境（venv）
  2. 安装全部 pip 依赖（requirements.txt）
  3. 检测 ffmpeg，Windows 下自动下载到技能目录
  4. 验证关键模块可正常导入
  5. 输出安装报告

用法：
  python scripts/install.py              # 完整安装
  python scripts/install.py --check      # 仅检测，不安装
  python scripts/install.py --no-ffmpeg  # 跳过 ffmpeg 下载
  python scripts/install.py --quiet      # 静默模式（仅输出错误和摘要）

设计原则：
  - 幂等：重复运行不会出错，已安装的跳过
  - 跨平台：Windows/Mac/Linux 均可运行
  - 自包含：不依赖外部脚本，纯 Python 标准库实现
  - 友好：彩色输出 + 进度提示 + 错误诊断
"""

import os
import sys
import subprocess
import platform
import shutil
import json
import urllib.request
import zipfile
import tempfile
from pathlib import Path

# ============================================================
# 配置
# ============================================================

SCRIPT_DIR = Path(__file__).parent.resolve()
SKILL_DIR = SCRIPT_DIR.parent
REQUIREMENTS_FILE = SCRIPT_DIR / "requirements.txt"

# venv 目录：放在技能目录下，避免污染全局环境
# 但如果 WorkBuddy 托管 Python 的 venv 已存在，优先使用
WORKBUDDY_VENV = Path(os.path.expanduser("~/.workbuddy/binaries/python/envs/default"))
LOCAL_VENV = SCRIPT_DIR / "venv"

# ffmpeg 下载地址（Windows）
FFMPEG_DIR = SCRIPT_DIR / "ffmpeg"
FFMPEG_WIN_URL = "https://github.com/BtbN/FFmpeg-Builds/releases/download/latest/ffmpeg-master-latest-win64-gpl.zip"
# 备用地址（更稳定但版本旧）
FFMPEG_WIN_FALLBACK = "https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip"

# 国内镜像（pip 安装加速）
PIP_MIRROR = "https://pypi.tuna.tsinghua.edu.cn/simple"

# 颜色输出
class Color:
    RESET = "\033[0m"
    RED = "\033[31m"
    GREEN = "\033[32m"
    YELLOW = "\033[33m"
    BLUE = "\033[34m"
    CYAN = "\033[36m"
    BOLD = "\033[1m"

def c(text, color):
    if not sys.stdout.isatty() and os.environ.get("NO_COLOR"):
        return text
    return f"{color}{text}{Color.RESET}"

# ============================================================
# 工具函数
# ============================================================

def info(msg):
    print(c(f"  [信息] {msg}", Color.CYAN))

def ok(msg):
    print(c(f"  [成功] {msg}", Color.GREEN))

def warn(msg):
    print(c(f"  [警告] {msg}", Color.YELLOW))

def error(msg):
    print(c(f"  [错误] {msg}", Color.RED))

def step(num, msg):
    print(c(f"\n━━━ 步骤 {num}: {msg} ━━━", Color.BLUE + Color.BOLD))

def run(cmd, **kwargs):
    """运行命令，返回 (returncode, stdout, stderr)"""
    result = subprocess.run(cmd, capture_output=True, text=True, **kwargs)
    return result.returncode, result.stdout, result.stderr

# ============================================================
# 步骤1：检测/选择 Python 环境
# ============================================================

def detect_python():
    """检测可用的 Python 解释器，优先使用 WorkBuddy 托管版本"""
    candidates = []

    # 优先：WorkBuddy 托管 Python
    workbuddy_py = Path(os.path.expanduser(
        "~/.workbuddy/binaries/python/versions/3.13.12/python.exe"
    ))
    if workbuddy_py.exists():
        candidates.append(("WorkBuddy托管", workbuddy_py))

    # 其次：当前 Python
    candidates.append(("当前Python", Path(sys.executable)))

    # 最后：系统 python3
    for name in ["python3", "python"]:
        path = shutil.which(name)
        if path:
            candidates.append((f"系统{name}", Path(path)))

    for label, py_path in candidates:
        try:
            rc, out, _ = run([str(py_path), "--version"])
            if rc == 0:
                version = out.strip()
                # 检查版本 >= 3.10
                parts = version.replace("Python ", "").split(".")
                major, minor = int(parts[0]), int(parts[1])
                if major >= 3 and minor >= 10:
                    return label, py_path, version
                else:
                    warn(f"{label} 版本过低: {version}（需要 3.10+）")
            else:
                warn(f"{label} 无法运行: {py_path}")
        except Exception as e:
            warn(f"{label} 检测失败: {e}")

    return None, None, None


def get_or_create_venv(python_path):
    """
    获取或创建虚拟环境
    策略：
      1. 如果 WorkBuddy 托管 venv 存在且可用，直接用
      2. 否则在技能目录下创建 venv
    """
    # 策略1：WorkBuddy 托管 venv
    wb_venv_python = WORKBUDDY_VENV / ("Scripts" if platform.system() == "Windows" else "bin") / ("python.exe" if platform.system() == "Windows" else "python")
    if wb_venv_python.exists():
        # 验证可用
        rc, out, _ = run([str(wb_venv_python), "-c", "import whisper; print('ok')"])
        if rc == 0:
            ok(f"使用 WorkBuddy 托管 venv: {WORKBUDDY_VENV}")
            return WORKBUDDY_VENV, wb_venv_python
        # venv 存在但 whisper 未装，也用它（后面会装）
        rc, out, _ = run([str(wb_venv_python), "--version"])
        if rc == 0:
            ok(f"使用 WorkBuddy 托管 venv（需安装依赖）: {WORKBUDDY_VENV}")
            return WORKBUDDY_VENV, wb_venv_python

    # 策略2：本地 venv
    local_venv_python = LOCAL_VENV / ("Scripts" if platform.system() == "Windows" else "bin") / ("python.exe" if platform.system() == "Windows" else "python")
    if local_venv_python.exists():
        rc, out, _ = run([str(local_venv_python), "--version"])
        if rc == 0:
            ok(f"使用本地 venv: {LOCAL_VENV}")
            return LOCAL_VENV, local_venv_python

    # 创建本地 venv
    info(f"创建虚拟环境: {LOCAL_VENV}")
    rc, out, err = run([str(python_path), "-m", "venv", str(LOCAL_VENV)])
    if rc != 0:
        error(f"创建 venv 失败: {err}")
        error("请手动创建: python -m venv scripts/venv")
        return None, None
    ok(f"虚拟环境已创建: {LOCAL_VENV}")
    return LOCAL_VENV, local_venv_python


def get_pip(venv_python):
    """获取 venv 内的 pip 路径"""
    if platform.system() == "Windows":
        pip = venv_python.parent / "pip.exe"
    else:
        pip = venv_python.parent / "pip"
    # 某些 venv 没有 pip 可执行文件，用 python -m pip
    return [str(venv_python), "-m", "pip"]

# ============================================================
# 步骤2：安装 pip 依赖
# ============================================================

def check_package_installed(venv_python, package):
    """检查某个包是否已安装"""
    rc, _, _ = run([str(venv_python), "-c", f"import {package}; print('ok')"])
    return rc == 0


def install_pip_deps(venv_python, use_mirror=True):
    """安装 requirements.txt 中的所有依赖"""
    if not REQUIREMENTS_FILE.exists():
        error(f"requirements.txt 不存在: {REQUIREMENTS_FILE}")
        return False

    pip_cmd = get_pip(venv_python)

    # 先升级 pip
    info("升级 pip...")
    mirror_args = ["-i", PIP_MIRROR] if use_mirror else []
    rc, out, err = run(pip_cmd + ["install", "--upgrade", "pip"] + mirror_args)
    if rc != 0:
        warn(f"pip 升级失败（不影响后续安装）: {err[:200]}")

    # 安装依赖
    info(f"安装依赖（来源: {REQUIREMENTS_FILE}）...")
    if use_mirror:
        info(f"使用国内镜像: {PIP_MIRROR}")

    cmd = pip_cmd + [
        "install",
        "-r", str(REQUIREMENTS_FILE),
        "--disable-pip-version-check",
    ] + mirror_args

    # 实时输出安装进度
    print(c("  ┌──────────────────────────────────────", Color.CYAN))
    process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    for line in process.stdout:
        # 只显示关键信息，过滤掉过多输出
        line = line.rstrip()
        if any(kw in line.lower() for kw in ["installing", "successfully", "downloading", "error", "warning", "collecting", "requirement already"]):
            print(f"  │ {line}")
    process.wait()
    print(c("  └──────────────────────────────────────", Color.CYAN))

    if process.returncode == 0:
        ok("全部 pip 依赖安装成功")
        return True
    else:
        error(f"pip 安装失败，返回码: {process.returncode}")
        return False

# ============================================================
# 步骤3：ffmpeg 检测与下载
# ============================================================

def find_ffmpeg():
    """查找系统中的 ffmpeg"""
    # 1. PATH 中的 ffmpeg
    path_ffmpeg = shutil.which("ffmpeg")
    if path_ffmpeg:
        return path_ffmpeg

    # 2. 技能目录下的 ffmpeg
    if platform.system() == "Windows":
        local_ffmpeg = FFMPEG_DIR / "bin" / "ffmpeg.exe"
    else:
        local_ffmpeg = FFMPEG_DIR / "bin" / "ffmpeg"
    if local_ffmpeg.exists():
        return str(local_ffmpeg)

    # 3. 常见安装路径（Windows）
    if platform.system() == "Windows":
        common_paths = [
            "D:/ffmpeg-4.2-win64-static/bin/ffmpeg.exe",
            "C:/ffmpeg/bin/ffmpeg.exe",
            os.path.expanduser("~/ffmpeg/bin/ffmpeg.exe"),
        ]
        for p in common_paths:
            if os.path.exists(p):
                return p

    return None


def download_ffmpeg_windows():
    """Windows 下自动下载 ffmpeg 到技能目录"""
    FFMPEG_DIR.mkdir(parents=True, exist_ok=True)

    urls = [FFMPEG_WIN_URL, FFMPEG_WIN_FALLBACK]
    for url in urls:
        try:
            info(f"尝试下载 ffmpeg: {url}")
            with tempfile.NamedTemporaryFile(suffix=".zip", delete=False) as tmp:
                tmp_path = tmp.name

            # 下载
            urllib.request.urlretrieve(url, tmp_path)
            ok(f"下载完成: {os.path.getsize(tmp_path) / 1024 / 1024:.1f}MB")

            # 解压
            info("解压中...")
            with zipfile.ZipFile(tmp_path, 'r') as zf:
                zf.extractall(FFMPEG_DIR)
            os.unlink(tmp_path)

            # 找到 ffmpeg.exe（解压后可能在子目录）
            ffmpeg_exe = None
            for root, dirs, files in os.walk(FFMPEG_DIR):
                for f in files:
                    if f.lower() == "ffmpeg.exe":
                        ffmpeg_exe = os.path.join(root, f)
                        break
                if ffmpeg_exe:
                    break

            if ffmpeg_exe:
                # 移动到标准位置 FFMPEG_DIR/bin/
                target_bin = FFMPEG_DIR / "bin"
                target_bin.mkdir(exist_ok=True)
                target_exe = target_bin / "ffmpeg.exe"
                if ffmpeg_exe != str(target_exe):
                    shutil.copy2(ffmpeg_exe, target_exe)
                    # 同时复制 ffprobe
                    ffprobe_src = os.path.join(os.path.dirname(ffmpeg_exe), "ffprobe.exe")
                    if os.path.exists(ffprobe_src):
                        shutil.copy2(ffprobe_src, target_bin / "ffprobe.exe")

                ok(f"ffmpeg 已安装: {target_exe}")
                return str(target_exe)
            else:
                warn("下载的 zip 中未找到 ffmpeg.exe")

        except Exception as e:
            warn(f"下载失败: {e}")
            continue

    error("所有下载源均失败，请手动安装 ffmpeg")
    return None


def setup_ffmpeg(skip_download=False):
    """检测/下载/配置 ffmpeg"""
    existing = find_ffmpeg()
    if existing:
        # 验证可用
        rc, out, _ = run([existing, "-version"])
        if rc == 0:
            version = out.split("\n")[0]
            ok(f"ffmpeg 已就绪: {existing}")
            info(f"版本: {version}")

            # 写入配置文件供脚本读取
            write_ffmpeg_config(existing)
            return existing

    if skip_download:
        warn("ffmpeg 未找到（已跳过下载）")
        warn("请手动安装:")
        if platform.system() == "Windows":
            warn("  方式1: 运行 python scripts/install.py （自动下载）")
            warn("  方式2: 从 https://www.gyan.dev/ffmpeg/builds/ 下载并解压")
            warn("  方式3: choco install ffmpeg")
        elif platform.system() == "Darwin":
            warn("  brew install ffmpeg")
        else:
            warn("  sudo apt install ffmpeg  或  sudo yum install ffmpeg")
        return None

    # Windows 自动下载
    if platform.system() == "Windows":
        info("Windows 环境，自动下载 ffmpeg...")
        result = download_ffmpeg_windows()
        if result:
            write_ffmpeg_config(result)
        return result
    else:
        warn("ffmpeg 未找到，请手动安装:")
        if platform.system() == "Darwin":
            warn("  brew install ffmpeg")
        else:
            warn("  sudo apt install ffmpeg")
        return None


def write_ffmpeg_config(ffmpeg_path):
    """将 ffmpeg 路径写入配置文件，供转写脚本读取"""
    config = SCRIPT_DIR / "env.json"
    data = {"ffmpeg_path": ffmpeg_path}
    try:
        with open(config, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        info(f"ffmpeg 路径已写入: {config}")
    except Exception as e:
        warn(f"写入配置失败: {e}")

# ============================================================
# 步骤4：验证安装
# ============================================================

def verify_installation(venv_python):
    """验证关键模块可正常导入"""
    print(c("\n  ┌──────────────────────────────────────", Color.CYAN))

    modules = [
        ("faster_whisper", "faster-whisper 引擎 (v1.1优先)"),
        ("whisper", "openai-whisper (回退引擎)"),
        ("torch", "PyTorch 推理引擎"),
        ("numpy", "数值计算"),
        ("openai", "大模型 API 客户端"),
        ("sounddevice", "音频录制"),
        ("soundfile", "音频文件读写"),
    ]

    all_ok = True
    for module, desc in modules:
        rc, out, err = run([str(venv_python), "-c", f"import {module}; print({module}.__version__ if hasattr({module}, '__version__') else 'ok')"])
        if rc == 0:
            version = out.strip()
            print(c(f"  │ ✅ {module:15s} {version:15s} {desc}", Color.GREEN))
        else:
            # faster_whisper 是可选的（有 openai-whisper 回退），whisper/torch 也可能因环境问题失败
            optional = module in ("faster_whisper", "dashscope")
            color = Color.YELLOW if optional else Color.RED
            mark = "⚪" if optional else "❌"
            label = "未安装(可选)" if optional else "MISSING"
            print(c(f"  │ {mark} {module:15s} {label:15s} {desc}", color))
            if not optional:
                all_ok = False

    # 可选模块
    rc, _, _ = run([str(venv_python), "-c", "import dashscope; print('ok')"])
    if rc == 0:
        print(c(f"  │ ✅ {"dashscope":15s} {"ok":15s} 通义听悟API (可选)", Color.GREEN))
    else:
        print(c(f"  │ ⚪ {"dashscope":15s} {"未安装":15s} 通义听悟API (可选)", Color.YELLOW))

    print(c("  └──────────────────────────────────────", Color.CYAN))
    return all_ok

# ============================================================
# 步骤5：生成环境信息文件
# ============================================================

def write_env_info(venv_path, venv_python, ffmpeg_path):
    """写入环境信息文件，供 SKILL.md / agent 读取"""
    env_info = {
        "venv_path": str(venv_path),
        "venv_python": str(venv_python),
        "ffmpeg_path": ffmpeg_path,
        "platform": platform.system(),
        "python_version": platform.python_version(),
        "installed_at": str(__import__("datetime").datetime.now()),
    }

    env_file = SCRIPT_DIR / "env.json"
    try:
        with open(env_file, "w", encoding="utf-8") as f:
            json.dump(env_info, f, indent=2, ensure_ascii=False)
        ok(f"环境信息已写入: {env_file}")
    except Exception as e:
        warn(f"写入环境信息失败: {e}")

# ============================================================
# 主流程
# ============================================================

def main():
    import argparse
    parser = argparse.ArgumentParser(description="会议纪要自动化技能 · 一键安装")
    parser.add_argument("--check", action="store_true", help="仅检测环境，不安装")
    parser.add_argument("--no-ffmpeg", action="store_true", help="跳过 ffmpeg 下载")
    parser.add_argument("--no-mirror", action="store_true", help="不使用国内镜像（用默认 PyPI）")
    parser.add_argument("--quiet", action="store_true", help="静默模式")
    args = parser.parse_args()

    print(c("\n" + "=" * 56, Color.BLUE + Color.BOLD))
    print(c("  会议纪要自动化技能 · 一键安装", Color.BLUE + Color.BOLD))
    print(c("=" * 56, Color.BLUE + Color.BOLD))

    print(f"\n  平台: {platform.system()} {platform.machine()}")
    print(f"  技能目录: {SKILL_DIR}")

    # ---- 步骤1: 检测 Python ----
    step(1, "检测 Python 环境")

    label, py_path, py_version = detect_python()
    if not py_path:
        error("未找到可用的 Python 3.10+，请先安装 Python")
        if platform.system() == "Windows":
            info("下载地址: https://www.python.org/downloads/")
        return 1

    ok(f"Python: {label} ({py_version})")
    info(f"路径: {py_path}")

    if args.check:
        # 仅检测模式
        step(2, "检测已安装依赖（仅检测模式）")
        # 优先检测 WorkBuddy venv
        check_py = WORKBUDDY_VENV / ("Scripts" if platform.system() == "Windows" else "bin") / ("python.exe" if platform.system() == "Windows" else "python")
        if not check_py.exists():
            check_py = py_path
        verify_installation(check_py)

        step(3, "检测 ffmpeg")
        ff = find_ffmpeg()
        if ff:
            ok(f"ffmpeg: {ff}")
        else:
            warn("ffmpeg 未安装")
        return 0

    # ---- 步骤2: 获取/创建 venv ----
    step(2, "准备虚拟环境")
    venv_path, venv_python = get_or_create_venv(py_path)
    if not venv_path:
        error("无法准备虚拟环境，安装终止")
        return 1

    # ---- 步骤3: 安装 pip 依赖 ----
    step(3, "安装 pip 依赖")

    # 检查是否已全部安装（幂等性）
    already_installed = all([
        check_package_installed(venv_python, "whisper"),
        check_package_installed(venv_python, "openai"),
        check_package_installed(venv_python, "sounddevice"),
        check_package_installed(venv_python, "soundfile"),
    ])

    if already_installed:
        ok("所有核心依赖已安装，跳过 pip install")
    else:
        success = install_pip_deps(venv_python, use_mirror=not args.no_mirror)
        if not success:
            error("依赖安装失败")
            info("可尝试: python scripts/install.py --no-mirror  （使用官方源）")
            return 1

    # ---- 步骤4: ffmpeg ----
    step(4, "检测/安装 ffmpeg")
    ffmpeg_path = setup_ffmpeg(skip_download=args.no_ffmpeg)

    # ---- 步骤5: 验证 ----
    step(5, "验证安装")
    all_ok = verify_installation(venv_python)

    # ---- 步骤6: 写入环境信息 ----
    step(6, "保存环境信息")
    write_env_info(venv_path, venv_python, ffmpeg_path)

    # ---- 摘要 ----
    print(c("\n" + "=" * 56, Color.BLUE + Color.BOLD))
    print(c("  安装摘要", Color.BLUE + Color.BOLD))
    print(c("=" * 56, Color.BLUE + Color.BOLD))

    print(f"\n  Python:  {py_version}")
    print(f"  venv:    {venv_path}")
    print(f"  ffmpeg:  {ffmpeg_path or '未安装（请手动安装）'}")

    if all_ok and ffmpeg_path:
        print(c("\n  ✅ 安装成功！技能已就绪。", Color.GREEN + Color.BOLD))
        print(c("  现在可以在 WorkBuddy 中说「帮我整理会议纪要」来使用。", Color.GREEN))
        return 0
    elif all_ok and not ffmpeg_path:
        print(c("\n  ⚠️  Python 依赖已就绪，但 ffmpeg 缺失。", Color.YELLOW))
        print(c("  路径A/B/C（平台纪要）可正常使用，路径D/E（本地音频）需先安装 ffmpeg。", Color.YELLOW))
        return 0
    else:
        print(c("\n  ❌ 部分依赖缺失，请查看上方错误信息。", Color.RED))
        return 1


if __name__ == "__main__":
    sys.exit(main())
