# -*- coding: utf-8 -*-
"""视频画面文字 OCR 流水线：ffmpeg 抽帧 + RapidOCR + phash 去重 + Markdown 报告。"""

from __future__ import annotations

import hashlib
import os
import re
import shutil
import subprocess
import tempfile
from collections import Counter
from pathlib import Path
from typing import Callable, Optional

from PIL import Image
import imagehash
import numpy as np

ProgressCallback = Optional[Callable[[float, str], None]]

# 浏览器 / UI 噪声行（保守过滤）
_UI_NOISE_PATTERNS = [
    re.compile(r"https?://", re.I),
    re.compile(r"www\.", re.I),
    re.compile(r"书签"),
    re.compile(r"收藏夹"),
    re.compile(r"新标签页"),
    re.compile(r"历史记录"),
    re.compile(r"下载内容"),
    re.compile(r"扩展程序"),
    re.compile(r"隐私设置"),
    re.compile(r"Cookie", re.I),
    re.compile(r"Chrome", re.I),
    re.compile(r"Microsoft Edge", re.I),
    re.compile(r"Firefox", re.I),
    re.compile(r"Safari", re.I),
    re.compile(r"地址栏"),
    re.compile(r"搜索或输入网址"),
    re.compile(r"Reload this page", re.I),
    re.compile(r"View page source", re.I),
    re.compile(r"^File$", re.I),
    re.compile(r"^Edit$", re.I),
    re.compile(r"^View$", re.I),
    re.compile(r"^Help$", re.I),
]


def _progress(cb: ProgressCallback, frac: float, msg: str) -> None:
    if cb:
        try:
            cb(max(0.0, min(1.0, frac)), msg)
        except Exception:
            pass


def _ensure_ffmpeg() -> None:
    for tool in ("ffmpeg", "ffprobe"):
        if shutil.which(tool) is None:
            raise RuntimeError(
                "未检测到 ffmpeg/ffprobe。请先安装 ffmpeg 并加入系统 PATH 后重试。\n"
                "Windows 可用：winget install ffmpeg\n"
                "或从 https://www.gyan.dev/ffmpeg/builds/ 下载并配置 PATH。"
            )


def probe_duration(video_path: str) -> float:
    """用 ffprobe 获取视频时长（秒）。"""
    _ensure_ffmpeg()
    path_for_probe = video_path
    tmp_dir = None
    try:
        if any(ord(ch) > 127 for ch in video_path):
            tmp_dir = Path(tempfile.mkdtemp(prefix="video_ocr_probe_"))
            path_for_probe = _ascii_video_copy(video_path, tmp_dir)
        cmd = [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            path_for_probe,
        ]
        out = subprocess.check_output(cmd, stderr=subprocess.STDOUT, text=True).strip()
        return float(out)
    except (subprocess.CalledProcessError, ValueError) as e:
        raise RuntimeError(f"无法读取视频时长，请确认文件完整且为常见视频格式。详情：{e}") from e
    finally:
        if tmp_dir is not None:
            shutil.rmtree(tmp_dir, ignore_errors=True)


def _run_ffmpeg(cmd: list[str]) -> None:
    """Run ffmpeg list-cmd; raise RuntimeError with stderr on failure."""
    try:
        proc = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
    except FileNotFoundError as e:
        raise RuntimeError(
            "未找到 ffmpeg。请安装并加入 PATH 后，新开终端再试。\n"
            "可用：winget install Gyan.FFmpeg\n"
            "装好后在命令行执行 ffmpeg -version 应能显示版本。"
        ) from e
    if proc.returncode != 0:
        err = (proc.stderr or b"").decode("utf-8", errors="replace")
        err = err[-1500:] if len(err) > 1500 else err
        raise RuntimeError(
            "ffmpeg 抽帧失败。请确认已安装可用的 ffmpeg（建议用 winget 安装官方包，"
            "避免损坏的 Anaconda 自带 ffmpeg）。\n"
            f"退出码：{proc.returncode}\n"
            f"详情：\n{err}"
        )


def _ascii_video_copy(video_path: str, work_dir: Path) -> str:
    """Copy to ASCII-only temp name to avoid Windows path encoding issues."""
    src = Path(video_path)
    suffix = src.suffix.lower() or ".mp4"
    if not suffix.startswith("."):
        suffix = "." + suffix
    dst = work_dir / f"input_video{suffix}"
    shutil.copy2(src, dst)
    return str(dst)


