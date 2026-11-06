# -*- coding: utf-8 -*-
"""视频文字识别 — Gradio 简易网页界面。"""

from __future__ import annotations

import shutil
import tempfile
import zipfile
from pathlib import Path

import gradio as gr

from ocr_pipeline import run_ocr


def _zip_keyframes(keyframes_dir: str, zip_path: Path) -> str | None:
    kd = Path(keyframes_dir)
    if not kd.is_dir():
        return None
    files = sorted(kd.glob("*.png"))
    if not files:
        return None
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for f in files:
            zf.write(f, arcname=f.name)
    return str(zip_path)


def process_video(video_file, progress=gr.Progress(track_tqdm=False)):
    if video_file is None:
        return "请先上传视频文件。", "", None, None

    # Gradio 可能返回路径字符串或临时文件对象
    if isinstance(video_file, dict) and "name" in video_file:
        video_path = video_file["name"]
    else:
        video_path = str(video_file)

    if not Path(video_path).is_file():
        return f"找不到上传的视频：{video_path}", "", None, None

    out_root = Path(tempfile.mkdtemp(prefix="video_ocr_"))
    out_dir = out_root / "output"

    def cb(frac, msg):
        try:
            progress(frac, desc=msg)
        except Exception:
            pass

    try:
        result = run_ocr(video_path, str(out_dir), progress_callback=cb)
    except Exception as e:
        return f"识别失败：{e}", "", None, None

    report_path = result["report_path"]
    try:
        md = Path(report_path).read_text(encoding="utf-8")
    except Exception:
        md = result.get("summary", "")

    zip_path = out_root / "keyframes.zip"
    zipped = _zip_keyframes(result["keyframes_dir"], zip_path)

    status = result["summary"] + f"\n输出目录：{result['out_dir']}"
    return status, md, report_path, zipped


CSS = """
.gradio-container { max-width: 960px !important; }
"""

with gr.Blocks(title="视频文字识别") as demo:
    gr.Markdown("# 视频文字识别")
    gr.Markdown(
        "上传本地视频，自动抽帧并用中英文 OCR 提取画面文字，"
        "去重后导出 Markdown 报告与关键帧图片。\n\n"
        "> **提示**：首次运行会下载 OCR 模型，请耐心等待。需要本机已安装 **ffmpeg** 并加入 PATH。"
    )

    with gr.Row():
        video_in = gr.Video(label="上传视频", sources=["upload"])

    start_btn = gr.Button("开始识别", variant="primary")

    status_out = gr.Textbox(label="进度 / 结果", lines=3, interactive=False)
    md_out = gr.Markdown(label="报告预览")

    with gr.Row():
        report_file = gr.File(label="下载 report.md")
        kf_zip = gr.File(label="下载关键帧 ZIP")

    start_btn.click(
        fn=process_video,
        inputs=[video_in],
        outputs=[status_out, md_out, report_file, kf_zip],
    )

if __name__ == "__main__":
    print("正在启动：http://127.0.0.1:7860")
    launch_kwargs = dict(
        server_name="127.0.0.1",
        server_port=7860,
        share=False,
        inbrowser=True,
    )
    # Gradio 4: css on Blocks; Gradio 5+/6: css on launch
    try:
        demo.queue().launch(**launch_kwargs, css=CSS)
    except TypeError:
        demo.queue().launch(**launch_kwargs)
