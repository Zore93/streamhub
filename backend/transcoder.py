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


# Map ffmpeg subtitle codec names to the way they should be extracted.
# Text codecs that WebVTT mux can usually convert directly:
_TEXT_SUB_CODECS = {
    "subrip", "srt", "ass", "ssa", "webvtt", "mov_text",
    "text", "subviewer", "subviewer1", "microdvd", "jacosub",
    "stl", "tx3g", "vplayer", "realtext", "sami", "smi", "mpl2",
    "arib_caption", "eia_608", "eia_708",
    "hdmv_text_subtitle",  # rare but exists
}

# Bitmap codecs (PGS/DVB/DVD-VOBSUB) — WebVTT cannot represent these without
# OCR.  We surface their existence in the result for the admin UI so the user
# knows a track was found but couldn't be auto-extracted.
_BITMAP_SUB_CODECS = {
    "hdmv_pgs_subtitle", "pgssub", "pgs",
    "dvd_subtitle", "vobsub",
    "dvb_subtitle", "dvb_teletext",
    "kate",  # Ogg bitmap — uncommon
}


async def extract_embedded_subtitles(
    src_path: str, out_dir: str, video_id: str,
) -> List[Dict]:
    """Extract every TEXT subtitle stream from `src_path` and convert it to
    WebVTT.  Returns a list of dicts the caller can persist directly to
    ``Video.subtitles``::

        {
            "rel_path": "<absolute path to the .vtt file>",
            "language": "ro" | "ja" | ... | "",
            "label":    "Romanian" | "Japanese" | ... | "Track 2",
        }

    Three-tier extraction strategy (each stream is tried with all three until
    one succeeds — this is the key reliability win):

      Tier-1: ``-c:s webvtt`` directly — fastest path, works for srt / mov_text.
      Tier-2: extract to NATIVE first (``-c:s copy`` to .srt / .ass), then
              convert that intermediate file to WebVTT.  Recovers many ASS
              subtitles whose styles make Tier-1 choke.
      Tier-3: re-encode through ``-c:s srt`` then to WebVTT.  Strips ASS
              styling but salvages the text content.

    Bitmap codecs (PGS/DVD/DVB) are NOT extracted (they would need OCR) but
    they ARE listed in the result so the EditVideo UI can show them as
    ``source="embedded-bitmap"`` placeholders.
    """
    import logging as _log
    L = _log.getLogger("transcoder.subs")

    info = await probe_video(src_path)
    out: List[Dict] = []
    Path(out_dir).mkdir(parents=True, exist_ok=True)
    streams = info.get("subtitle_streams") or []
    L.info("extract_embedded: %s — %d subtitle stream(s) found", Path(src_path).name, len(streams))

    for s in streams:
        codec = (s.get("codec_name") or "").lower()
        idx = int(s.get("index", 0))
        lang = (s.get("language") or "").strip().lower() or "und"
        label = s.get("title") or _LANG_LABELS.get(lang, lang.upper() if lang != "und" else f"Track {idx}")
        safe_lang = re.sub(r"[^a-z0-9]+", "", lang) or "und"

        if codec in _BITMAP_SUB_CODECS:
            L.info("  - stream #%d codec=%s lang=%s → SKIP (bitmap)", idx, codec, lang)
            continue

        # Default-include unknown codecs as text — many obscure muxer names
        # exist and ffmpeg can usually decode them.  Worst case we'll fail
        # the three-tier extraction below and skip with a log message.
        if codec and codec not in _TEXT_SUB_CODECS:
            L.info("  - stream #%d codec=%s lang=%s → unknown codec, attempting extraction anyway", idx, codec, lang)

        out_name = f"{video_id}_emb_{idx}_{safe_lang}.vtt"
        out_path = Path(out_dir) / out_name

        success_tier = None
        last_err = ""

        # ---------- Tier-1: direct WebVTT mux -----------------------------
        last_err = await _ffmpeg_extract_subtitle(src_path, idx, out_path, codec_args=["-c:s", "webvtt"])
        if _file_nonempty(out_path):
            success_tier = 1
        else:
            L.info("  - stream #%d tier-1 (direct webvtt) failed: %s", idx, last_err[:200] if last_err else "(no stderr)")

        # ---------- Tier-2: native copy → webvtt --------------------------
        if not success_tier:
            inter_ext = ".srt" if codec in {"subrip", "srt"} else ".ass" if codec in {"ass", "ssa"} else ".srt"
            inter_path = out_path.with_suffix(inter_ext)
            err1 = await _ffmpeg_extract_subtitle(src_path, idx, inter_path, codec_args=["-c:s", "copy"])
            if _file_nonempty(inter_path):
                # Convert the standalone subtitle file to WebVTT
                proc = await asyncio.create_subprocess_exec(
                    "ffmpeg", "-y", "-i", str(inter_path), "-c:s", "webvtt", str(out_path),
                    stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.PIPE,
                )
                _stdout, stderr = await proc.communicate()
                try:
                    inter_path.unlink()
                except Exception:
                    pass
                if _file_nonempty(out_path):
                    success_tier = 2
                else:
                    last_err = stderr.decode(errors="replace") if stderr else ""
                    L.info("  - stream #%d tier-2 (native→webvtt) failed: %s", idx, last_err[:200])
            else:
                last_err = err1
                L.info("  - stream #%d tier-2 native copy failed: %s", idx, last_err[:200])

        # ---------- Tier-3: transcode through srt -------------------------
        if not success_tier:
            tmp_srt = out_path.with_suffix(".srt")
            err2 = await _ffmpeg_extract_subtitle(src_path, idx, tmp_srt, codec_args=["-c:s", "srt"])
            if _file_nonempty(tmp_srt):
                proc = await asyncio.create_subprocess_exec(
                    "ffmpeg", "-y", "-i", str(tmp_srt), "-c:s", "webvtt", str(out_path),
                    stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.PIPE,
                )
                _stdout, stderr = await proc.communicate()
                try:
                    tmp_srt.unlink()
                except Exception:
                    pass
                if _file_nonempty(out_path):
                    success_tier = 3
                else:
                    last_err = stderr.decode(errors="replace") if stderr else ""
            else:
                last_err = err2

        if not success_tier:
            L.warning("  - stream #%d FAILED all 3 tiers (codec=%s lang=%s).  Last err: %s",
                      idx, codec, lang, last_err[:300] if last_err else "(none)")
            # Clean any partial output
            try:
                if out_path.exists():
                    out_path.unlink()
            except Exception:
                pass
            continue

        L.info("  - stream #%d codec=%s lang=%s label=%s → EXTRACTED (tier-%d, %d bytes)",
               idx, codec, lang, label, success_tier, out_path.stat().st_size)
        out.append({
            "rel_path": str(out_path),
            "language": lang if lang != "und" else "",
            "label": label,
        })
    return out


def _file_nonempty(p: Path) -> bool:
    try:
        return p.exists() and p.stat().st_size > 0
    except Exception:
        return False


async def _ffmpeg_extract_subtitle(src: str, stream_index: int, out: Path, codec_args: List[str]) -> str:
    """Run a single ffmpeg extraction.  Returns the (possibly truncated)
    stderr output for logging.  Tries both ``-map 0:<idx>`` and ``-map 0:s:0``
    selectors because some unusual MKVs only accept the latter.
    """
    # Remove any stale output
    try:
        if out.exists():
            out.unlink()
    except Exception:
        pass
    cmd = [
        "ffmpeg", "-y",
        "-fflags", "+genpts",
        "-err_detect", "ignore_err",
        "-i", src,
        "-map", f"0:{stream_index}",
        *codec_args,
        str(out),
    ]
    proc = await asyncio.create_subprocess_exec(
        *cmd, stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.PIPE,
    )
    _stdout, stderr = await proc.communicate()
    return (stderr or b"").decode(errors="replace")


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