def _auto_fps(duration: float, fps: float | None = None) -> float:
    """fps>0 用用户设置；否则自动：短视频(<180s) 2 帧/秒，长视频 0.2 帧/秒。"""
    if fps and fps > 0:
        return float(fps)
    return 2.0 if duration < 180 else 0.2


def _extract_frames_opencv(video_path: str, frames_dir: Path, duration: float, fps_set: float | None = None) -> list[tuple[Path, float]]:
    """Fallback frame extraction via OpenCV when ffmpeg fails."""
    try:
        import cv2
    except Exception as e:
        raise RuntimeError(f"OpenCV 不可用，无法作为抽帧备用方案。详情：{e}") from e

    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        raise RuntimeError("OpenCV 无法打开该视频文件。")

    fps = float(cap.get(cv2.CAP_PROP_FPS) or 0) or 25.0
    interval = 1.0 / _auto_fps(duration, fps_set)
    step = max(int(round(fps * interval)), 1)
    out: list[tuple[Path, float]] = []
    idx = 0
    saved = 0
    while True:
        ok, frame = cap.read()
        if not ok:
            break
        if idx % step == 0:
            ts = idx / fps
            path = frames_dir / f"cv_{saved:06d}.png"
            # BGR -> RGB write via cv2
            if not cv2.imwrite(str(path), frame):
                idx += 1
                continue
            out.append((path, ts))
            saved += 1
        idx += 1
    cap.release()
    if not out:
        raise RuntimeError("OpenCV 抽帧结果为空。")
    return out


def extract_frames(video_path: str, frames_dir: Path, duration: float, fps_set: float | None = None) -> list[tuple[Path, float]]:
    """抽帧到 frames_dir。fps_set>0 按设置；否则自动。返回 [(png_path, timestamp_sec), ...]"""
    frames_dir.mkdir(parents=True, exist_ok=True)
    for old in frames_dir.glob("*.png"):
        old.unlink()

    safe_video = _ascii_video_copy(video_path, frames_dir.parent)
    ffmpeg_error = None
    rate = _auto_fps(duration, fps_set)

    try:
        pattern = str(frames_dir / "frame_%06d.png")
        cmd = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
               "-i", safe_video, "-vf", f"fps={rate:g}", pattern]
        _run_ffmpeg(cmd)
        files = sorted(frames_dir.glob("frame_*.png"))
        if not files:
            raise RuntimeError("抽帧结果为空：视频可能无有效画面，或 ffmpeg 无法解码该文件。")
        return [(f, i / rate) for i, f in enumerate(files)]
    except Exception as e:
        ffmpeg_error = e
        for old in frames_dir.glob("*.png"):
            old.unlink()
        try:
            return _extract_frames_opencv(safe_video, frames_dir, duration, fps_set)
        except Exception as e2:
            raise RuntimeError(
                "抽帧失败：ffmpeg 与 OpenCV 备用方案都未成功。\n"
                f"ffmpeg 错误：{ffmpeg_error}\n"
                f"OpenCV 错误：{e2}\n"
                "请在新的命令行执行 ffmpeg -version；若异常，请运行：winget install Gyan.FFmpeg"
            ) from e2



def dedupe_frames(
    frames: list[tuple[Path, float]], threshold: int = 4
) -> list[tuple[Path, float]]:
    """用 perceptual hash 去掉近乎相同的帧。"""
    if not frames:
        return []
    kept: list[tuple[Path, float]] = []
    hashes: list[imagehash.ImageHash] = []
    for path, ts in frames:
        try:
            with Image.open(path) as im:
                h = imagehash.phash(im)
        except Exception:
            continue
        is_dup = False
        for prev in hashes:
            if abs(h - prev) <= threshold:
                is_dup = True
                break
        if not is_dup:
            kept.append((path, ts))
            hashes.append(h)
    return kept


def _is_ui_noise(line: str) -> bool:
    s = line.strip()
    if not s:
        return True
    if len(s) <= 1:
        return True
    for pat in _UI_NOISE_PATTERNS:
        if pat.search(s):
            return True
    return False


_ocr_engine = None


MODEL_DIR = Path(__file__).resolve().parent / "models"
V5_REC = MODEL_DIR / "ch_PP-OCRv5_rec_server_infer.onnx"
V5_DICT = MODEL_DIR / "ppocrv5_dict.txt"
V5_URLS = [
    "https://www.modelscope.cn/models/RapidAI/RapidOCR/resolve/v3.4.0/onnx/PP-OCRv5/rec/ch_PP-OCRv5_rec_server_infer.onnx",
]


