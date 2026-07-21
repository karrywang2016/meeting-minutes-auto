# 本地音频降级流程

## 适用场景

- 用户手头有 mp3/wav/m4a 录音文件，但不是腾讯会议/飞书/钉钉平台录制
- 平台连接器未启用，但需要处理会议录音
- 课程演示 Python 方案

## 方案1（优先）：飞书妙记上传

利用飞书妙记的 AI 转写能力处理本地音频，质量优于本地 Whisper。

### 前置条件
- 已启用飞书连接器（feishu）
- 已授权 drive、minutes domain

### 流程

```bash
# 1. 上传音频文件到飞书云空间
lark-cli drive +upload --file /path/to/meeting.mp3
# 输出: file_token

# 2. 用 file_token 生成妙记
lark-cli minutes +upload --file-token <file_token>
# 输出: minute_token

# 3. 等待转写完成（1分钟音频约处理10-30秒，大文件5-10分钟）
# 轮询状态直到 ready

# 4. 拉取四维信息
lark-cli minutes +detail --minute-tokens <minute_token> --summary --todo --transcript --chapter
```

### 优势
- 转写质量高（飞书 AI）
- 自动生成 AI 总结和待办
- 支持发言人识别

### 限制
- 文件大小限制（通常 <4GB）
- 需联网上传
- 处理时间取决于文件大小

---

## 方案2（兜底）：Python 脚本

当飞书不可用时，用本地 Python 脚本处理。

### 前置条件

**首次使用必须运行一键安装脚本**（自动创建 venv + 安装全部依赖 + 下载 ffmpeg）：

```bash
# Windows（使用 WorkBuddy 托管 Python，推荐）
"C:/Users/<用户名>/.workbuddy/binaries/python/versions/3.13.12/python.exe" scripts/install.py

# Mac/Linux
python3 scripts/install.py

# 安装选项
python scripts/install.py --check      # 仅检测环境
python scripts/install.py --no-ffmpeg  # 跳过 ffmpeg 下载
python scripts/install.py --no-mirror  # 使用官方 PyPI
```

安装脚本会自动处理：
- ✅ Python 虚拟环境（优先复用 WorkBuddy 托管 venv）
- ✅ 全部 pip 依赖（openai-whisper, torch, openai, sounddevice 等）
- ✅ ffmpeg（Windows 自动下载，Mac/Linux 提示手动安装）
- ✅ 生成 `scripts/env.json` 记录环境路径

**判断是否已安装**：检查 `scripts/env.json` 是否存在。存在则使用其中 `venv_python` 路径运行脚本。

**手动安装（替代方案）**：

```bash
# 不使用 install.py，手动安装
cd <技能目录>/scripts
python -m venv venv
# Windows
venv\Scripts\pip install -r requirements.txt
# Mac/Linux
venv/bin/pip install -r requirements.txt
# 依赖: openai, dashscope, openai-whisper, sounddevice, soundfile
# 还需安装 ffmpeg: https://ffmpeg.org/download.html
```

### 环境配置

```bash
# 申请 API Key
# DeepSeek: https://platform.deepseek.com/ (新用户送500万Token)
# 通义千问: https://dashscope.console.aliyun.com/

# 配置环境变量
export DEEPSEEK_API_KEY="sk-你的key"
export DASHSCOPE_API_KEY="sk-你的key"
```

### 使用方式

```bash
# Demo模式（零配置体验）
python meeting_minutes.py --demo

# 本地 Whisper 转写 + DeepSeek 总结（免费+便宜）
python meeting_minutes.py --audio meeting.mp3 --stt whisper --llm deepseek

# 通义听悟 API + 通义千问（高质量）
python meeting_minutes.py --audio meeting.mp3 --stt dashscope --llm qwen

# 直接传入文字稿
python meeting_minutes.py --transcript transcript.txt --llm deepseek

# 指定输出文件
python meeting_minutes.py --demo --output 我的会议纪要.md
```

### Whisper 模型选择

| 模型 | 大小 | 速度 | 准确率 | 显存 | 适用 |
|------|------|------|--------|------|------|
| tiny | 39MB | 最快 | 一般 | 1GB | 快速测试 |
| base | 74MB | 快 | 还行 | 1GB | **推荐入门** |
| small | 244MB | 中等 | 不错 | 2GB | 日常使用 |
| medium | 769MB | 较慢 | 好 | 5GB | 高质量 |
| large | 1550MB | 慢 | 最好 | 10GB | 极致准确 |

### 费用估算（1小时会议）

| 方案 | 转写 | 总结 | 合计 |
|------|------|------|------|
| Whisper本地 + DeepSeek | ¥0 | ¥0.05-0.2 | **¥0.05-0.2** |
| 通义听悟 + 通义千问 | ¥1.4 | ¥0.3 | **¥1.7** |

### 输出格式

脚本输出 Markdown 文件，结构：
1. 会议信息表（技术栈/耗时/费用）
2. 议题与结论
3. 待办事项表
4. 其他备注
5. 完整转写文本（附末尾核对用）

---

## 方案选择决策

```
有本地音频文件？
  ├─ 飞书连接器已启用？ → 方案1：飞书妙记上传（质量更高）
  └─ 飞书不可用？
      ├─ 有 Python + ffmpeg 环境？ → 方案2：Python 脚本
      └─ 无环境 → 引导用户安装，或手动用通义听悟网页版
```
