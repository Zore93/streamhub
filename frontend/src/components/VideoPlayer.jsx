import React, { useEffect, useRef, useState } from "react";
import { Play, Pause, Volume2, VolumeX, Maximize, Subtitles, Settings, Download } from "lucide-react";
import { mediaUrl } from "@/lib/api";
import {
  DropdownMenu, DropdownMenuTrigger, DropdownMenuContent, DropdownMenuItem,
  DropdownMenuLabel, DropdownMenuSeparator,
} from "@/components/ui/dropdown-menu";

/**
 * Custom video player with rearrangeable controls so that the order along the
 * bottom bar is:  play · time · scrubber │ volume · CC · resolution · download · fullscreen
 */
export default function VideoPlayer({ video, currentRendition, resolution, setResolution, allowDownload }) {
  const ref = useRef(null);
  const wrapRef = useRef(null);
  const [playing, setPlaying] = useState(false);
  const [muted, setMuted] = useState(false);
  const [volume, setVolume] = useState(1);
  const [time, setTime] = useState(0);
  const [duration, setDuration] = useState(video.duration_sec || 0);
  const [activeTrack, setActiveTrack] = useState("off");
  const [savedTime, setSavedTime] = useState(0);

  // When user switches resolution we preserve current playback time
  useEffect(() => {
    const v = ref.current;
    if (!v) return;
    const wasPlaying = !v.paused;
    v.currentTime = savedTime;
    if (wasPlaying) v.play().catch(() => {});
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [currentRendition?.url]);

  useEffect(() => {
    const v = ref.current;
    if (!v) return;
    const onTime = () => setTime(v.currentTime);
    const onDur = () => setDuration(v.duration || video.duration_sec || 0);
    const onPlay = () => setPlaying(true);
    const onPause = () => setPlaying(false);
    v.addEventListener("timeupdate", onTime);
    v.addEventListener("loadedmetadata", onDur);
    v.addEventListener("play", onPlay);
    v.addEventListener("pause", onPause);
    return () => {
      v.removeEventListener("timeupdate", onTime);
      v.removeEventListener("loadedmetadata", onDur);
      v.removeEventListener("play", onPlay);
      v.removeEventListener("pause", onPause);
    };
  }, [video.duration_sec]);

  const togglePlay = () => {
    const v = ref.current; if (!v) return;
    if (v.paused) v.play(); else v.pause();
  };
  const seek = (e) => {
    const v = ref.current; if (!v) return;
    const t = parseFloat(e.target.value);
    v.currentTime = t; setTime(t);
  };
  const toggleMute = () => {
    const v = ref.current; if (!v) return;
    v.muted = !v.muted; setMuted(v.muted);
  };
  const setVol = (e) => {
    const v = ref.current; if (!v) return;
    const x = parseFloat(e.target.value);
    v.volume = x; setVolume(x); setMuted(x === 0);
  };
  const toggleFullscreen = () => {
    const w = wrapRef.current; if (!w) return;
    if (!document.fullscreenElement) w.requestFullscreen?.();
    else document.exitFullscreen?.();
  };
  const selectTrack = (id) => {
    setActiveTrack(id);
    const v = ref.current; if (!v) return;
    for (let i = 0; i < v.textTracks.length; i++) {
      v.textTracks[i].mode = (v.textTracks[i].id === id) ? "showing" : "disabled";
    }
  };
  const fmt = (s) => {
    if (!s || !isFinite(s)) return "0:00";
    const m = Math.floor(s / 60);
    const sec = Math.floor(s % 60);
    return `${m}:${String(sec).padStart(2, "0")}`;
  };

  // Wire <track> ids so we can toggle them
  useEffect(() => {
    const v = ref.current; if (!v) return;
    setTimeout(() => {
      for (let i = 0; i < v.textTracks.length; i++) {
        v.textTracks[i].mode = i === 0 ? "showing" : "disabled";
      }
      if (v.textTracks[0]) setActiveTrack(v.textTracks[0].id || "0");
    }, 100);
  }, [video.subtitles?.length, currentRendition?.url]);

  if (!currentRendition) return null;

  return (
    <div ref={wrapRef} className="relative w-full h-full bg-black group" data-testid="video-player">
      <video
        ref={ref}
        src={mediaUrl(currentRendition.url)}
        crossOrigin="anonymous"
        className="w-full h-full"
        onTimeUpdate={() => setSavedTime(ref.current?.currentTime || 0)}
        onClick={togglePlay}
        poster={video.thumbnail_url ? mediaUrl(video.thumbnail_url) : undefined}
      >
        {(video.subtitles || []).map((s, i) => (
          <track key={s.id} id={s.id} kind="subtitles" src={mediaUrl(s.url)} srcLang={s.language} label={s.label} default={i === 0} />
        ))}
      </video>

      {/* Bottom control bar */}
      <div className="absolute bottom-0 left-0 right-0 px-3 pt-10 pb-3 bg-gradient-to-t from-black/85 via-black/40 to-transparent opacity-100 group-hover:opacity-100 transition-opacity">
        {/* Scrubber */}
        <input
          type="range" min="0" max={duration || 0} step="0.1" value={time}
          onChange={seek}
          className="w-full accent-rose-500 cursor-pointer"
          data-testid="player-scrubber"
        />
        <div className="flex items-center gap-2 mt-2 text-zinc-100 text-sm">
          <button onClick={togglePlay} className="hover:text-rose-400 p-1" data-testid="player-play">
            {playing ? <Pause size={20} /> : <Play size={20} fill="currentColor" />}
          </button>
          <span className="tabular-nums text-xs text-zinc-300">{fmt(time)} / {fmt(duration)}</span>

          <div className="flex-1" />

          {/* Volume */}
          <div className="flex items-center gap-1 group/vol">
            <button onClick={toggleMute} className="hover:text-rose-400 p-1" data-testid="player-mute">
              {muted || volume === 0 ? <VolumeX size={18} /> : <Volume2 size={18} />}
            </button>
            <input
              type="range" min="0" max="1" step="0.05"
              value={muted ? 0 : volume} onChange={setVol}
              className="w-0 opacity-0 group-hover/vol:w-20 group-hover/vol:opacity-100 transition-all accent-rose-500 cursor-pointer"
            />
          </div>

          {/* CC (subtitles) - right beside volume */}
          {(video.subtitles || []).length > 0 && (
            <DropdownMenu>
              <DropdownMenuTrigger asChild>
                <button className="hover:text-rose-400 p-1" data-testid="player-cc">
                  <Subtitles size={18} />
                </button>
              </DropdownMenuTrigger>
              <DropdownMenuContent className="bg-zinc-900 border-zinc-800 text-zinc-100">
                <DropdownMenuLabel className="text-xs">Subtitles</DropdownMenuLabel>
                <DropdownMenuSeparator className="bg-zinc-800" />
                <DropdownMenuItem onClick={() => selectTrack("off")} className={activeTrack === "off" ? "text-rose-400" : ""}>
                  Off
                </DropdownMenuItem>
                {(video.subtitles || []).map((s) => (
                  <DropdownMenuItem key={s.id} onClick={() => selectTrack(s.id)} className={activeTrack === s.id ? "text-rose-400" : ""} data-testid={`player-cc-${s.id}`}>
                    {s.label} <span className="text-xs text-zinc-500 ml-2">({s.language})</span>
                  </DropdownMenuItem>
                ))}
              </DropdownMenuContent>
            </DropdownMenu>
          )}

          {/* Resolution - right beside CC */}
          {(video.renditions || []).length > 1 && (
            <DropdownMenu>
              <DropdownMenuTrigger asChild>
                <button className="hover:text-rose-400 p-1 inline-flex items-center gap-1 text-xs" data-testid="player-resolution">
                  <Settings size={18} />
                  <span className="hidden sm:inline">{resolution}</span>
                </button>
              </DropdownMenuTrigger>
              <DropdownMenuContent className="bg-zinc-900 border-zinc-800 text-zinc-100">
                <DropdownMenuLabel className="text-xs">Quality</DropdownMenuLabel>
                <DropdownMenuSeparator className="bg-zinc-800" />
                {video.renditions.map((r) => (
                  <DropdownMenuItem key={r.resolution} onClick={() => setResolution(r.resolution)} className={resolution === r.resolution ? "text-rose-400" : ""} data-testid={`player-res-${r.resolution}`}>
                    {r.resolution}
                  </DropdownMenuItem>
                ))}
              </DropdownMenuContent>
            </DropdownMenu>
          )}

          {/* Download (if allowed) */}
          {allowDownload && (
            <a
              href={mediaUrl(currentRendition.url)}
              download
              className="hover:text-rose-400 p-1"
              data-testid="player-download"
              title="Download this resolution"
            >
              <Download size={18} />
            </a>
          )}

          <button onClick={toggleFullscreen} className="hover:text-rose-400 p-1" data-testid="player-fullscreen">
            <Maximize size={18} />
          </button>
        </div>
      </div>
    </div>
  );
}