def _ensure_v5_model() -> bool:
    """确保高精度 PP-OCRv5 识别模型存在（首次自动下载约 81MB）。"""
    if V5_REC.exists() and V5_REC.stat().st_size > 50_000_000 and V5_DICT.exists():
        return True
    import urllib.request
    MODEL_DIR.mkdir(exist_ok=True)
    tmp = V5_REC.with_suffix(".part")
    for url in V5_URLS:
        try:
            print("下载高精度识别模型（约 81MB，仅首次）…", flush=True)
            urllib.request.urlretrieve(url, tmp)
            if tmp.stat().st_size > 50_000_000:
                tmp.replace(V5_REC)
                return V5_DICT.exists()
        except Exception as e:
            print(f"模型下载失败：{e}", flush=True)
    return False


def _get_ocr():
    global _ocr_engine
    if _ocr_engine is None:
        try:
            from rapidocr_onnxruntime import RapidOCR
        except Exception as e:
            # ImportError / OSError both possible for DLL init failures on Windows.
            raise RuntimeError(
                "无法加载 OCR 引擎（rapidocr_onnxruntime / onnxruntime）。"
                "请用 启动.bat / start.bat 完成依赖安装与诊断（Python 3.10–3.12）。"
                "若错误含 DLL / onnxruntime_pybind11_state：请安装官方 Microsoft VC++ x64 运行库后重试；"
                "本程序不会自动安装该运行库。"
                "仍失败时可能是本机 CPU/系统不被当前 onnxruntime 支持，需以本机 diagnose_last.txt 为准。"
                f" 原始错误：{e}"
            ) from e
        try:
            if _ensure_v5_model():
                _ocr_engine = RapidOCR(rec_model_path=str(V5_REC), rec_keys_path=str(V5_DICT))
            else:
                print("[提示] 高精度模型不可用，改用默认轻量模型。", flush=True)
                _ocr_engine = RapidOCR()
        except Exception as e:
            raise RuntimeError(f"初始化 OCR 引擎失败：{e}") from e
    return _ocr_engine


def ocr_frame(path: Path, conf_threshold: float = 0.5) -> list[str]:
    """对单帧 OCR，返回过滤后的文本行。"""
    engine = _get_ocr()
    result, _ = engine(str(path))
    lines: list[str] = []
    if not result:
        return lines
    for item in result:
        # item: [box, text, score]
        if len(item) < 3:
            continue
        text = str(item[1]).strip()
        try:
            score = float(item[2])
        except (TypeError, ValueError):
            score = 0.0
        if score < conf_threshold:
            continue
        if _is_ui_noise(text):
            continue
        lines.append(text)
    return lines


def _normalize_for_overlap(text: str) -> set[str]:
    # 按字符/短词粗分，便于中英混合重叠比较
    chars = re.findall(r"[\u4e00-\u9fff]|[A-Za-z0-9]{2,}", text.lower())
    return set(chars)


def _overlap_ratio(a: str, b: str) -> float:
    sa, sb = _normalize_for_overlap(a), _normalize_for_overlap(b)
    if not sa or not sb:
        # 短文本直接比字符串
        if not a or not b:
            return 0.0
        shorter, longer = (a, b) if len(a) <= len(b) else (b, a)
        if shorter in longer:
            return 1.0
        return 0.0
    inter = len(sa & sb)
    return inter / max(min(len(sa), len(sb)), 1)


def _norm_line(t: str) -> str:
    return re.sub(r"[\s\W_]+", "", t).lower()


