"""FFmpeg transcoding & thumbnail generation."""
import asyncio
import json
import os
import re
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
    """Returns {duration, width, height, subtitle_streams} via ffprobe.

    `subtitle_streams` is a list of dicts describing each embedded subtitle
    track found in the container (typically populated only for .mkv files):
        {
            "index": <stream index, e.g. 2>,
            "codec_name": "subrip" | "ass" | "mov_text" | "webvtt" | ...,
            "language": <ISO 639-1/2 code, "und" or ""=unknown>,
            "title": <free-form title from the file, may be empty>,
        }
    """
    proc = await asyncio.create_subprocess_exec(
        "ffprobe",
        "-v", "error",
        "-show_entries", "stream=index,codec_type,codec_name:stream_tags=language,title:format=duration",
        "-of", "json",
        path,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, _ = await proc.communicate()
    try:
        info = json.loads(stdout.decode())
        streams = info.get("streams", [])
        fmt = info.get("format", {})
        # Pick the FIRST video stream for width/height
        video_stream: Dict = next(
            (s for s in streams if s.get("codec_type") == "video"), {}
        )
        # We had to add codec_type to the projection but `stream=width,height`
        # was the original selector — re-query for it cheaply now.
        if not video_stream.get("width"):
            proc2 = await asyncio.create_subprocess_exec(
                "ffprobe",
                "-v", "error",
                "-select_streams", "v:0",
                "-show_entries", "stream=width,height",
                "-of", "json",
                path,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            out2, _ = await proc2.communicate()
            try:
                video_stream = json.loads(out2.decode()).get("streams", [{}])[0]
            except Exception:
                video_stream = {}
        sub_streams: List[Dict] = []
        for s in streams:
            if s.get("codec_type") != "subtitle":
                continue
            tags = s.get("tags") or {}
            sub_streams.append({
                "index": int(s.get("index", 0)),
                "codec_name": s.get("codec_name") or "",
                "language": (tags.get("language") or "").strip().lower(),
                "title": (tags.get("title") or "").strip(),
            })
        return {
            "width": int(video_stream.get("width", 0) or 0),
            "height": int(video_stream.get("height", 0) or 0),
            "duration": float(fmt.get("duration", 0) or 0),
            "subtitle_streams": sub_streams,
        }
    except Exception:
        return {"width": 0, "height": 0, "duration": 0.0, "subtitle_streams": []}


# Map ffmpeg subtitle codec names to (output extension, whether it needs SRT→VTT conversion).
# Bitmap codecs (PGS / VobSub / DVB) cannot be converted to WebVTT — they need OCR.
_TEXT_SUB_CODECS = {"subrip", "srt", "ass", "ssa", "webvtt", "mov_text"}


async def extract_embedded_subtitles(
    src_path: str, out_dir: str, video_id: str,
) -> List[Dict]:
    """Extract every TEXT subtitle stream from `src_path` and convert it to
    WebVTT.  Returns a list of dicts the caller can persist directly to
    `Video.subtitles`:
        {
            "rel_path": "<out_dir-relative>",  # e.g. "subtitles/<video>_track2.vtt"
            "language": "ro" | "ja" | ... | "",
            "label":    "Romanian" | "Japanese" | ... | "Track 2",
        }
    Bitmap subtitle streams (PGS / DVD / DVB) are SKIPPED because WebVTT only
    supports plain text — the player can't render image-based subs anyway.
    """
    info = await probe_video(src_path)
    out: List[Dict] = []
    Path(out_dir).mkdir(parents=True, exist_ok=True)
    for s in info.get("subtitle_streams", []):
        codec = (s.get("codec_name") or "").lower()
        if codec not in _TEXT_SUB_CODECS:
            continue  # skip bitmap subs (would need OCR)
        idx = int(s.get("index", 0))
        lang = (s.get("language") or "").strip().lower() or "und"
        # Use the embedded title if present, otherwise a language-based label.
        label = s.get("title") or _LANG_LABELS.get(lang, lang.upper() if lang != "und" else f"Track {idx}")
        safe_lang = re.sub(r"[^a-z0-9]+", "", lang) or "und"
        out_name = f"{video_id}_emb_{idx}_{safe_lang}.vtt"
        out_path = Path(out_dir) / out_name
        # Stream-copy to VTT — ffmpeg knows how to convert any text-based
        # subtitle format (srt, ass, mov_text, etc.) to WebVTT.
        proc = await asyncio.create_subprocess_exec(
            "ffmpeg",
            "-y",
            "-i", src_path,
            "-map", f"0:{idx}",
            "-c:s", "webvtt",
            str(out_path),
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.PIPE,
        )
        await proc.communicate()
        if proc.returncode != 0 or not out_path.exists() or out_path.stat().st_size == 0:
            # Some odd ASS files need explicit text codec fallback
            try:
                if out_path.exists():
                    out_path.unlink()
            except Exception:
                pass
            continue
        out.append({
            "rel_path": str(out_path),
            "language": lang if lang != "und" else "",
            "label": label,
        })
    return out


# ISO 639-1/2 → human label.  Kept minimal — covers the common cases the
# auto-extractor will produce; unknown codes fall back to UPPERCASE.
_LANG_LABELS: Dict[str, str] = {
    "en": "English",
    "ro": "Romanian",
    "ja": "Japanese",
    "jpn": "Japanese",
    "zh": "Chinese",
    "ko": "Korean",
    "es": "Spanish",
    "fr": "French",
    "de": "German",
    "it": "Italian",
    "pt": "Portuguese",
    "ru": "Russian",
    "ar": "Arabic",
    "hi": "Hindi",
    "tr": "Turkish",
    "pl": "Polish",
    "nl": "Dutch",
    "sv": "Swedish",
    "no": "Norwegian",
    "fi": "Finnish",
    "da": "Danish",
    "hu": "Hungarian",
    "cs": "Czech",
    "el": "Greek",
}


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
