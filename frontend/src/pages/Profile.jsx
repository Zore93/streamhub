import React, { useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import api, { mediaUrl } from "@/lib/api";
import { useAuth } from "@/contexts/AuthContext";
import { useT } from "@/contexts/LanguageContext";
import VideoCard from "@/components/VideoCard";
import { Button } from "@/components/ui/button";
import { Camera, Crown, Trash2, Pencil } from "lucide-react";
import { Link } from "react-router-dom";
import { toast } from "sonner";

export default function Profile() {
  const { id } = useParams();
  const { user, setUser } = useAuth();
  const { t } = useT();
  const [profile, setProfile] = useState(null);
  const [videos, setVideos] = useState([]);

  const load = async () => {
    const { data } = await api.get(`/users/${id}`);
    setProfile(data);
    const { data: vids } = await api.get(`/users/${id}/videos`);
    setVideos(vids);
  };

  useEffect(() => { load(); }, [id]);

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

  if (!profile) return <div className="text-zinc-500">{t("page.loading")}</div>;

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
            <div className="h-24 w-24 rounded-full bg-zinc-800 border-4 border-zinc-950 overflow-hidden">
              {profile.avatar_url && <img src={mediaUrl(profile.avatar_url)} alt="" className="w-full h-full object-cover" />}
            </div>
            {isMe && (
              <label className="absolute bottom-0 right-0 bg-rose-500 hover:bg-rose-600 text-white p-1.5 rounded-full cursor-pointer" data-testid="upload-avatar-btn">
                <Camera size={12} />
                <input type="file" accept="image/*" className="hidden" onChange={(e) => e.target.files?.[0] && uploadFile(e.target.files[0], "avatar")} />
              </label>
            )}
          </div>
          <div className="mb-2">
            <div className="flex items-center gap-2">
              <h1 className="text-2xl font-bold font-heading">@{profile.username}</h1>
              {profile.is_pro && <span className="pro-gradient text-white text-xs font-semibold px-2 py-1 rounded inline-flex items-center gap-1"><Crown size={10} /> PRO</span>}
            </div>
            <p className="text-zinc-500 text-sm">{profile.email}</p>
          </div>
        </div>
      </div>

      <h2 className="text-2xl font-semibold mb-4">{t("profile.videos")} ({videos.length})</h2>
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
    </div>
  );
}