def merge_consecutive(
    items: list[tuple[float, list[str], Path]], overlap_thresh: float = 0.7
) -> list[dict]:
    """按文字行去重：每行只保留第一次出现，后面重复（含 OCR 小误差）跳过。"""
    import difflib

    seen: list[str] = []
    sections: list[dict] = []
    for ts, lines, path in items:
        fresh: list[str] = []
        for ln in lines:
            n = _norm_line(ln)
            if len(n) < 2:
                continue
            dup = False
            for old in seen[-300:]:
                if n == old or (len(n) >= 4 and (n in old)):
                    dup = True
                    break
                if abs(len(n) - len(old)) <= max(3, len(n) // 4) and \
                        difflib.SequenceMatcher(None, n, old).ratio() >= 0.85:
                    dup = True
                    break
            if not dup:
                seen.append(n)
                fresh.append(ln)
        if not fresh:
            if sections:
                sections[-1]["end"] = ts
            continue
        sections.append({"start": ts, "end": ts, "text": "\n".join(fresh),
                         "frame": path, "count": 1})
    return sections


def _fmt_ts(sec: float) -> str:
    sec = max(0, int(sec))
    h, rem = divmod(sec, 3600)
    m, s = divmod(rem, 60)
    if h:
        return f"{h:02d}:{m:02d}:{s:02d}"
    return f"{m:02d}:{s:02d}"


def _looks_paywall(text: str) -> bool:
    keys = [
        "付费",
        "会员",
        "订阅",
        "解锁",
        "开通",
        "试读",
        "剩余",
        "登录后",
        "paywall",
        "subscribe",
        "premium",
        "会员专享",
        "继续阅读",
    ]
    t = text.lower()
    return any(k.lower() in t for k in keys)


def select_keyframes(sections: list[dict], max_n: int = 5) -> list[dict]:
    """选 3–5 张关键帧：开头、中段、疑似付费墙、结尾。"""
    if not sections:
        return []
    n = len(sections)
    picks: list[dict] = []
    indices = set()

    # 开头
    indices.add(0)
    # 结尾
    if n > 1:
        indices.add(n - 1)
    # 中段
    if n >= 3:
        indices.add(n // 2)
        if n >= 5:
            indices.add(n // 4)
            indices.add((3 * n) // 4)

    # 付费墙优先
    for i, sec in enumerate(sections):
        if _looks_paywall(sec["text"]):
            indices.add(i)

    ordered = sorted(indices)
    # 限制数量：优先保留头、尾、付费、中
    if len(ordered) > max_n:
        priority = []
        # 头尾
        priority.extend([ordered[0], ordered[-1]])
        pay = [i for i in ordered if _looks_paywall(sections[i]["text"])]
        priority.extend(pay)
        mid = [i for i in ordered if i not in priority]
        for i in mid:
            priority.append(i)
        # 去重保序
        seen = set()
        final = []
        for i in priority:
            if i not in seen:
                seen.add(i)
                final.append(i)
            if len(final) >= max_n:
                break
        ordered = sorted(final)

    # 至少 3 张（若有足够 section）
    if len(ordered) < 3 and n >= 3:
        for i in [0, n // 2, n - 1]:
            if i not in ordered:
                ordered.append(i)
        ordered = sorted(set(ordered))[:max_n]

    for i in ordered:
        picks.append(sections[i])
    return picks[:max_n]


def write_report(
    out_dir: Path,
    video_path: str,
    duration: float,
    sections: list[dict],
    keyframes: list[dict],
) -> Path:
    """写 report.md（中文标题）并复制关键帧。"""
    out_dir.mkdir(parents=True, exist_ok=True)
    kf_dir = out_dir / "keyframes"
    kf_dir.mkdir(exist_ok=True)
    # 清空旧关键帧
    for p in kf_dir.glob("*"):
        if p.is_file():
            p.unlink()

    kf_names = []
    for idx, sec in enumerate(keyframes, 1):
        src: Path = sec["frame"]
        name = f"keyframe_{idx:02d}_{_fmt_ts(sec['start']).replace(':', '-')}.png"
        dst = kf_dir / name
        try:
            shutil.copy2(src, dst)
            kf_names.append((name, sec))
        except Exception:
            continue

    lines = []
    lines.append("# 视频文字识别报告")
    lines.append("")
    lines.append("## 基本信息")
    lines.append("")
    lines.append(f"- **视频文件**：`{Path(video_path).name}`")
    lines.append(f"- **时长**：{_fmt_ts(duration)}（约 {duration:.1f} 秒）")
    lines.append(f"- **文本段落数**：{len(sections)}")
    lines.append(f"- **关键帧数**：{len(kf_names)}")
    lines.append("")
    lines.append("## 关键帧")
    lines.append("")
    if not kf_names:
        lines.append("（无）")
    else:
        for name, sec in kf_names:
            lines.append(f"- `{name}` — 约 {_fmt_ts(sec['start'])}")
            preview = sec["text"].replace("\n", " ")[:80]
            lines.append(f"  - 预览：{preview}{'…' if len(sec['text']) > 80 else ''}")
        lines.append("")
        for name, _ in kf_names:
            lines.append(f"![关键帧](keyframes/{name})")
            lines.append("")
    lines.append("## 按时间线整理的文字")
    lines.append("")
    if not sections:
        lines.append("未识别到有效文字。可尝试分辨率更高或字幕更清晰的视频。")
    else:
        for i, sec in enumerate(sections, 1):
            t0, t1 = _fmt_ts(sec["start"]), _fmt_ts(sec["end"])
            if sec["start"] == sec["end"]:
                head = f"### {i}. [{t0}]"
            else:
                head = f"### {i}. [{t0} – {t1}]"
            lines.append(head)
            lines.append("")
            lines.append(sec["text"])
            lines.append("")

    lines.append("---")
    lines.append("")
    lines.append("*由本地「视频文字识别」工具生成。*")
    lines.append("")

    report_path = out_dir / "report.md"
    report_path.write_text("\n".join(lines), encoding="utf-8")
    return report_path


def run_ocr(
    video_path: str,
    out_dir: str,
    progress_callback: ProgressCallback = None,
    fps: float | None = None,
) -> dict:
    """
    主入口：抽帧 → 去重 → OCR → 合并 → 报告。
    返回 dict：report_path, keyframes_dir, summary, sections_count, ...
    """
    video_path = str(Path(video_path).resolve())
    if not os.path.isfile(video_path):
        raise FileNotFoundError(f"找不到视频文件：{video_path}")

    out = Path(out_dir).resolve()
    out.mkdir(parents=True, exist_ok=True)
    work = out / "_work_frames"
    work.mkdir(exist_ok=True)

    _progress(progress_callback, 0.02, "检查 ffmpeg…")
    _ensure_ffmpeg()

    _progress(progress_callback, 0.05, "读取视频时长…")
    duration = probe_duration(video_path)

    _progress(progress_callback, 0.1, "提取视频帧…")
    try:
        frames = extract_frames(video_path, work, duration, fps)
    except subprocess.CalledProcessError as e:
        raise RuntimeError(f"抽帧失败，请确认视频可读且已安装 ffmpeg。详情：{e}") from e

    if not frames:
        raise RuntimeError("未能从视频中提取到任何帧，请换一个视频文件重试。")

    _progress(progress_callback, 0.25, f"已提取 {len(frames)} 帧，正在去重…")
    frames = dedupe_frames(frames, threshold=4)
    _progress(progress_callback, 0.35, f"去重后剩余 {len(frames)} 帧，开始 OCR…")

    # 提前初始化 OCR，避免装错依赖后空跑一整遍
    _progress(progress_callback, 0.36, "加载 OCR 模型（首次会下载）…")
    _get_ocr()

    ocr_items: list[tuple[float, list[str], Path]] = []
    total = max(len(frames), 1)
    for i, (path, ts) in enumerate(frames):
        frac = 0.35 + 0.50 * (i / total)
        _progress(progress_callback, frac, f"OCR 识别中 ({i + 1}/{total})…")
        try:
            lines = ocr_frame(path, conf_threshold=0.5)
        except Exception as e:
            # 单帧失败不中断
            lines = []
            _progress(progress_callback, frac, f"第 {i + 1} 帧识别失败，已跳过：{e}")
        ocr_items.append((ts, lines, path))

    _progress(progress_callback, 0.88, "合并相近文本并生成报告…")
    sections = merge_consecutive(ocr_items, overlap_thresh=0.7)
    keyframes = select_keyframes(sections, max_n=5)
    report_path = write_report(out, video_path, duration, sections, keyframes)
    fulltext_path = out / "fulltext.md"
    fulltext_path.write_text(
        "# 全文合并\n\n" + "\n".join(s["text"] for s in sections) + "\n",
        encoding="utf-8",
    )

    # 清理工作帧（保留输出目录中的 keyframes 与 report）
    try:
        shutil.rmtree(work, ignore_errors=True)
    except Exception:
        pass

    text_chars = sum(len(s["text"]) for s in sections)
    summary = (
        f"完成：时长 {_fmt_ts(duration)}，有效段落 {len(sections)} 段，"
        f"约 {text_chars} 字，关键帧 {len(keyframes)} 张。报告已保存。"
    )
    _progress(progress_callback, 1.0, summary)

    return {
        "report_path": str(report_path),
        "fulltext_path": str(fulltext_path),
        "keyframes_dir": str(out / "keyframes"),
        "out_dir": str(out),
        "summary": summary,
        "sections_count": len(sections),
        "duration": duration,
        "keyframes": [str(out / "keyframes" / p.name) for p in (out / "keyframes").glob("*.png")],
    }


if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("用法: python ocr_pipeline.py <视频路径> [输出目录]")
        sys.exit(1)
    vp = sys.argv[1]
    od = sys.argv[2] if len(sys.argv) > 2 else str(Path(vp).with_suffix("")) + "_ocr_out"
    def _cb(f, m):
        print(f"[{f:.0%}] {m}")
    r = run_ocr(vp, od, _cb)
    print(r["summary"])
    print(r["report_path"])
