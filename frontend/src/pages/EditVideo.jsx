import React, { useEffect, useState } from "react";
import { useParams, useNavigate } from "react-router-dom";
import api, { mediaUrl } from "@/lib/api";
import { useAuth } from "@/contexts/AuthContext";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Trash2, Plus, ArrowLeft } from "lucide-react";
import { toast } from "sonner";

export default function EditVideo() {
  const { id } = useParams();
  const { user } = useAuth();
  const nav = useNavigate();
  const [v, setV] = useState(null);
  const [cats, setCats] = useState([]);
  const [subFile, setSubFile] = useState(null);
  const [subLang, setSubLang] = useState("en");
  const [subLabel, setSubLabel] = useState("English");

  const load = async () => {
    const { data } = await api.get(`/videos/${id}`);
    setV(data);
  };
  useEffect(() => { load(); api.get("/categories").then((r) => setCats(r.data)); }, [id]);

  if (!v) return <div className="text-zinc-500">Loading...</div>;
  if (user && v.uploader_id !== user.id && user.role !== "admin") {
    return <div className="text-zinc-400">You can only edit your own videos.</div>;
  }

  const save = async (patch) => {
    const { data } = await api.patch(`/videos/${id}`, patch);
    setV(data); toast.success("Saved");
  };

  const addSubtitle = async (e) => {
    e.preventDefault();
    if (!subFile) return toast.error("Pick a subtitle file");
    if ((v.subtitles || []).length >= 10) return toast.error("Maximum 10 subtitles");
    const fd = new FormData();
    fd.append("file", subFile);
    fd.append("language", subLang);
    fd.append("label", subLabel);
    try {
      await api.post(`/videos/${id}/subtitles`, fd, { headers: { "Content-Type": "multipart/form-data" } });
      toast.success("Subtitle added");
      setSubFile(null);
      await load();
    } catch (err) {
      toast.error(err.response?.data?.detail || "Upload failed");
    }
  };

  const delSubtitle = async (sid) => {
    if (!window.confirm("Delete this subtitle?")) return;
    await api.delete(`/videos/${id}/subtitles/${sid}`);
    await load();
  };

  return (
    <div className="max-w-3xl mx-auto" data-testid="edit-video-page">
      <Button variant="ghost" onClick={() => nav(-1)} className="mb-3"><ArrowLeft size={14} className="mr-2" /> Back</Button>
      <h1 className="text-3xl font-bold font-heading mb-6">Edit Video</h1>

      <div className="bg-zinc-900 border border-zinc-800 rounded-xl p-6 space-y-4">
        <div><Label>Title</Label><Input value={v.title} onChange={(e) => setV({ ...v, title: e.target.value })} onBlur={() => save({ title: v.title })} className="bg-zinc-950 border-zinc-800" data-testid="edit-title" /></div>
        <div><Label>Description</Label><Textarea value={v.description || ""} onChange={(e) => setV({ ...v, description: e.target.value })} onBlur={() => save({ description: v.description })} className="bg-zinc-950 border-zinc-800" data-testid="edit-description" /></div>
        <div><Label>Tags (comma separated)</Label>
          <Input value={(v.tags || []).join(", ")} onChange={(e) => setV({ ...v, tags: e.target.value.split(",").map((s) => s.trim()).filter(Boolean) })} onBlur={() => save({ tags: v.tags })} className="bg-zinc-950 border-zinc-800" /></div>
        <div>
          <Label>Category</Label>
          <Select value={v.category_id || "none"} onValueChange={(val) => { const c = val === "none" ? null : val; setV({ ...v, category_id: c }); save({ category_id: c }); }}>
            <SelectTrigger className="bg-zinc-950 border-zinc-800"><SelectValue /></SelectTrigger>
            <SelectContent>
              <SelectItem value="none">None</SelectItem>
              {cats.map((c) => <SelectItem key={c.id} value={c.id}>{c.name}</SelectItem>)}
            </SelectContent>
          </Select>
        </div>
        <div>
          <Label>Access</Label>
          <Select value={v.access_tier} onValueChange={(val) => { setV({ ...v, access_tier: val }); save({ access_tier: val }); }}>
            <SelectTrigger className="bg-zinc-950 border-zinc-800"><SelectValue /></SelectTrigger>
            <SelectContent>
              <SelectItem value="free">Everyone</SelectItem>
              <SelectItem value="pro">PRO only</SelectItem>
            </SelectContent>
          </Select>
        </div>
        {v.thumbnail_options?.length > 0 && (
          <div>
            <Label>Thumbnail</Label>
            <div className="grid grid-cols-5 gap-2 mt-2">
              {v.thumbnail_options.map((t, i) => (
                <button key={i} onClick={() => save({ thumbnail_url: t })} className={`rounded-md overflow-hidden border-2 ${v.thumbnail_url === t ? "border-rose-500" : "border-transparent"}`}>
                  <img src={mediaUrl(t)} alt="" className="w-full aspect-video object-cover" />
                </button>
              ))}
            </div>
          </div>
        )}
      </div>

      {/* Subtitles */}
      <div className="bg-zinc-900 border border-zinc-800 rounded-xl p-6 mt-6" data-testid="subtitles-section">
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-xl font-semibold font-heading">Subtitles</h2>
          <span className="text-xs text-zinc-500">{(v.subtitles || []).length}/10</span>
        </div>
        <form onSubmit={addSubtitle} className="grid grid-cols-1 sm:grid-cols-4 gap-2 items-end mb-4">
          <div className="sm:col-span-1"><Label>Language</Label><Input value={subLang} onChange={(e) => setSubLang(e.target.value)} placeholder="en" className="bg-zinc-950 border-zinc-800" /></div>
          <div className="sm:col-span-1"><Label>Label</Label><Input value={subLabel} onChange={(e) => setSubLabel(e.target.value)} placeholder="English" className="bg-zinc-950 border-zinc-800" /></div>
          <div className="sm:col-span-1"><Label>File (.srt/.ass)</Label><Input type="file" accept=".srt,.ass,.vtt" onChange={(e) => setSubFile(e.target.files?.[0])} className="bg-zinc-950 border-zinc-800" data-testid="sub-file" /></div>
          <Button type="submit" className="pro-gradient text-white border-0" data-testid="sub-add"><Plus size={14} className="mr-1" /> Add</Button>
        </form>
        <div className="space-y-2">
          {(v.subtitles || []).map((s) => (
            <div key={s.id} className="flex items-center justify-between bg-zinc-950 border border-zinc-800 rounded-md p-3" data-testid={`sub-${s.id}`}>
              <div>
                <span className="font-semibold">{s.label}</span>
                <span className="text-xs text-zinc-500 ml-2">({s.language} · {s.format})</span>
              </div>
              <Button size="sm" variant="destructive" onClick={() => delSubtitle(s.id)}><Trash2 size={14} /></Button>
            </div>
          ))}
          {(v.subtitles || []).length === 0 && <p className="text-zinc-500 text-sm">No subtitles. Upload .srt or .ass — we'll auto-convert to WebVTT for the player.</p>}
        </div>
      </div>
    </div>
  );
}
