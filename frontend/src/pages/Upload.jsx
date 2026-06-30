import React, { useEffect, useRef, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import api from "@/lib/api";
import { uploadVideoChunked } from "@/lib/chunkedUpload";
import { useAuth } from "@/contexts/AuthContext";
import { useT } from "@/contexts/LanguageContext";
import { categoryLabel } from "@/i18n";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Progress } from "@/components/ui/progress";
import { Loader2, Home as HomeIcon, X, Plus, CheckCircle2, AlertCircle, Pencil } from "lucide-react";
import { toast } from "sonner";

function humanSize(bytes) {
  if (!bytes) return "0 B";
  const u = ["B", "KB", "MB", "GB", "TB"];
  let i = 0; let n = bytes;
  while (n >= 1024 && i < u.length - 1) { n /= 1024; i++; }
  return `${n.toFixed(n < 10 ? 1 : 0)} ${u[i]}`;
}

export default function Upload() {
  const { user } = useAuth();
  const { t, siteCfg, lang } = useT();
  const nav = useNavigate();
  const [files, setFiles] = useState([]);        // staged files awaiting metadata
  const [tasks, setTasks] = useState([]);        // upload progress per file
  const [shared, setShared] = useState({
    description: "",
    tags: "",
    category_id: "none",
    access_tier: "free",
    is_short: false,
  });
  const [categories, setCategories] = useState([]);
  const [busy, setBusy] = useState(false);
  const abortRef = useRef([]);

  useEffect(() => {
    api.get("/categories").then((r) => setCategories(r.data)).catch(() => {});
  }, []);

  const shortsMax = siteCfg?.shorts_max_duration_sec ?? 60;
  const bulkEnabled = siteCfg?.bulk_upload_enabled ?? true;
  const concurrency = Math.max(1, Math.min(6, siteCfg?.bulk_upload_concurrency ?? 3));

  const addFiles = (newFiles) => {
    const list = Array.from(newFiles || []);
    const limit = bulkEnabled ? 50 : 1;
    setFiles((prev) => {
      const merged = [...prev];
      for (const f of list) {
        if (merged.length >= limit) break;
        // Strip extension for the default title
        const title = f.name.replace(/\.[^.]+$/, "").replace(/[._-]+/g, " ");
        merged.push({ id: `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`, file: f, title });
      }
      if (list.length + prev.length > limit) {
        toast.warning(`Limit ${limit} file(s) at once.`);
      }
      return merged;
    });
  };

  const removeStaged = (id) => setFiles((prev) => prev.filter((f) => f.id !== id));
  const updateTitle = (id, title) => setFiles((prev) => prev.map((f) => f.id === id ? { ...f, title } : f));

  /** Upload `files` with a concurrency cap; updates `tasks` reactively. */
  const startAll = async () => {
    if (!files.length) return toast.error("Choose at least one file.");
    setBusy(true);
    const queue = [...files];
    const initialTasks = queue.map((f) => ({
      id: f.id,
      filename: f.file.name,
      size: f.file.size,
      title: f.title,
      loaded: 0,
      status: "pending", // pending | uploading | processing | done | error
      message: "",
      video: null,
    }));
    setTasks(initialTasks);

    const runOne = async (entry) => {
      const updateTask = (patch) => setTasks((prev) => prev.map((p) => p.id === entry.id ? { ...p, ...patch } : p));
      try {
        updateTask({ status: "uploading" });
        const controller = new AbortController();
        abortRef.current.push({ id: entry.id, controller });
        const metadata = {
          title: entry.title || entry.file.name,
          description: shared.description,
          tags: shared.tags,
          category_id: shared.category_id === "none" ? null : shared.category_id,
          access_tier: shared.access_tier,
          is_short: shared.is_short,
        };
        const video = await uploadVideoChunked({
          file: entry.file,
          metadata,
          signal: controller.signal,
          onProgress: (loaded) => updateTask({ loaded }),
        });
        updateTask({ status: "done", video });
      } catch (err) {
        const msg = err?.response?.data?.detail || err?.message || "Upload failed";
        updateTask({ status: "error", message: msg });
      }
    };

    // Fixed-size worker pool
    const workers = Array.from({ length: concurrency }, async () => {
      while (queue.length) {
        const entry = queue.shift();
        if (entry) await runOne(entry);
      }
    });
    await Promise.all(workers);
    setBusy(false);
    setFiles([]);
    abortRef.current = [];
  };

  const cancelTask = (id) => {
    const found = abortRef.current.find((x) => x.id === id);
    if (found) found.controller.abort();
  };

  const cancelAll = () => {
    abortRef.current.forEach((x) => { try { x.controller.abort(); } catch (_e) { /* */ } });
  };

  if (!user) {
    return <div className="text-zinc-400">{t("comments.signInToComment")}</div>;
  }

  // After all uploads completed → show summary with edit links
  const allDoneOrErrored = tasks.length > 0 && tasks.every((t) => t.status === "done" || t.status === "error");

  if (allDoneOrErrored && !busy) {
    const success = tasks.filter((t) => t.status === "done");
    const failed = tasks.filter((t) => t.status === "error");
    return (
      <div className="max-w-3xl mx-auto" data-testid="upload-summary">
        <div className="bg-zinc-900 border border-zinc-800 rounded-xl p-6">
          <h1 className="text-2xl font-bold font-heading mb-4">Încărcare finalizată</h1>
          {success.length > 0 && (
            <div className="mb-4">
              <h2 className="text-sm font-semibold text-emerald-400 mb-2">
                {success.length} videoclip(e) procesate cu succes — poți edita fiecare:
              </h2>
              <div className="space-y-2">
                {success.map((t) => (
                  <div key={t.id} className="flex items-center justify-between bg-zinc-950 border border-zinc-800 rounded-md px-3 py-2" data-testid={`upload-done-${t.id}`}>
                    <div className="flex items-center gap-2 min-w-0">
                      <CheckCircle2 size={16} className="text-emerald-400 flex-shrink-0" />
                      <span className="truncate text-sm">{t.title}</span>
                    </div>
                    <div className="flex gap-2 flex-shrink-0">
                      <Link to={`/edit-video/${t.video?.id}`}>
                        <Button size="sm" variant="secondary" data-testid={`edit-uploaded-${t.id}`}>
                          <Pencil size={12} className="mr-1" /> Edit
                        </Button>
                      </Link>
                      <Link to={`/watch/${t.video?.slug || t.video?.id}`}>
                        <Button size="sm" variant="outline">Vizionează</Button>
                      </Link>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}
          {failed.length > 0 && (
            <div className="mb-4">
              <h2 className="text-sm font-semibold text-red-400 mb-2">{failed.length} eșuate:</h2>
              <div className="space-y-1">
                {failed.map((t) => (
                  <div key={t.id} className="flex items-center gap-2 text-sm text-red-300" data-testid={`upload-failed-${t.id}`}>
                    <AlertCircle size={14} /> <span className="truncate">{t.filename}</span>: <span className="text-xs text-zinc-400">{t.message}</span>
                  </div>
                ))}
              </div>
            </div>
          )}
          <div className="flex gap-2 flex-wrap mt-4">
            <Button onClick={() => { setTasks([]); setFiles([]); }} className="pro-gradient text-white border-0">
              Încarcă alte videoclipuri
            </Button>
            <Link to="/"><Button variant="outline"><HomeIcon size={14} className="mr-2" /> Acasă</Button></Link>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="max-w-3xl mx-auto" data-testid="upload-page">
      <h1 className="text-3xl font-bold font-heading mb-2">{t("upload.title")}</h1>
      {bulkEnabled && (
        <p className="text-zinc-400 text-sm mb-6">
          Poți selecta până la 50 de fișiere odată. Fiecare se încarcă în bucăți (chunked) cu progres separat — închiderea browserului întrerupe restul, dar bucățile deja trimise rămân pe server.
        </p>
      )}

      {/* File picker / drop zone */}
      <div className="bg-zinc-900 border border-zinc-800 rounded-xl p-6 mb-4">
        <label
          htmlFor="file-input"
          className="block border-2 border-dashed border-zinc-700 hover:border-rose-500 transition-colors rounded-lg p-8 text-center cursor-pointer"
          data-testid="upload-dropzone"
        >
          <Plus size={32} className="mx-auto text-zinc-500 mb-2" />
          <p className="text-zinc-300 font-medium">
            {bulkEnabled ? "Trage videoclipuri aici sau click pentru a selecta" : "Click pentru a selecta un videoclip"}
          </p>
          <p className="text-xs text-zinc-500 mt-1">
            Max {Math.round((siteCfg?.max_upload_size_mb ?? 1024) / 1024)} GB per fișier · {bulkEnabled ? `până la 50 odată · ${concurrency} simultan` : "1 odată"}
          </p>
          <input
            id="file-input"
            type="file"
            multiple={bulkEnabled}
            accept="video/*"
            className="hidden"
            onChange={(e) => addFiles(e.target.files)}
            data-testid="upload-file"
          />
        </label>
      </div>

      {/* Staged files w/ inline title editing */}
      {files.length > 0 && !busy && (
        <div className="bg-zinc-900 border border-zinc-800 rounded-xl p-4 mb-4 space-y-2" data-testid="upload-staged">
          {files.map((f, i) => (
            <div key={f.id} className="flex items-center gap-2 bg-zinc-950 border border-zinc-800 rounded-md p-2">
              <span className="text-xs text-zinc-500 w-6">#{i + 1}</span>
              <Input
                value={f.title}
                onChange={(e) => updateTitle(f.id, e.target.value)}
                className="bg-zinc-900 border-zinc-700 text-sm flex-1"
                placeholder="Titlu"
                data-testid={`staged-title-${f.id}`}
              />
              <span className="text-xs text-zinc-500">{humanSize(f.file.size)}</span>
              <button onClick={() => removeStaged(f.id)} className="text-zinc-500 hover:text-red-400 p-1" data-testid={`remove-${f.id}`}>
                <X size={14} />
              </button>
            </div>
          ))}
        </div>
      )}

      {/* Shared metadata applied to every file in the batch */}
      {files.length > 0 && !busy && (
        <div className="bg-zinc-900 border border-zinc-800 rounded-xl p-6 mb-4 space-y-4">
          <p className="text-xs text-zinc-500">
            Câmpurile de mai jos se aplică tuturor fișierelor încărcate. Le poți schimba individual ulterior prin „Edit” după upload.
          </p>
          <div>
            <Label>{t("upload.description")}</Label>
            <Textarea value={shared.description} onChange={(e) => setShared({ ...shared, description: e.target.value })} className="bg-zinc-950 border-zinc-800" data-testid="upload-description" />
          </div>
          <div>
            <Label>{t("upload.tags")}</Label>
            <Input value={shared.tags} onChange={(e) => setShared({ ...shared, tags: e.target.value })} className="bg-zinc-950 border-zinc-800" data-testid="upload-tags" />
          </div>
          <div>
            <Label>{t("upload.category")}</Label>
            <Select value={shared.category_id} onValueChange={(v) => setShared({ ...shared, category_id: v })}>
              <SelectTrigger className="bg-zinc-950 border-zinc-800" data-testid="upload-category"><SelectValue /></SelectTrigger>
              <SelectContent>
                <SelectItem value="none">{t("upload.categoryNone")}</SelectItem>
                {categories.map((c) => <SelectItem key={c.id} value={c.id}>{categoryLabel(c, lang)}</SelectItem>)}
              </SelectContent>
            </Select>
          </div>
          <div>
            <Label>{t("upload.access")}</Label>
            <Select value={shared.access_tier} onValueChange={(v) => setShared({ ...shared, access_tier: v })}>
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
            <Switch checked={shared.is_short} onCheckedChange={(v) => setShared({ ...shared, is_short: v })} data-testid="upload-is-short" />
          </div>
          <Button onClick={startAll} disabled={busy} className="w-full pro-gradient text-white border-0" data-testid="upload-submit">
            {busy ? <><Loader2 size={14} className="mr-2 animate-spin" /> Se încarcă...</> : `Încarcă ${files.length} videoclip${files.length === 1 ? "" : "e"}`}
          </Button>
        </div>
      )}

      {/* Live progress while uploads run */}
      {tasks.length > 0 && (
        <div className="bg-zinc-900 border border-zinc-800 rounded-xl p-4 space-y-2" data-testid="upload-tasks">
          <div className="flex items-center justify-between mb-1">
            <h3 className="text-sm font-semibold">Progres</h3>
            {busy && <Button size="sm" variant="ghost" onClick={cancelAll}>Anulează tot</Button>}
          </div>
          {tasks.map((t) => {
            const pct = t.size ? Math.min(100, Math.round((t.loaded / t.size) * 100)) : 0;
            return (
              <div key={t.id} className="bg-zinc-950 border border-zinc-800 rounded-md p-2" data-testid={`task-${t.id}`}>
                <div className="flex items-center justify-between text-sm">
                  <span className="truncate flex-1 min-w-0">{t.title}</span>
                  <span className="text-xs text-zinc-500 ml-2 flex-shrink-0">
                    {t.status === "uploading" && `${humanSize(t.loaded)} / ${humanSize(t.size)} · ${pct}%`}
                    {t.status === "done" && <span className="text-emerald-400">✓ Procesare în fundal</span>}
                    {t.status === "error" && <span className="text-red-400">✕ {t.message}</span>}
                    {t.status === "pending" && "în coadă..."}
                  </span>
                  {t.status === "uploading" && (
                    <button onClick={() => cancelTask(t.id)} className="ml-2 text-zinc-500 hover:text-red-400">
                      <X size={12} />
                    </button>
                  )}
                </div>
                {(t.status === "uploading" || t.status === "pending") && <Progress value={pct} className="h-1.5 mt-1" />}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
