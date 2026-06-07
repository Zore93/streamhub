import React from "react";
import { Link } from "react-router-dom";
import { mediaUrl } from "@/lib/api";
import { Play, Eye, Crown, Loader2, Heart, MessageCircle } from "lucide-react";

/**
 * Map the highest available source/rendition height to a marketing label.
 *
 * We consider BOTH the transcoded renditions AND the original source's
 * dimensions — that way a 4K source that has only been partially transcoded
 * (e.g. while 1080p is still encoding) still shows the eventual "4K" badge
 * the user expects.  We also use `max(width, height)` because some content
 * is uploaded sideways (wider than tall) — the long side is the real res.
 *  - 360p → "360P"
 *  - 720p → "720P"
 *  - 1080p → "1080P"
 *  - 1440p / 2K / 2048p → "2K"
 *  - 2160p / 4K / 4096p → "4K"
 *  - 4320p / 8K → "8K"
 */
function highestResolutionLabel(v) {
  const heights = [];
  // From renditions (height OR resolution number)
  for (const r of v.renditions || []) {
    const h = parseInt(r.height, 10) || parseInt(String(r.resolution).replace(/[^0-9]/g, ""), 10) || 0;
    const w = parseInt(r.width, 10) || 0;
    if (h) heights.push(h);
    if (w) heights.push(w);
  }
  // From the original source — wins for migrated/legacy videos with only one transcoded rendition.
  const oh = parseInt(v.original_height, 10) || 0;
  const ow = parseInt(v.original_width, 10) || 0;
  if (oh) heights.push(oh);
  if (ow) heights.push(ow);
  if (heights.length === 0) return null;
  const max = Math.max(...heights);
  if (max >= 4000) return "4K";
  if (max >= 2000) return "2K";
  if (max >= 1080) return "1080P";
  if (max >= 720) return "720P";
  if (max >= 480) return "480P";
  if (max >= 360) return "360P";
  return null;
}

export default function VideoCard({ v, vertical = false }) {
  const isProcessing = v.status && v.status !== "ready";
  const resLabel = highestResolutionLabel(v);
  const watchKey = v.slug || v.id;
  return (
    <Link to={`/watch/${watchKey}`} className="group block" data-testid={`video-card-${v.id}`}>
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

        {/* Top-left: highest available resolution (uses the same pro-gradient
            chip styling as PRO so it visually pairs with it). */}
        {resLabel && (
          <div
            className="absolute top-2 left-2 pro-gradient text-white text-xs font-semibold px-2 py-1 rounded-md"
            data-testid={`res-badge-${v.id}`}
          >
            {resLabel}
          </div>
        )}

        {/* Top-right: PRO badge */}
        {v.access_tier === "pro" && (
          <div className="absolute top-2 right-2 pro-gradient text-white text-xs font-semibold px-2 py-1 rounded-md flex items-center gap-1">
            <Crown size={10} /> PRO
          </div>
        )}

        {/* Processing badge bumps to mid-left when present so it doesn't collide */}
        {isProcessing && (
          <div className="absolute top-12 left-2 bg-amber-500/95 text-white text-[10px] font-semibold px-2 py-1 rounded-md flex items-center gap-1" data-testid="processing-badge">
            <Loader2 size={10} className="animate-spin" /> {v.progress != null ? `${v.progress}%` : "…"}
          </div>
        )}

        {/* Bottom row: time / likes / comments */}
        <div className="absolute bottom-2 right-2 flex items-center gap-1.5">
          {(v.likes?.length || 0) > 0 && (
            <span className="bg-black/80 text-white text-[11px] px-1.5 py-0.5 rounded inline-flex items-center gap-1" data-testid={`likes-${v.id}`}>
              <Heart size={10} /> {v.likes.length}
            </span>
          )}
          {(v.comments_count || 0) > 0 && (
            <span className="bg-black/80 text-white text-[11px] px-1.5 py-0.5 rounded inline-flex items-center gap-1" data-testid={`comments-${v.id}`}>
              <MessageCircle size={10} /> {v.comments_count}
            </span>
          )}
          {v.duration_sec > 0 && (
            <span className="bg-black/80 text-white text-xs px-1.5 py-0.5 rounded">
              {formatDuration(v.duration_sec)}
            </span>
          )}
        </div>
      </div>
      <div className="mt-2 sm:mt-3">
        <h3 className="font-semibold text-sm sm:text-base text-zinc-100 line-clamp-2 group-hover:text-rose-400 transition-colors">{v.title}</h3>
        <div className="text-xs sm:text-sm text-zinc-500 mt-1 flex items-center gap-2 sm:gap-3">
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
