import React from "react";
import { Link } from "react-router-dom";
import { mediaUrl } from "@/lib/api";
import { Play, Eye, Crown, Loader2 } from "lucide-react";

export default function VideoCard({ v, vertical = false }) {
  const isProcessing = v.status && v.status !== "ready";
  return (
    <Link to={`/watch/${v.id}`} className="group block" data-testid={`video-card-${v.id}`}>
      <div className={`${vertical ? "aspect-[9/16]" : "aspect-video"} overflow-hidden rounded-lg bg-zinc-900 relative`}>
        {v.thumbnail_url ? (
          <img
            src={mediaUrl(v.thumbnail_url)}
            alt={v.title}
            className="w-full h-full object-cover transition-transform duration-300 group-hover:scale-105"
          />
        ) : (
          <div className="w-full h-full flex items-center justify-center text-zinc-700">
            <Play size={32} />
          </div>
        )}
        <div className="absolute inset-0 bg-black/40 opacity-0 group-hover:opacity-100 transition flex items-center justify-center">
          <div className="h-12 w-12 rounded-full bg-rose-500 flex items-center justify-center">
            <Play size={20} className="text-white fill-white" />
          </div>
        </div>
        {v.access_tier === "pro" && (
          <div className="absolute top-2 right-2 pro-gradient text-white text-xs font-semibold px-2 py-1 rounded-md flex items-center gap-1">
            <Crown size={10} /> PRO
          </div>
        )}
        {isProcessing && (
          <div className="absolute top-2 left-2 bg-amber-500/95 text-white text-[10px] font-semibold px-2 py-1 rounded-md flex items-center gap-1" data-testid="processing-badge">
            <Loader2 size={10} className="animate-spin" /> {v.progress != null ? `${v.progress}%` : "…"}
          </div>
        )}
        {v.duration_sec > 0 && (
          <div className="absolute bottom-2 right-2 bg-black/80 text-white text-xs px-1.5 py-0.5 rounded">
            {formatDuration(v.duration_sec)}
          </div>
        )}
      </div>
      <div className="mt-3">
        <h3 className="font-semibold text-zinc-100 line-clamp-2 group-hover:text-rose-400 transition-colors">{v.title}</h3>
        <div className="text-sm text-zinc-500 mt-1 flex items-center gap-3">
          <span className="truncate">{v.uploader_username}</span>
          <span className="flex items-center gap-1"><Eye size={12} />{v.views}</span>
        </div>
      </div>
    </Link>
  );
}

function formatDuration(s) {
  const m = Math.floor(s / 60);
  const sec = Math.floor(s % 60);
  return `${m}:${String(sec).padStart(2, "0")}`;
}
