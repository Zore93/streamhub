import React, { useEffect, useState, useRef } from "react";
import { useParams } from "react-router-dom";
import api, { mediaUrl } from "@/lib/api";
import { useAuth } from "@/contexts/AuthContext";
import { Layout } from "@/layout/Layout";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Heart, Eye, Crown, Lock, Send, Trash2 } from "lucide-react";
import { toast } from "sonner";
import { Link } from "react-router-dom";
import VideoPlayer from "@/components/VideoPlayer";

export default function Watch() {
  const { id } = useParams();
  const { user } = useAuth();
  const [video, setVideo] = useState(null);
  const [recs, setRecs] = useState([]);
  const [comments, setComments] = useState([]);
  const [comment, setComment] = useState("");
  const [resolution, setResolution] = useState(null);
  const [allowDownload, setAllowDownload] = useState(false);
  const videoRef = useRef(null);

  const load = async () => {
    const { data } = await api.get(`/videos/${id}`);
    setVideo(data);
    if (data.renditions?.length && !resolution) {
      setResolution(data.renditions[data.renditions.length - 1].resolution);
    }
  };

  useEffect(() => {
    load();
    api.get(`/videos/${id}/recommendations?limit=15`).then((r) => setRecs(r.data));
    api.get(`/videos/${id}/comments`).then((r) => setComments(r.data));
    api.get("/site/player-config").then((r) => setAllowDownload(!!r.data.allow_video_download)).catch(() => {});
    api.post(`/videos/${id}/view`).catch(() => {});
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id]);

  const currentRendition = video?.renditions?.find((r) => r.resolution === resolution) || video?.renditions?.[0];

  const submitComment = async (e) => {
    e.preventDefault();
    if (!comment.trim()) return;
    try {
      const { data } = await api.post(`/videos/${id}/comments`, { content: comment });
      setComments([data, ...comments]);
      setComment("");
    } catch (err) {
      toast.error(err.response?.data?.detail || "Comment failed");
    }
  };

  const toggleLike = async () => {
    if (!user) return toast.error("Login required");
    const { data } = await api.post(`/videos/${id}/like`);
    setVideo({ ...video, likes: data.liked ? [...(video.likes || []), user.id] : (video.likes || []).filter((x) => x !== user.id) });
  };

  const delComment = async (cid) => {
    await api.delete(`/comments/${cid}`);
    setComments(comments.filter((c) => c.id !== cid));
  };

  if (!video) return <Layout><div className="text-zinc-500">Loading...</div></Layout>;

  const isLocked = video.locked || (video.access_tier === "pro" && !user?.is_pro);

  return (
    <Layout recommendations={recs}>
      <div data-testid="watch-page">
        <div className="aspect-video bg-black rounded-lg overflow-hidden relative">
          {isLocked ? (
            <div className="absolute inset-0 flex flex-col items-center justify-center bg-zinc-950" data-testid="locked-view">
              <Lock size={48} className="text-rose-500 mb-3" />
              <h3 className="text-xl font-semibold mb-1">PRO content</h3>
              <p className="text-zinc-400 mb-4">Upgrade to PRO to watch this video</p>
              <Link to="/pro"><Button className="pro-gradient text-white border-0">Upgrade Now</Button></Link>
            </div>
          ) : currentRendition ? (
            <VideoPlayer
              video={video}
              currentRendition={currentRendition}
              resolution={resolution}
              setResolution={setResolution}
              allowDownload={allowDownload}
            />
          ) : (
            <div className="absolute inset-0 flex items-center justify-center text-zinc-500">
              Video is {video.status}... ({video.progress}%)
            </div>
          )}
        </div>

        <div className="flex items-center justify-between mt-5 mb-2">
          <h1 className="text-2xl sm:text-3xl font-bold font-heading">{video.title}</h1>
          {video.access_tier === "pro" && <span className="pro-gradient text-white text-xs font-semibold px-3 py-1 rounded-md flex items-center gap-1"><Crown size={12} /> PRO</span>}
        </div>

        <div className="flex flex-wrap items-center gap-4 text-zinc-500 mb-4">
          <span className="flex items-center gap-1.5"><Eye size={14} /> {video.views} views</span>
          <button onClick={toggleLike} className="flex items-center gap-1.5 hover:text-rose-400 transition" data-testid="like-btn">
            <Heart size={14} className={user && video.likes?.includes(user.id) ? "fill-rose-500 text-rose-500" : ""} />
            {video.likes?.length || 0}
          </button>
          <Link to={`/profile/${video.uploader_id}`} className="hover:text-zinc-200">@{video.uploader_username}</Link>
        </div>

        {video.description && (
          <div className="bg-zinc-900 border border-zinc-800 rounded-lg p-4 mb-6 text-zinc-300 whitespace-pre-line">{video.description}</div>
        )}

        {video.tags?.length > 0 && (
          <div className="flex flex-wrap gap-2 mb-6">
            {video.tags.map((t) => <span key={t} className="text-xs bg-zinc-800 text-zinc-300 px-2 py-1 rounded">#{t}</span>)}
          </div>
        )}

        {/* Comments */}
        <div className="mt-8" data-testid="comments-section">
          <h2 className="text-xl font-semibold mb-4">Comments ({comments.length})</h2>
          {user ? (
            <form onSubmit={submitComment} className="flex gap-2 mb-6">
              <Textarea value={comment} onChange={(e) => setComment(e.target.value)} placeholder="Add a comment" className="bg-zinc-900 border-zinc-800" data-testid="comment-input" />
              <Button type="submit" className="pro-gradient text-white border-0 self-end" data-testid="comment-submit"><Send size={14} /></Button>
            </form>
          ) : (
            <p className="text-zinc-500 mb-4">Sign in to comment.</p>
          )}
          <div className="space-y-3">
            {comments.map((c) => (
              <div key={c.id} className="flex gap-3 bg-zinc-900 border border-zinc-800 rounded-lg p-3" data-testid={`comment-${c.id}`}>
                <div className="h-10 w-10 rounded-full bg-zinc-800 flex-shrink-0 overflow-hidden">
                  {c.avatar_url && <img src={mediaUrl(c.avatar_url)} alt="" className="w-full h-full object-cover" />}
                </div>
                <div className="flex-1">
                  <div className="flex items-center justify-between">
                    <span className="font-semibold text-sm">@{c.username}</span>
                    {(user?.id === c.user_id || user?.role === "admin") && (
                      <button onClick={() => delComment(c.id)} className="text-zinc-500 hover:text-red-400"><Trash2 size={14} /></button>
                    )}
                  </div>
                  <p className="text-zinc-300 mt-1 whitespace-pre-line">{c.content}</p>
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>
    </Layout>
  );
}
