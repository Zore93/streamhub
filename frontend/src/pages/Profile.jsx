import React, { useEffect, useMemo, useState } from "react";
import { useParams, Link } from "react-router-dom";
import api, { mediaUrl } from "@/lib/api";
import { useAuth } from "@/contexts/AuthContext";
import { useT } from "@/contexts/LanguageContext";
import VideoCard from "@/components/VideoCard";
import FramedAvatar from "@/components/FramedAvatar";
import { Button } from "@/components/ui/button";
import { Camera, Crown, Trash2, Pencil, Coins, Sparkles } from "lucide-react";
import { toast } from "sonner";

export default function Profile() {
  const { id } = useParams();
  const { user, setUser } = useAuth();
  const { t } = useT();
  const [profile, setProfile] = useState(null);
  const [videos, setVideos] = useState([]);
  const [tab, setTab] = useState("videos"); // videos | frames
  const [allFrames, setAllFrames] = useState([]);

  useEffect(() => {
    let alive = true;
    Promise.all([
      api.get(`/users/${id}`),
      api.get(`/users/${id}/videos`),
      api.get("/shop/frames").catch(() => ({ data: [] })),
    ]).then(([p, v, f]) => {
      if (!alive) return;
      setProfile(p.data);
      setVideos(v.data);
      setAllFrames(f.data || []);
    });
    return () => { alive = false; };
  }, [id]);

  const isMe = user?.id === id;

  const uploadFile = async (file, kind) => {
    const fd = new FormData();
    fd.append("file", file);
    const { data } = await api.post(`/users/me/${kind}`, fd);
    setProfile({ ...profile, [`${kind}_url`]: data[`${kind}_url`] });
    setUser({ ...user, [`${kind}_url`]: data[`${kind}_url`] });
    toast.success(`${kind} updated`);
  };

  const deleteVideo = async (vid) => {
    if (!window.confirm(t("profile.confirmDelete"))) return;
    await api.delete(`/videos/${vid}`);
    setVideos(videos.filter((v) => v.id !== vid));
    toast.success(t("profile.deleted"));
  };

  const selectedFrame = useMemo(
    () => profile?.selected_frame || allFrames.find((f) => f.id === profile?.selected_frame_id) || null,
    [profile, allFrames],
  );

  const applyFrame = async (frameId) => {
    const { data } = await api.post("/users/me/selected-frame", { frame_id: frameId });
    setUser(data);
    setProfile((p) => ({ ...p, selected_frame_id: data.selected_frame_id, selected_frame: data.selected_frame }));
    toast.success(frameId ? "Cadru aplicat" : "Cadru eliminat");
  };

  if (!profile) return <div className="text-zinc-500">{t("page.loading")}</div>;

  const ownedFrames = allFrames.filter((f) => (profile.owned_frames || []).includes(f.id));

  return (
    <div data-testid="profile-page">
      <div className="rounded-xl overflow-hidden bg-zinc-900 mb-6 relative">
        <div className="h-32 sm:h-48 bg-gradient-to-br from-zinc-800 to-zinc-900 relative">
          {profile.cover_url && <img src={mediaUrl(profile.cover_url)} alt="" className="w-full h-full object-cover" />}
          {isMe && (
            <label className="absolute top-3 right-3 bg-black/70 text-white px-3 py-1.5 rounded-md text-xs flex items-center gap-1 cursor-pointer hover:bg-black/90" data-testid="upload-cover-btn">
              <Camera size={12} /> {t("profile.changeCover")}
              <input type="file" accept="image/*" className="hidden" onChange={(e) => e.target.files?.[0] && uploadFile(e.target.files[0], "cover")} />
            </label>
          )}
        </div>
        <div className="px-4 sm:px-6 pb-6 flex items-end gap-4 -mt-12 flex-wrap">
          <div className="relative">
            <FramedAvatar
              src={profile.avatar_url}
              username={profile.username}
              size={88}
              frame={selectedFrame}
              data-testid="profile-avatar"
            />
            {isMe && (
              <label className="absolute -bottom-1 -right-1 bg-rose-500 hover:bg-rose-600 text-white p-1.5 rounded-md cursor-pointer z-10" data-testid="upload-avatar-btn">
                <Camera size={12} />
                <input type="file" accept="image/*" className="hidden" onChange={(e) => e.target.files?.[0] && uploadFile(e.target.files[0], "avatar")} />
              </label>
            )}
          </div>
          <div className="mb-2 flex-1 min-w-0">
            <div className="flex items-center gap-2 flex-wrap">
              <h1 className="text-2xl font-bold font-heading">@{profile.username}</h1>
              {profile.is_pro && <span className="pro-gradient text-white text-xs font-semibold px-2 py-1 rounded inline-flex items-center gap-1"><Crown size={10} /> PRO</span>}
              {isMe && (
                <span
                  className="inline-flex items-center gap-1 bg-amber-500/15 text-amber-300 border border-amber-500/40 text-xs font-semibold px-2 py-1 rounded"
                  data-testid="profile-coins"
                  title="Monede acumulate"
                >
                  <Coins size={12} /> {profile.coins || 0}
                </span>
              )}
            </div>
            {isMe && profile.email && (
              <p className="text-zinc-500 text-sm" data-testid="profile-email">{profile.email}</p>
            )}
            {profile.bio && <p className="text-zinc-400 text-sm mt-1">{profile.bio}</p>}
          </div>
        </div>
      </div>

      {/* Tabs */}
      <div className="flex gap-2 mb-4 flex-wrap" role="tablist">
        <button
          data-testid="tab-videos"
          className={`px-3 py-1.5 rounded-md text-sm font-medium transition-colors ${tab === "videos" ? "bg-rose-500 text-white" : "bg-zinc-900 text-zinc-300 hover:bg-zinc-800"}`}
          onClick={() => setTab("videos")}
        >
          {t("profile.videos")} ({videos.length})
        </button>
        {isMe && (
          <button
            data-testid="tab-frames"
            className={`px-3 py-1.5 rounded-md text-sm font-medium inline-flex items-center gap-1.5 transition-colors ${tab === "frames" ? "bg-rose-500 text-white" : "bg-zinc-900 text-zinc-300 hover:bg-zinc-800"}`}
            onClick={() => setTab("frames")}
          >
            <Sparkles size={14} /> Cadre
          </button>
        )}
      </div>

      {tab === "videos" && (
        <div className="grid grid-cols-2 sm:grid-cols-2 lg:grid-cols-3 gap-3 sm:gap-6">
          {videos.map((v) => (
            <div key={v.id} className="relative">
              <VideoCard v={v} />
              {isMe && (
                <div className="absolute top-2 left-2 flex gap-1">
                  <Link to={`/edit-video/${v.id}`}>
                    <Button size="sm" variant="secondary" className="h-7" data-testid={`edit-video-${v.id}`}><Pencil size={12} /></Button>
                  </Link>
                  <Button size="sm" variant="destructive" onClick={() => deleteVideo(v.id)} className="h-7" data-testid={`delete-video-${v.id}`}>
                    <Trash2 size={12} />
                  </Button>
                </div>
              )}
            </div>
          ))}
          {videos.length === 0 && <p className="text-zinc-500 col-span-3">{t("page.empty")}</p>}
        </div>
      )}

      {tab === "frames" && isMe && (
        <div>
          <div className="flex items-center justify-between mb-4 flex-wrap gap-2">
            <p className="text-sm text-zinc-400">
              Aplică un cadru pe avatarul tău. Cumpără cadre noi din{" "}
              <Link to="/shop" className="text-rose-400 hover:underline">magazin</Link>.
            </p>
            <Button
              variant="outline"
              size="sm"
              onClick={() => applyFrame(null)}
              data-testid="clear-frame-btn"
            >
              Fără cadru
            </Button>
          </div>
          <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 gap-4">
            {ownedFrames.length === 0 && (
              <p className="text-zinc-500 col-span-full">
                Nu deții niciun cadru. Vizitează{" "}
                <Link to="/shop" className="text-rose-400 hover:underline">magazinul</Link>{" "}
                pentru a cumpăra cu monedele tale.
              </p>
            )}
            {ownedFrames.map((f) => {
              const selected = profile.selected_frame_id === f.id;
              return (
                <div
                  key={f.id}
                  className={`rounded-lg p-3 bg-zinc-900 border ${selected ? "border-rose-500" : "border-zinc-800"} flex flex-col items-center gap-2`}
                  data-testid={`owned-frame-${f.id}`}
                >
                  <FramedAvatar
                    src={profile.avatar_url}
                    username={profile.username}
                    size={84}
                    frame={f}
                  />
                  <div className="text-sm font-medium text-center text-zinc-100">{f.name}</div>
                  <RarityBadge rarity={f.rarity} />
                  <Button
                    size="sm"
                    className="w-full"
                    variant={selected ? "secondary" : "default"}
                    onClick={() => applyFrame(selected ? null : f.id)}
                    data-testid={`apply-frame-${f.id}`}
                  >
                    {selected ? "Aplicat" : "Aplică"}
                  </Button>
                </div>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
}

function RarityBadge({ rarity }) {
  const colors = {
    common: "bg-zinc-800 text-zinc-300 border-zinc-700",
    rare: "bg-blue-500/15 text-blue-300 border-blue-500/40",
    epic: "bg-purple-500/15 text-purple-300 border-purple-500/40",
    legendary: "bg-amber-500/15 text-amber-300 border-amber-500/40",
  };
  return (
    <span className={`text-[10px] font-semibold uppercase tracking-wide px-1.5 py-0.5 rounded border ${colors[rarity] || colors.common}`}>
      {rarity}
    </span>
  );
}
