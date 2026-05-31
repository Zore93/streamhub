import React, { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import api, { mediaUrl } from "@/lib/api";
import { useAuth } from "@/contexts/AuthContext";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Progress } from "@/components/ui/progress";
import { toast } from "sonner";

export default function Upload() {
  const { user } = useAuth();
  const nav = useNavigate();
  const [file, setFile] = useState(null);
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [tags, setTags] = useState("");
  const [categories, setCategories] = useState([]);
  const [categoryId, setCategoryId] = useState("none");
  const [accessTier, setAccessTier] = useState("free");
  const [busy, setBusy] = useState(false);
  const [uploadedVideo, setUploadedVideo] = useState(null);
  const [progress, setProgress] = useState(0);
  const [pollProgress, setPollProgress] = useState(0);

  useEffect(() => {
    api.get("/categories").then((r) => setCategories(r.data));
  }, []);

  useEffect(() => {
    if (!uploadedVideo || uploadedVideo.status === "ready") return;
    const i = setInterval(async () => {
      try {
        const { data } = await api.get(`/videos/${uploadedVideo.id}`);
        setUploadedVideo(data);
        setPollProgress(data.progress || 0);
        if (data.status === "ready" || data.status === "failed") {
          clearInterval(i);
        }
      } catch {}
    }, 2500);
    return () => clearInterval(i);
  }, [uploadedVideo?.id, uploadedVideo?.status]);

  const submit = async (e) => {
    e.preventDefault();
    if (!file) {
      toast.error("Pick a video file");
      return;
    }
    setBusy(true);
    setProgress(0);
    const fd = new FormData();
    fd.append("file", file);
    fd.append("title", title);
    fd.append("description", description);
    fd.append("tags", tags);
    if (categoryId && categoryId !== "none") fd.append("category_id", categoryId);
    fd.append("access_tier", accessTier);
    try {
      const { data } = await api.post("/videos/upload", fd, {
        headers: { "Content-Type": "multipart/form-data" },
        onUploadProgress: (e) => setProgress(Math.round((e.loaded / (e.total || 1)) * 100)),
      });
      toast.success("Upload complete. Processing...");
      setUploadedVideo(data);
    } catch (err) {
      toast.error(err.response?.data?.detail || "Upload failed");
    } finally {
      setBusy(false);
    }
  };

  const pickThumbnail = async (rel) => {
    const { data } = await api.patch(`/videos/${uploadedVideo.id}`, { thumbnail_url: rel });
    setUploadedVideo(data);
    toast.success("Thumbnail set");
  };

  if (!user) {
    return <div className="text-zinc-400">Please log in to upload.</div>;
  }

  if (uploadedVideo) {
    return (
      <div className="max-w-3xl mx-auto" data-testid="upload-progress">
        <h1 className="text-3xl font-bold font-heading mb-6">Processing your video</h1>
        <div className="bg-zinc-900 border border-zinc-800 rounded-xl p-6">
          <div className="mb-4 font-semibold">{uploadedVideo.title}</div>
          <div className="text-sm text-zinc-500 mb-2">Status: <span className="text-zinc-200">{uploadedVideo.status}</span> ({pollProgress}%)</div>
          <Progress value={pollProgress} className="h-2" />
          {uploadedVideo.status === "ready" && uploadedVideo.thumbnail_options?.length > 0 && (
            <>
              <div className="mt-6 mb-2 text-sm font-semibold">Choose a thumbnail (10 generated):</div>
              <div className="grid grid-cols-5 gap-2">
                {uploadedVideo.thumbnail_options.map((t, i) => (
                  <button
                    key={i}
                    onClick={() => pickThumbnail(t)}
                    className={`rounded-md overflow-hidden border-2 ${uploadedVideo.thumbnail_url === t ? "border-rose-500" : "border-transparent"}`}
                    data-testid={`thumb-option-${i}`}
                  >
                    <img src={mediaUrl(t)} alt="" className="w-full aspect-video object-cover" />
                  </button>
                ))}
              </div>
              <Button className="mt-6 pro-gradient text-white border-0" onClick={() => nav(`/watch/${uploadedVideo.id}`)} data-testid="goto-video-btn">
                View Video
              </Button>
            </>
          )}
          {uploadedVideo.status === "failed" && (
            <div className="text-red-400 mt-4">Processing failed: {uploadedVideo.error}</div>
          )}
        </div>
      </div>
    );
  }

  return (
    <div className="max-w-2xl mx-auto" data-testid="upload-page">
      <h1 className="text-3xl font-bold font-heading mb-6">Upload Video</h1>
      <form onSubmit={submit} className="space-y-4 bg-zinc-900 border border-zinc-800 rounded-xl p-6">
        <div>
          <Label>Video file</Label>
          <Input type="file" accept="video/*" onChange={(e) => setFile(e.target.files?.[0])} className="bg-zinc-950 border-zinc-800" required data-testid="upload-file" />
        </div>
        <div>
          <Label>Title</Label>
          <Input value={title} onChange={(e) => setTitle(e.target.value)} className="bg-zinc-950 border-zinc-800" required data-testid="upload-title" />
        </div>
        <div>
          <Label>Description</Label>
          <Textarea value={description} onChange={(e) => setDescription(e.target.value)} className="bg-zinc-950 border-zinc-800" data-testid="upload-description" />
        </div>
        <div>
          <Label>Tags (comma-separated)</Label>
          <Input value={tags} onChange={(e) => setTags(e.target.value)} className="bg-zinc-950 border-zinc-800" data-testid="upload-tags" />
        </div>
        <div>
          <Label>Category</Label>
          <Select value={categoryId} onValueChange={setCategoryId}>
            <SelectTrigger className="bg-zinc-950 border-zinc-800" data-testid="upload-category"><SelectValue placeholder="Select" /></SelectTrigger>
            <SelectContent>
              <SelectItem value="none">None</SelectItem>
              {categories.map((c) => <SelectItem key={c.id} value={c.id}>{c.name}</SelectItem>)}
            </SelectContent>
          </Select>
        </div>
        <div>
          <Label>Access</Label>
          <Select value={accessTier} onValueChange={setAccessTier}>
            <SelectTrigger className="bg-zinc-950 border-zinc-800" data-testid="upload-access"><SelectValue /></SelectTrigger>
            <SelectContent>
              <SelectItem value="free">Everyone (free)</SelectItem>
              <SelectItem value="pro">PRO users only</SelectItem>
            </SelectContent>
          </Select>
        </div>
        {busy && <Progress value={progress} className="h-2" />}
        <Button type="submit" disabled={busy} className="w-full pro-gradient text-white border-0" data-testid="upload-submit">
          {busy ? `Uploading ${progress}%...` : "Upload"}
        </Button>
      </form>
    </div>
  );
}
