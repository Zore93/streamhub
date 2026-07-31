import React, { useEffect, useRef, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import api, { mediaUrl, BACKEND_URL } from "@/lib/api";
import { useAuth } from "@/contexts/AuthContext";
import { useT } from "@/contexts/LanguageContext";
import { categoryLabel } from "@/i18n";
import { Layout } from "@/layout/Layout";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { Eye, Crown, Lock, Send, Trash2, Loader2, ThumbsUp, Folder, Coins } from "lucide-react";
import { toast } from "sonner";
import VideoPlayer from "@/components/VideoPlayer";
import FramedAvatar from "@/components/FramedAvatar";
import { Progress } from "@/components/ui/progress";

export default function Watch() {
  const { id } = useParams();
  const navigate = useNavigate();
  const { user, refresh } = useAuth();
  const { t, lang } = useT();
  const [video, setVideo] = useState(null);
  const [recs, setRecs] = useState([]);
  const [comments, setComments] = useState([]);
  const [comment, setComment] = useState("");
  const [resolution, setResolution] = useState(null);
  const [allowDownload, setAllowDownload] = useState(false);
  const [categories, setCategories] = useState([]);
  const [nextInSeries, setNextInSeries] = useState(null);

  useEffect(() => {
    api.get("/categories").then((r) => setCategories(r.data)).catch(() => {});
  }, []);
  const category = categories.find((c) => c.id === video?.category_id);

  // When this video belongs to a Shorts series, look up the next episode so
  // we can auto-advance playback + show a "Next episode" link in the UI.
  useEffect(() => {
    if (!video?.shorts_series_id) { setNextInSeries(null); return; }
    let alive = true;
    api.get(`/shorts-series/${video.shorts_series_id}`).then((r) => {
      if (!alive) return;
      const eps = r.data.episodes || [];
      const idx = eps.findIndex((e) => e.id === video.id);
      const next = idx >= 0 && idx + 1 < eps.length ? eps[idx + 1] : null;
      setNextInSeries(next);
    }).catch(() => {});
    return () => { alive = false; };
  }, [video?.shorts_series_id, video?.id]);

  const goToNextEpisode = () => {
    if (!nextInSeries) return;
    navigate(`/watch/${nextInSeries.slug || nextInSeries.id}`);
  };

  // 5-second countdown overlay when an episode ends and there's a next one.
  const [autoplayCountdown, setAutoplayCountdown] = useState(null); // null | 5..0
  const countdownTimerRef = useRef(null);
  const clearAutoplay = () => {
    if (countdownTimerRef.current) {
      clearInterval(countdownTimerRef.current);
      countdownTimerRef.current = null;
    }
    setAutoplayCountdown(null);
  };
  const startAutoplay = () => {
    if (!nextInSeries) return;
    // Guard against a duplicate timer if the video re-emits `ended` (Safari).
    if (countdownTimerRef.current) return;
    setAutoplayCountdown(5);
    countdownTimerRef.current = setInterval(() => {
      setAutoplayCountdown((c) => {
        if (c == null) return null;
        if (c <= 1) {
          clearInterval(countdownTimerRef.current);
          countdownTimerRef.current = null;
          // Navigate on the next tick so React finishes this state update first.
          setTimeout(goToNextEpisode, 0);
          return 0;
        }
        return c - 1;
      });
    }, 1000);
  };
  // Reset the countdown whenever we land on a new episode.
  useEffect(() => {
    clearAutoplay();
  }, [id]);
  useEffect(() => () => clearAutoplay(), []);

  useEffect(() => {
    let alive = true;
    Promise.all([
      api.get(`/videos/${id}`),
      api.get(`/videos/${id}/recommendations?limit=15`),
      api.get(`/videos/${id}/comments`),
    ]).then(([v, rec, com]) => {
      if (!alive) return;
      setVideo(v.data);
      if (v.data.renditions?.length) {
        setResolution((cur) => cur || v.data.renditions[v.data.renditions.length - 1].resolution);
      }
      if (v.data.slug && id !== v.data.slug) {
        navigate(`/watch/${v.data.slug}`, { replace: true });
      }
      setRecs(rec.data);
      setComments(com.data);
    });
    api.post(`/videos/${id}/view`).catch(() => {});
    return () => { alive = false; };
  }, [id, navigate]);

  useEffect(() => {
    api.get("/site/player-config").then((r) => setAllowDownload(!!r.data.allow_video_download)).catch(() => {});
  }, []);

  // Real-time status updates via WebSocket (replaces HTTP polling).  Open a
  // /api/videos/{id}/status socket whenever the video isn't fully ready and
  // merge incoming `video.status` packets into local state.  When playback is
  // already possible we skip the socket entirely.
  const wsRef = useRef(null);
  useEffect(() => {
    if (!video) return;
    const hasPlayable = (video.renditions || []).length > 0;
    if (video.status === "ready" && hasPlayable) return;
    if (video.status === "failed") return;

    const base = BACKEND_URL || window.location.origin;
    const url = new URL(`/api/videos/${id}/status`, base);
    url.protocol = url.protocol === "https:" ? "wss:" : "ws:";
    let cancelled = false;
    let reconnectTimer = null;

    const connect = () => {
      let ws;
      try { ws = new WebSocket(url.toString()); } catch { return; }
      wsRef.current = ws;
      ws.onmessage = (ev) => {
        try {
          const payload = JSON.parse(ev.data);
          if (payload.type === "video.status" && payload.data) {
            setVideo((prev) => (prev ? { ...prev, ...payload.data } : prev));
            // Promote default resolution as soon as first rendition lands.
            const r = payload.data.renditions || [];
            if (r.length && !resolution) {
              setResolution(r[r.length - 1].resolution);
            }
          }
        } catch (_e) { /* ignore */ }
      };
      ws.onclose = () => {
        if (cancelled) return;
        reconnectTimer = setTimeout(connect, 3000);
      };
      ws.onerror = () => { try { ws.close(); } catch (_e) { /* ignore */ } };
    };
    connect();

    return () => {
      cancelled = true;
      if (reconnectTimer) clearTimeout(reconnectTimer);
      const ws = wsRef.current;
      if (!ws) return;
      if (ws.readyState === WebSocket.CONNECTING) {
        ws.addEventListener("open", () => { try { ws.close(); } catch (_e) { /* ignore */ } }, { once: true });
      } else {
        try { ws.close(); } catch (_e) { /* ignore */ }
      }
    };
  }, [id, video?.status, video?.renditions?.length, resolution]);

  const currentRendition = video?.renditions?.find((r) => r.resolution === resolution) || video?.renditions?.[0];

  const submitComment = async (e) => {
    e.preventDefault();
    if (!comment.trim()) return;
    try {
      const { data } = await api.post(`/videos/${id}/comments`, { content: comment });
      setComments([data, ...comments]);
      setComment("");
      if (data.coins_awarded > 0) {
        toast.success(`+${data.coins_awarded} ${t("common.coins")}!`, { icon: "🪙" });
        refresh?.();
      }
    } catch (err) {
      toast.error(err.response?.data?.detail || "Comment failed");
    }
  };

  const toggleLike = async () => {
    if (!user) return toast.error(t("auth.signIn"));
    const { data } = await api.post(`/videos/${id}/like`);
    setVideo({ ...video, likes: data.liked ? [...(video.likes || []), user.id] : (video.likes || []).filter((x) => x !== user.id) });
    if (data.coins_awarded > 0) {
      toast.success(`+${data.coins_awarded} ${t("common.coins")}!`, { icon: "🪙" });
      refresh?.();
    }
  };

  const delComment = async (cid) => {
    await api.delete(`/comments/${cid}`);
    setComments(comments.filter((c) => c.id !== cid));
  };

  if (!video) return <Layout><div className="text-zinc-500">{t("page.loading")}</div></Layout>;

  const isVipVideo = video.access_tier === "vip";
  const isProVideo = video.access_tier === "pro";
  // The server is the source of truth for locked state (it already applied the
  // tier hierarchy + admin bypass). Fall back to a client-side check only when
  // the server left the flag unset AND the client-side user object is fresh.
  const isLocked = video.locked === true;
  const hasPlayable = (video.renditions || []).length > 0;
  const isProcessing = !isLocked && (!hasPlayable || video.status === "processing");

  return (
    <Layout recommendations={recs}>
      <div data-testid="watch-page">
        <div className="aspect-video bg-black rounded-lg overflow-hidden relative">
          {isLocked ? (
            <div className="absolute inset-0 flex flex-col items-center justify-center bg-zinc-950 text-center px-6" data-testid="locked-view">
              <Lock size={48} className={isVipVideo ? "vip-gradient-text mb-3" : "text-rose-500 mb-3"} />
              <h3 className="text-xl font-semibold mb-1">
                {isVipVideo ? "Conținut VIP" : t("player.proLocked")}
              </h3>
              <p className="text-zinc-400 mb-4">
                {isVipVideo
                  ? "Ai nevoie de un abonament VIP pentru a vedea acest episod."
                  : t("player.proLocked.body")}
              </p>
              {isVipVideo ? (
                <Link to="/vip" data-testid="upgrade-vip-btn">
                  <Button className="vip-gradient text-black font-bold border-0">
                    <Crown size={14} className="mr-1" /> Devino VIP
                  </Button>
                </Link>
              ) : (
                <Link to="/pro"><Button className="pro-gradient text-white border-0">{t("player.upgrade")}</Button></Link>
              )}
            </div>
          ) : isProcessing ? (
            <div className="absolute inset-0 flex flex-col items-center justify-center bg-zinc-950 text-center px-6" data-testid="processing-view">
              <Loader2 size={42} className="text-rose-500 mb-4 animate-spin" />
              <p className="text-zinc-200 max-w-md">{t("player.processing")}</p>
              {video.progress != null && (
                <div className="w-64 mt-5">
                  <Progress value={video.progress} className="h-2" />
                  <div className="text-xs text-zinc-500 mt-2">{video.progress}%</div>
                </div>
              )}
            </div>
          ) : currentRendition ? (
            <>
              <VideoPlayer
                video={video}
                currentRendition={currentRendition}
                resolution={resolution}
                setResolution={setResolution}
                allowDownload={allowDownload}
                onEnded={startAutoplay}
              />
              {nextInSeries && autoplayCountdown !== null && (
                <div
                  className="absolute inset-0 z-30 flex items-center justify-center bg-black/85 backdrop-blur-sm"
                  data-testid="autoplay-overlay"
                >
                  <div className="max-w-md w-full text-center px-6">
                    <div className="text-xs uppercase tracking-[0.24em] text-zinc-500 mb-2">
                      Următorul episod în {autoplayCountdown}…
                    </div>
                    {nextInSeries.thumbnail_url && (
                      <img
                        src={mediaUrl(nextInSeries.thumbnail_url)}
                        alt=""
                        className="mx-auto mb-3 rounded-md max-h-40 object-cover shadow-lg"
                      />
                    )}
                    <h3 className="text-lg font-semibold text-zinc-50 mb-4 line-clamp-2">
                      {nextInSeries.title}
                    </h3>
                    <div className="flex justify-center gap-2">
                      <Button
                        variant="outline"
                        onClick={clearAutoplay}
                        className="border-zinc-700 hover:bg-zinc-800"
                        data-testid="autoplay-cancel"
                      >
                        Anulează
                      </Button>
                      <Button
                        onClick={() => { clearAutoplay(); goToNextEpisode(); }}
                        className="pro-gradient text-white border-0"
                        data-testid="autoplay-play-now"
                      >
                        Redă acum
                      </Button>
                    </div>
                  </div>
                </div>
              )}
            </>
          ) : (
            <div className="absolute inset-0 flex items-center justify-center text-zinc-500">
              {video.status}...
            </div>
          )}
        </div>

        <div className="flex items-center justify-between mt-5 mb-2 flex-wrap gap-2">
          <h1 className="text-2xl sm:text-3xl font-bold font-heading">{video.title}</h1>
          <div className="flex items-center gap-2 flex-wrap">
            {nextInSeries && (
              <button
                type="button"
                onClick={goToNextEpisode}
                className="text-xs px-3 py-1.5 rounded-md bg-zinc-800 hover:bg-zinc-700 text-zinc-100 flex items-center gap-1.5 transition-colors"
                data-testid="next-episode-btn"
                title={nextInSeries.title}
              >
                Next → <span className="text-zinc-400 max-w-[220px] truncate">{nextInSeries.title}</span>
              </button>
            )}
            {video.access_tier === "vip" ? (
              <span className="vip-gradient text-black text-xs font-bold px-3 py-1 rounded-md flex items-center gap-1" data-testid="watch-vip-badge">
                <Crown size={12} /> VIP
              </span>
            ) : video.access_tier === "pro" && (
              <span className="pro-gradient text-white text-xs font-semibold px-3 py-1 rounded-md flex items-center gap-1" data-testid="watch-pro-badge">
                <Crown size={12} /> PRO
              </span>
            )}
          </div>
        </div>

        <div className="flex flex-wrap items-center gap-3 sm:gap-4 mb-4">
          <button
            onClick={toggleLike}
            className={`inline-flex items-center gap-2 px-4 py-2 rounded-full text-sm font-medium transition-colors border ${
              user && video.likes?.includes(user.id)
                ? "bg-rose-500 border-rose-500 text-white"
                : "bg-zinc-900 border-zinc-800 text-zinc-200 hover:bg-zinc-800"
            }`}
            data-testid="like-btn"
          >
            <ThumbsUp size={14} className={user && video.likes?.includes(user.id) ? "fill-white" : ""} />
            <span>Like</span>
            <span className="text-zinc-400">·</span>
            <span>{video.likes?.length || 0}</span>
          </button>
          <span className="text-zinc-500 text-sm flex items-center gap-1.5"><Eye size={14} /> {video.views} {t("video.views")}</span>
          {/* Uploader — opens profile in a new tab on Ctrl/Cmd+click; users can also right-click → "open in new tab". */}
          <a
            href={`/profile/${video.uploader_id}`}
            target="_blank"
            rel="noopener noreferrer"
            className="text-zinc-400 hover:text-zinc-100 text-sm"
            data-testid="uploader-link"
          >
            @{video.uploader_username}
          </a>
          {category && (
            <a
              href={`/category/${category.id}`}
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex items-center gap-1.5 text-sm text-zinc-300 bg-zinc-900 hover:bg-zinc-800 border border-zinc-800 px-3 py-1 rounded-full transition-colors"
              data-testid="video-category-link"
            >
              <Folder size={12} /> {categoryLabel(category, lang)}
            </a>
          )}
        </div>

        {video.description && (
          <div className="bg-zinc-900 border border-zinc-800 rounded-lg p-4 mb-6 text-zinc-300 whitespace-pre-line">{video.description}</div>
        )}

        {video.tags?.length > 0 && (
          <div className="flex flex-wrap gap-2 mb-6">
            {video.tags.map((tg) => <span key={tg} className="text-xs bg-zinc-800 text-zinc-300 px-2 py-1 rounded">#{tg}</span>)}
          </div>
        )}

        {/* Comments */}
        <div className="mt-8" data-testid="comments-section">
          <h2 className="text-xl font-semibold mb-4">{t("comments.title")} ({comments.length})</h2>
          {user ? (
            <form onSubmit={submitComment} className="flex gap-3 mb-6 items-start">
              <FramedAvatar
                src={user.avatar_url}
                username={user.username}
                size={56}
                frame={null}
                className="flex-shrink-0 hidden sm:inline-block"
              />
              <Textarea
                value={comment}
                onChange={(e) => setComment(e.target.value)}
                placeholder={t("comments.placeholder")}
                className="bg-zinc-900 border-zinc-800 min-h-[88px] text-base"
                rows={3}
                data-testid="comment-input"
              />
              <Button type="submit" className="pro-gradient text-white border-0 self-end h-10 px-4" data-testid="comment-submit">
                <Send size={16} />
              </Button>
            </form>
          ) : (
            <p className="text-zinc-500 mb-4">{t("comments.signInToComment")}</p>
          )}
          <div className="space-y-4">
            {comments.map((c) => (
              <div
                key={c.id}
                className="flex gap-4 bg-zinc-900 border border-zinc-800 rounded-lg p-4"
                data-testid={`comment-${c.id}`}
              >
                <a
                  href={`/profile/${c.user_id}`}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="flex-shrink-0"
                >
                  <FramedAvatar
                    src={c.avatar_url}
                    username={c.username}
                    size={100}
                    frame={c.frame || null}
                    data-testid={`comment-avatar-${c.id}`}
                  />
                </a>
                <div className="flex-1 min-w-0">
                  <div className="flex items-center justify-between gap-2">
                    <a
                      href={`/profile/${c.user_id}`}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="font-semibold text-base hover:text-rose-300 transition-colors"
                      data-testid={`comment-author-${c.id}`}
                    >
                      @{c.username}
                    </a>
                    {(user?.id === c.user_id || user?.role === "admin") && (
                      <button
                        onClick={() => delComment(c.id)}
                        className="text-zinc-500 hover:text-red-400"
                        data-testid={`comment-delete-${c.id}`}
                      >
                        <Trash2 size={16} />
                      </button>
                    )}
                  </div>
                  <p className="text-zinc-200 mt-2 whitespace-pre-line text-base leading-relaxed">{c.content}</p>
                </div>
              </div>
            ))}
            {comments.length === 0 && <p className="text-zinc-500 text-sm">{t("comments.empty")}</p>}
          </div>
        </div>
      </div>
    </Layout>
  );
}
