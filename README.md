# 视频文字识别（Windows 本地版）

在本地电脑上对视频画面做中英文 OCR：上传视频 → 抽帧 → 识别文字 → 去重整理 → 导出 Markdown 报告与关键帧。

界面为浏览器中的简易网页（Gradio），数据默认不出本机。

## 环境要求

1. **Python 3.10–3.12（推荐）**  
   - 官网：https://www.python.org/downloads/  
   - 安装时勾选 **Add python.exe to PATH**  
   - 说明：请优先选 3.10 / 3.11 / 3.12。`rapidocr_onnxruntime` 对 3.13 支持尚不完整。

2. **ffmpeg**（抽帧必需）  
   - 推荐：在 PowerShell / 命令提示符执行  
     ```bat
     winget install Gyan.FFmpeg
     ```  
   - 或从 https://www.gyan.dev/ffmpeg/builds/ 下载「release full」压缩包，解压后把 `bin` 目录加入系统 PATH  
   - 安装后新开一个终端，执行 `ffmpeg -version` 能显示版本即成功

3. **Microsoft Visual C++ Redistributable（x64）**（OCR / onnxruntime 常需要）  
   - 官方说明与下载：https://learn.microsoft.com/en-us/cpp/windows/latest-supported-vc-redist  
   - 本包 **不会** 自动安装 VC++ 运行库。若诊断提示 `onnxruntime_pybind11_state` / DLL 初始化失败，请先手动安装官方 x64 再重试。  
   - 即便装好依赖，仍 **不保证** 每台电脑都能跑通：部分较旧 CPU / 系统组合不被当前 onnxruntime 轮子支持，必须以本机诊断结果为准。

4. 可选：独立显卡可加速部分依赖，但 **CPU 即可**，短视频一般够用。

## 使用步骤

1. 解压本压缩包到任意目录（路径尽量不要含特殊字符）。
2. 双击 **`启动.bat`** 或 **`start.bat`**（批处理内容为英文 ASCII，避免 Windows 中文代码页把命令拆坏）。  
   - 首次会创建 `.venv` 并按 `requirements.txt` 安装固定版本依赖，可能需要几分钟；杀毒软件可能拖慢安装。  
   - 启动前会运行 `diagnostic_environment.py`；失败则暂停并给出可操作提示（不会自动上传日志）。  
   - 首次 OCR 还会自动下载模型，请耐心等待。
3. 浏览器自动打开，或手动访问：**http://127.0.0.1:7860**
4. 上传视频 → 点击 **开始识别** → 等待进度结束 → 下载 `report.md` 与关键帧 ZIP。

## 依赖固定（与 DLL 问题相关）

本包仅使用官方 PyPI 包，并固定：

- `rapidocr_onnxruntime==1.4.4`
- `onnxruntime==1.20.1`（偏保守的 CPU 版；社区在更新版本上多次报告 Windows DLL 初始化失败，降到 1.20.1 常可恢复）
- `opencv-python`（**不用** `opencv-python-headless`，避免与 RapidOCR 依赖冲突）

每次启动会在 **本目录 `.venv` 内** 先卸载（若存在）`onnxruntime` / `onnxruntime-gpu` / `onnxruntime-directml` / `msvc-runtime` / `opencv-python-headless`，再按 `requirements.txt` 安装。这只改本工具虚拟环境，**不会**复制或删除你系统 / Anaconda 里的 DLL。

启动脚本用绝对工作目录下的 `.venv\Scripts\python.exe` 直接调用，**不依赖** `activate`。

### 启动时临时清理 PATH（仅本次进程）

若系统 PATH 里挂了 Anaconda / Miniconda / Conda 目录，旧的 VC++ / 运行库 DLL 可能抢先被加载，导致 `DLL 初始化例程失败`，即使 venv 本身是干净的。

`start.bat` / `启动.bat` 会在 **当前启动进程内** 从 PATH 去掉路径段中含 `anaconda` / `conda` / `miniconda` 的目录（大小写不敏感），其它目录（含 ffmpeg）保留。这 **不会** 修改你的用户或系统环境变量。

## 常见问题

| 问题 | 处理 |
|------|------|
| `onnxruntime_pybind11_state` / DLL 初始化失败 | 看同目录 `diagnose_last.txt`；确认已用本包 bat 安装；安装官方 VC++ x64 后再开 bat。仍失败则可能是 CPU/系统不被该 onnxruntime 支持，本包无法在远端替你保证 |
| 提示找不到 ffmpeg | 安装 ffmpeg 并确认 PATH，**新开**终端后再双击启动（PATH 清理不会删掉非 conda 的 ffmpeg） |
| 找不到 Python | 安装 3.10–3.12 并勾选加入 PATH（建议 python.org，而非仅 Anaconda） |
| 端口 7860 被占用 | 关闭占用该端口的程序，或改 `app.py` 里的 `server_port` |
| 识别结果很少 | 画面文字太小/模糊/被压缩；可换清晰度更高的源视频 |
| pip 很慢或失败 | 检查网络；可配置国内 PyPI 镜像后再运行 `启动.bat` |
| 想彻底重装依赖 | 可自行删除本目录下的 `.venv` 后重跑 bat（非必须；正常 repair 流程会重装 OCR 相关包） |

## 目录结构

```
video_ocr_windows/
  app.py                      # Gradio 界面（中文）
  ocr_pipeline.py             # 抽帧 / OCR / 去重 / 报告
  diagnostic_environment.py   # 启动前环境诊断（仅本机打印/写 diagnose_last.txt）
  check_python.py
  requirements.txt
  start.bat / 启动.bat        # ASCII 启动脚本
  README.md
```

请勿把 `.venv` 或大模型缓存打进分享包；本机首次运行会自动下载所需组件。诊断信息只写在本地 `diagnose_last.txt`，不会自动上传。

## ffmpeg 抽帧失败（常见）

若提示抽帧失败或退出码异常：

1. 新开 **命令提示符**，执行 `ffmpeg -version`、`where ffmpeg`。
2. 若版本异常、找不到，或路径落在残缺的 Anaconda 目录，请安装官方包：
   ```bat
   winget install Gyan.FFmpeg
   ```
3. 安装后 **关掉旧的启动窗口**，再双击 `start.bat`。
4. 本程序会把上传视频复制成英文临时文件名再抽帧；若仍失败，会尝试用 OpenCV 备用抽帧。

## start.bat 闪退或启动失败

请重新完整解压压缩包，不要只替换 `start.bat`。新版由 `setup_env.py` 创建和检查环境，发生错误会保留窗口。

若还不行，在这个文件夹的地址栏输入 `cmd` 并回车，然后运行 `cmd /k start.bat`，把窗口里的报错文字复制出来。
