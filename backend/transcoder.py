"""FFmpeg transcoding & thumbnail generation."""
import asyncio
import json
import os
from pathlib import Path
from typing import Dict, List, Optional, Tuple

RESOLUTIONS: Dict[str, Tuple[int, int]] = {
    "360p": (640, 360),
    "720p": (1280, 720),
    "1080p": (1920, 1080),
    "2048p": (2048, 1152),  # approx 2k
    "4096p": (4096, 2160),  # 4k UHD
}


async def probe_video(path: str) -> Dict:
    """Returns {duration, width, height} via ffprobe."""
    proc = await asyncio.create_subprocess_exec(
        "ffprobe",
        "-v", "error",
        "-select_streams", "v:0",
        "-show_entries", "stream=width,height:format=duration",
        "-of", "json",
        path,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, _ = await proc.communicate()
    try:
        info = json.loads(stdout.decode())
        stream = info.get("streams", [{}])[0]
        fmt = info.get("format", {})
        return {
            "width": int(stream.get("width", 0) or 0),
            "height": int(stream.get("height", 0) or 0),
            "duration": float(fmt.get("duration", 0) or 0),
        }
    except Exception:
        return {"width": 0, "height": 0, "duration": 0.0}


async def generate_thumbnails(
    video_path: str, out_dir: str, video_id: str, duration_sec: float, count: int = 10
) -> List[str]:
    """Generates `count` thumbnails evenly across the video."""
    Path(out_dir).mkdir(parents=True, exist_ok=True)
    paths: List[str] = []
    if duration_sec <= 0:
        duration_sec = 10.0
    for i in range(count):
        # take frames at fraction i/(count+1) skipping first and last edges
        t = duration_sec * (i + 1) / (count + 1)
        out = os.path.join(out_dir, f"{video_id}_thumb_{i}.jpg")
        proc = await asyncio.create_subprocess_exec(
            "ffmpeg",
            "-y",
            "-ss", f"{t:.2f}",
            "-i", video_path,
            "-frames:v", "1",
            "-vf", "scale=640:-2",
            "-q:v", "3",
            out,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
        )
        await proc.wait()
        if os.path.exists(out):
            paths.append(out)
    return paths


async def transcode_to_resolution(
    input_path: str,
    output_path: str,
    target_resolution: str,
) -> bool:
    """Transcodes input video to a specific resolution in mp4 (H.264 + AAC).
    Returns True on success."""
    if target_resolution not in RESOLUTIONS:
        return False
    w, h = RESOLUTIONS[target_resolution]
    # scale keeping aspect with -2 then pad? simplest: scale width to w, height adjusted to even
    vf = f"scale='if(gt(a,{w}/{h}),{w},-2)':'if(gt(a,{w}/{h}),-2,{h})'"
    Path(os.path.dirname(output_path)).mkdir(parents=True, exist_ok=True)
    proc = await asyncio.create_subprocess_exec(
        "ffmpeg",
        "-y",
        "-i", input_path,
        "-vf", vf,
        "-c:v", "libx264",
        "-preset", "veryfast",
        "-crf", "23",
        "-c:a", "aac",
        "-b:a", "128k",
        "-movflags", "+faststart",
        output_path,
        stdout=asyncio.subprocess.DEVNULL,
        stderr=asyncio.subprocess.PIPE,
    )
    _, err = await proc.communicate()
    return proc.returncode == 0 and os.path.exists(output_path)


def filter_resolutions_for_source(
    source_height: int, enabled: List[str]
) -> List[str]:
    """Only keep enabled resolutions that are <= source height (plus the closest higher)."""
    out: List[str] = []
    for r in enabled:
        if r not in RESOLUTIONS:
            continue
        _, h = RESOLUTIONS[r]
        if h <= source_height + 50:  # small tolerance
            out.append(r)
    if not out and enabled:
        # ensure at least one (the lowest enabled)
        sorted_enabled = sorted(
            [r for r in enabled if r in RESOLUTIONS],
            key=lambda r: RESOLUTIONS[r][1],
        )
        if sorted_enabled:
            out = [sorted_enabled[0]]
    return out
