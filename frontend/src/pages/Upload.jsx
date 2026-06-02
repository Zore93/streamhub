import React, { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import api from "@/lib/api";
import { useAuth } from "@/contexts/AuthContext";
import { useT } from "@/contexts/LanguageContext";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Progress } from "@/components/ui/progress";
import { Loader2, Home as HomeIcon } from "lucide-react";
import { toast } from "sonner";

export default function Upload() {
  const { user } = useAuth();
  const { t, siteCfg } = useT();
  const nav = useNavigate();
  const [file, setFile] = useState(null);
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [tags, setTags] = useState("");
  const [categories, setCategories] = useState([]);
  const [categoryId, setCategoryId] = useState("none");
  const [accessTier, setAccessTier] = useState("free");
  const [isShort, setIsShort] = useState(false);
  const [busy, setBusy] = useState(false);
  const [uploadedVideo, setUploadedVideo] = useState(null);
  const [progress, setProgress] = useState(0);

  useEffect(() => {
    api.get("/categories").then((r) => setCategories(r.data));
  }, []);

  const shortsMax = siteCfg?.shorts_max_duration_sec ?? 60;

  const submit = async (e) => {
    e.preventDefault();
    if (!file) {
      toast.error(t("upload.file"));
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
    fd.append("is_short", String(isShort));
    try {
      const { data } = await api.post("/videos/upload", fd, {
        headers: { "Content-Type": "multipart/form-data" },
        onUploadProgress: (e) => setProgress(Math.round((e.loaded / (e.total || 1)) * 100)),
      });
      toast.success(t("upload.complete"));
      setUploadedVideo(data);
    } catch (err) {
      toast.error(err.response?.data?.detail || "Upload failed");
    } finally {
      setBusy(false);
    }
  };

  if (!user) {
    return <div className="text-zinc-400">{t("comments.signInToComment")}</div>;
  }

  // Once upload is accepted, show "processing in background" page and let user
  // navigate away. The transcoder keeps running server-side.
  if (uploadedVideo) {
    return (
      <div className="max-w-xl mx-auto" data-testid="upload-success">
        <div className="bg-zinc-900 border border-zinc-800 rounded-xl p-8 text-center">
          <Loader2 size={42} className="text-rose-500 mx-auto mb-4 animate-spin" />
          <h1 className="text-2xl font-bold font-heading mb-2">{t("upload.processing.title")}</h1>
          <p className="text-zinc-400 mb-6">{t("upload.processing.body")}</p>
          <div className="flex flex-col sm:flex-row gap-2 justify-center">
            <Button
              onClick={() => nav(`/watch/${uploadedVideo.id}`)}
              className="pro-gradient text-white border-0"
              data-testid="goto-video-btn"
            >
              {t("upload.viewVideo")}
            </Button>
            <Link to="/">
              <Button variant="outline" className="border-zinc-700 hover:bg-zinc-800 w-full sm:w-auto" data-testid="goto-home-btn">
                <HomeIcon size={14} className="mr-2" /> {t("upload.continueBrowsing")}
              </Button>
            </Link>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="max-w-2xl mx-auto" data-testid="upload-page">
      <h1 className="text-3xl font-bold font-heading mb-6">{t("upload.title")}</h1>
      <form onSubmit={submit} className="space-y-4 bg-zinc-900 border border-zinc-800 rounded-xl p-6">
        <div>
          <Label>{t("upload.file")}</Label>
          <Input type="file" accept="video/*" onChange={(e) => setFile(e.target.files?.[0])} className="bg-zinc-950 border-zinc-800" required data-testid="upload-file" />
        </div>
        <div>
          <Label>{t("upload.titleField")}</Label>
          <Input value={title} onChange={(e) => setTitle(e.target.value)} className="bg-zinc-950 border-zinc-800" required data-testid="upload-title" />
        </div>
        <div>
          <Label>{t("upload.description")}</Label>
          <Textarea value={description} onChange={(e) => setDescription(e.target.value)} className="bg-zinc-950 border-zinc-800" data-testid="upload-description" />
        </div>
        <div>
          <Label>{t("upload.tags")}</Label>
          <Input value={tags} onChange={(e) => setTags(e.target.value)} className="bg-zinc-950 border-zinc-800" data-testid="upload-tags" />
        </div>
        <div>
          <Label>{t("upload.category")}</Label>
          <Select value={categoryId} onValueChange={setCategoryId}>
            <SelectTrigger className="bg-zinc-950 border-zinc-800" data-testid="upload-category"><SelectValue placeholder="Select" /></SelectTrigger>
            <SelectContent>
              <SelectItem value="none">{t("upload.categoryNone")}</SelectItem>
              {categories.map((c) => <SelectItem key={c.id} value={c.id}>{c.name}</SelectItem>)}
            </SelectContent>
          </Select>
        </div>
        <div>
          <Label>{t("upload.access")}</Label>
          <Select value={accessTier} onValueChange={setAccessTier}>
            <SelectTrigger className="bg-zinc-950 border-zinc-800" data-testid="upload-access"><SelectValue /></SelectTrigger>
            <SelectContent>
              <SelectItem value="free">{t("upload.access.free")}</SelectItem>
              <SelectItem value="pro">{t("upload.access.pro")}</SelectItem>
            </SelectContent>
          </Select>
        </div>
        <div className="flex items-start justify-between bg-zinc-950 border border-zinc-800 rounded-md p-3">
          <div className="pr-4">
            <Label className="block">{t("upload.isShort")}</Label>
            <p className="text-xs text-zinc-500 mt-1">{t("upload.isShort.help", null, { dur: shortsMax })}</p>
          </div>
          <Switch checked={isShort} onCheckedChange={setIsShort} data-testid="upload-is-short" />
        </div>
        {busy && <Progress value={progress} className="h-2" />}
        <Button type="submit" disabled={busy} className="w-full pro-gradient text-white border-0" data-testid="upload-submit">
          {busy ? `${t("upload.busy")} ${progress}%...` : t("upload.btn")}
        </Button>
      </form>
    </div>
  );
}
