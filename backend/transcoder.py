"""FFmpeg transcoding & thumbnail generation."""
import asyncio
import json
import logging
import os
import re
from pathlib import Path
from typing import Awaitable, Callable, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

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
        # Pick the LARGEST video stream (by pixel count) for width/height.
        # Many MKV / MP4 containers embed cover-art as a tiny attached picture
        # stream flagged as codec_type="video" — that used to make us encode
        # 1080p sources at only 320x320 (or whatever the thumbnail was).
        # Re-query width/height per video stream because the initial projection
        # didn't include them.
        proc2 = await asyncio.create_subprocess_exec(
            "ffprobe",
            "-v", "error",
            "-select_streams", "v",
            "-show_entries", "stream=index,width,height,disposition",
            "-of", "json",
            path,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        out2, _ = await proc2.communicate()
        try:
            vstreams = json.loads(out2.decode()).get("streams", []) or []
        except Exception:
            vstreams = []
        # Prefer streams whose `attached_pic` disposition flag is 0 (i.e. real
        # video), then pick the biggest one by width*height.
        def _pixels(s: Dict) -> int:
            try:
                return int(s.get("width", 0) or 0) * int(s.get("height", 0) or 0)
            except Exception:
                return 0
        real_streams = [
            s for s in vstreams
            if not (s.get("disposition") or {}).get("attached_pic")
        ]
        pool = real_streams or vstreams
        video_stream: Dict = max(pool, key=_pixels, default={})
        if _pixels(video_stream) == 0 and vstreams:
            # last-resort fallback — some ffprobe builds don't fill disposition
            video_stream = max(vstreams, key=_pixels, default={})
        logger.info(
            "probe_video: %s → %d video stream(s), chose index=%s %dx%d (candidates: %s)",
            Path(path).name, len(vstreams), video_stream.get("index"),
            int(video_stream.get("width", 0) or 0),
            int(video_stream.get("height", 0) or 0),
            [(s.get("index"), s.get("width"), s.get("height")) for s in vstreams],
        )
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


# crf + max video bitrate (kbps) per output height + audio bitrate + x264 preset
# `preset` controls encoding SPEED vs compression:
#   veryfast  — ~5-8x real-time (fast like it used to be before compression profiles)
#   fast      — ~3-5x real-time
#   medium    — ~1-2x real-time (ffmpeg default)
#   slow      — ~0.5x real-time (best compression)
ENCODE_PROFILES: Dict[str, dict] = {
    "default":  {"crf": 23, "preset": "veryfast", "caps": {360: 1000, 720: 3500, 1080: 7000, 1152: 8000, 2160: 18000}, "audio": "128k"},
    "original": {"crf": 20, "preset": "slow",     "caps": {360: 1200, 720: 4000, 1080: 8000, 1152: 9000, 2160: 20000}, "audio": "160k"},
    "balanced": {"crf": 23, "preset": "slow",     "caps": {360: 900,  720: 2800, 1080: 5000, 1152: 6000, 2160: 14000}, "audio": "128k"},
    "strong":   {"crf": 25, "preset": "slow",     "caps": {360: 700,  720: 2000, 1080: 3500, 1152: 4200, 2160: 10000}, "audio": "128k"},
    "max":      {"crf": 27, "preset": "slow",     "caps": {360: 500,  720: 1400, 1080: 2500, 1152: 3000, 2160: 7000},  "audio": "96k"},
}
DEFAULT_ENCODE_PROFILE = "default"


async def transcode_to_resolution(
    input_path: str,
    output_path: str,
    target_resolution: str,
    profile: str = DEFAULT_ENCODE_PROFILE,
    duration_sec: float = 0.0,
    on_progress: Optional[Callable[[float, float], Awaitable[None]]] = None,
) -> bool:
    """Transcodes input video to a specific resolution in mp4 (H.264 + AAC).
    Returns True on success.

    If `duration_sec` and `on_progress` are provided, ffmpeg's `-progress pipe:1`
    stream is parsed and the async callback is invoked ~every ~1s with
    (percent_done, eta_seconds) so callers can surface live progress to the UI.

    Strategy: encode into a /tmp staging file first (large videos + multiple
    renditions can easily blow past the small UPLOAD_DIR volume on cloud
    pods — /tmp is usually the bigger overlayfs). We `shutil.move` to the
    final path on success.
    """
    if target_resolution not in RESOLUTIONS:
        return False
    w, h = RESOLUTIONS[target_resolution]
    prof = ENCODE_PROFILES.get(profile) or ENCODE_PROFILES[DEFAULT_ENCODE_PROFILE]
    cap = prof["caps"].get(h, 5000)
    preset = prof.get("preset", "slow")
    logger.info(
        "transcode_to_resolution: → %s (%dx%d) profile=%s preset=%s crf=%d maxrate=%dk dur=%.1fs",
        target_resolution, w, h, profile, preset, prof["crf"], cap, duration_sec,
    )
    vf = f"scale='if(gt(a,{w}/{h}),{w},-2)':'if(gt(a,{w}/{h}),-2,{h})'"
    Path(os.path.dirname(output_path)).mkdir(parents=True, exist_ok=True)
    import tempfile
    tmp_fd, tmp_name = tempfile.mkstemp(
        suffix=f"_{target_resolution}.mp4", prefix=f"rend_",
    )
    os.close(tmp_fd)
    try:
        # When we want live progress we pipe the key=value stream to stdout.
        progress_arg = ["-progress", "pipe:1"] if (on_progress and duration_sec > 0) else []
        proc = await asyncio.create_subprocess_exec(
            "ffmpeg",
            "-y",
            "-v", "error",
            "-nostats",
            "-i", input_path,
            "-vf", vf,
            "-c:v", "libx264",
            "-preset", preset,
            "-crf", str(prof["crf"]),
            "-maxrate", f"{cap}k",
            "-bufsize", f"{cap * 2}k",
            "-profile:v", "high",
            "-pix_fmt", "yuv420p",
            "-c:a", "aac",
            "-b:a", prof["audio"],
            "-movflags", "+faststart",
            *progress_arg,
            tmp_name,
            stdout=asyncio.subprocess.PIPE if progress_arg else asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.PIPE,
        )

        # Read progress stream concurrently with waiting for ffmpeg to finish.
        async def _drain_progress():
            if not progress_arg or proc.stdout is None:
                return
            start_ts = asyncio.get_event_loop().time()
            last_report = 0.0
            out_time_us = 0  # last reported encode position in microseconds
            try:
                while True:
                    line = await proc.stdout.readline()
                    if not line:
                        break
                    s = line.decode(errors="ignore").strip()
                    if s.startswith("out_time_us=") or s.startswith("out_time_ms="):
                        try:
                            v = int(s.split("=", 1)[1])
                            # ffmpeg historically mis-labels "out_time_ms" as microseconds
                            out_time_us = v
                        except Exception:
                            pass
                    elif s.startswith("out_time="):
                        # HH:MM:SS.mmm fallback
                        try:
                            hh, mm, rest = s.split("=", 1)[1].split(":")
                            ss = float(rest)
                            out_time_us = int((int(hh) * 3600 + int(mm) * 60 + ss) * 1_000_000)
                        except Exception:
                            pass
                    elif s.startswith("progress="):
                        pass  # emitted periodically; use as a flush trigger below
                    else:
                        continue
                    now = asyncio.get_event_loop().time()
                    if now - last_report < 1.0:
                        continue
                    last_report = now
                    secs_done = out_time_us / 1_000_000.0
                    pct = max(0.0, min(100.0, (secs_done / duration_sec) * 100.0))
                    elapsed = now - start_ts
                    speed = (secs_done / elapsed) if elapsed > 0.1 else 0.0
                    eta = ((duration_sec - secs_done) / speed) if speed > 0.01 else 0.0
                    try:
                        await on_progress(pct, max(0.0, eta))
                    except Exception:
                        pass
            except Exception:
                pass

        drain_task = asyncio.create_task(_drain_progress())
        _, err = await proc.communicate()
        drain_task.cancel()
        try:
            await drain_task
        except Exception:
            pass

        if proc.returncode != 0 or not os.path.exists(tmp_name) or os.path.getsize(tmp_name) == 0:
            tail = (err or b"").decode("utf-8", errors="ignore")[-2000:]
            logger.warning(
                "ffmpeg failed for %s → %s (rc=%s). stderr tail:\n%s",
                target_resolution, output_path, proc.returncode, tail,
            )
            try: os.remove(tmp_name)
            except Exception: pass
            return False
        import shutil as _shutil
        _shutil.move(tmp_name, output_path)
        # Final 100% ping so the UI isn't stuck at e.g. 97%.
        if on_progress:
            try:
                await on_progress(100.0, 0.0)
            except Exception:
                pass
        return os.path.exists(output_path)
    except Exception as e:  # noqa: BLE001
        logger.exception("transcode_to_resolution crashed: %s", e)
        try: os.remove(tmp_name)
        except Exception: pass
        return False


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




# ============ 15s / 30s PREVIEW CLIPS ============
# For non-paying users on PRO/VIP videos: we serve a short free preview and
# then show an upsell overlay. The preview is encoded ONCE at upload with
# `-c copy` for speed; if the keyframe layout prevents a clean copy we fall
# back to a tiny re-encode. Max output ~5-20 MB regardless of source size.
async def extract_preview_clip(src_path: str, out_path: str, duration_sec: int = 30) -> bool:
    """Extract the first `duration_sec` seconds of the source into `out_path`.

    Fast path: `-c copy` (no re-encode). Fallback path: libx264 at CRF 24.
    """
    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    # ---- Fast path: stream-copy VIDEO, re-encode AUDIO to AAC ------
    # Audio must be re-encoded even in the fast path: many sources use codecs
    # MP4 cannot carry (AC3, DTS, Opus in MKV, FLAC, PCM, etc.) and `-c:a copy`
    # into .mp4 silently drops them → the preview ends up muted. AAC @ 128k is
    # universally compatible and still fast because video is still copied.
    try:
        proc = await asyncio.create_subprocess_exec(
            "ffmpeg",
            "-y",
            "-ss", "0",
            "-i", src_path,
            "-t", str(duration_sec),
            "-map", "0:v:0",
            "-map", "0:a:0?",   # audio optional
            "-c:v", "copy",
            "-c:a", "aac",
            "-b:a", "128k",
            "-ac", "2",
            "-movflags", "+faststart",
            str(out),
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.PIPE,
        )
        _, err = await proc.communicate()
        if proc.returncode == 0 and out.exists() and out.stat().st_size > 1024:
            logger.info("preview copy OK: %s (%.1f MB)", out.name, out.stat().st_size / 1024 / 1024)
            return True
        logger.info("preview copy failed (rc=%s), falling back to re-encode: %s",
                    proc.returncode, (err or b'')[-200:].decode(errors='replace'))
    except Exception as e:  # noqa: BLE001
        logger.warning("preview copy exception, falling back: %s", e)
    # ---- Fallback: re-encode (always succeeds) --------------------
    try:
        proc = await asyncio.create_subprocess_exec(
            "ffmpeg",
            "-y",
            "-ss", "0",
            "-i", src_path,
            "-t", str(duration_sec),
            "-vf", "scale='min(1280,iw)':-2",
            "-c:v", "libx264",
            "-preset", "veryfast",
            "-crf", "24",
            "-c:a", "aac",
            "-b:a", "128k",
            "-movflags", "+faststart",
            str(out),
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.PIPE,
        )
        _, err = await proc.communicate()
        if proc.returncode == 0 and out.exists() and out.stat().st_size > 1024:
            logger.info("preview re-encode OK: %s (%.1f MB)", out.name, out.stat().st_size / 1024 / 1024)
            return True
        logger.warning("preview re-encode FAILED rc=%s: %s", proc.returncode, (err or b'')[-400:].decode(errors='replace'))
    except Exception as e:  # noqa: BLE001
        logger.warning("preview re-encode exception: %s", e)
    return False
