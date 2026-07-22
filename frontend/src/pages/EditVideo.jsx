import React, { useEffect, useMemo, useState } from "react";
import { useParams, useNavigate } from "react-router-dom";
import api, { mediaUrl } from "@/lib/api";
import { useAuth } from "@/contexts/AuthContext";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Trash2, Plus, ArrowLeft, FileText, Star, StarOff, Sparkles, Check, X } from "lucide-react";
import { toast } from "sonner";

// Common subtitle languages — keeps the picker small but covers most cases.
// Used only as a fallback if /api/languages isn't reachable.
const COMMON_LANGS = [
  { code: "ro", label: "Română" },
  { code: "en", label: "English" },
  { code: "fr", label: "Français" },
  { code: "de", label: "Deutsch" },
  { code: "es", label: "Español" },
  { code: "it", label: "Italiano" },
  { code: "pt", label: "Português" },
  { code: "ja", label: "日本語" },
  { code: "ko", label: "한국어" },
  { code: "zh", label: "中文" },
  { code: "ru", label: "Русский" },
  { code: "hu", label: "Magyar" },
  { code: "tr", label: "Türkçe" },
  { code: "ar", label: "العربية" },
  { code: "other", label: "Other / custom" },
];

export default function EditVideo() {
  const { id } = useParams();
  const { user } = useAuth();
  const nav = useNavigate();
  const [v, setV] = useState(null);
  const [cats, setCats] = useState([]);
  const [allLangs, setAllLangs] = useState([]);
  const [subFile, setSubFile] = useState(null);
  const [subLang, setSubLang] = useState("ro");
  const [subLangCustom, setSubLangCustom] = useState("");
  const [subLabel, setSubLabel] = useState("Română");
  const [autoDetected, setAutoDetected] = useState(false);
  const [busy, setBusy] = useState(false);

  const load = async () => {
    const { data } = await api.get(`/videos/${id}`);
    setV(data);
  };
  useEffect(() => {
    load();
    api.get("/categories").then((r) => setCats(r.data));
    api.get("/languages").then((r) => setAllLangs(r.data)).catch(() => setAllLangs(COMMON_LANGS));
  }, [id]);

  // Auto-suggest label when language changes
  useEffect(() => {
    if (subLang === "other") return;
    const found = allLangs.find((l) => l.code === subLang) || COMMON_LANGS.find((l) => l.code === subLang);
    if (found) setSubLabel(found.label);
  }, [subLang, allLangs]);

  // Auto-detect language from filename when the user picks a subtitle file
  useEffect(() => {
    if (!subFile) { setAutoDetected(false); return; }
    const name = subFile.name.toLowerCase();
    // Lightweight client-side detection — full check runs server-side too.
    const PATTERNS = [
      ["ja", /\b(ja|jp|jpn|japanese)\b|jpsub|japsub/],
      ["ro", /\b(ro|rom|ron|romanian|romana)\b|rosub/],
      ["en", /\b(en|eng|english)\b|engsub/],
      ["es", /\b(es|esp|spa|spanish)\b|spasub/],
      ["fr", /\b(fr|fra|french|francais)\b|frasub/],
      ["de", /\b(de|deu|ger|german|deutsch)\b/],
      ["it", /\b(it|ita|italian|italiano)\b/],
      ["pt", /\b(pt|por|portuguese)\b/],
      ["ko", /\b(ko|kor|korean)\b/],
      ["zh", /\b(zh|chi|chn|chinese|mandarin)\b/],
      ["ru", /\b(ru|rus|russian)\b/],
      ["ar", /\b(ar|ara|arabic)\b/],
      ["tr", /\b(tr|tur|turkish)\b/],
      ["pl", /\b(pl|pol|polish)\b/],
      ["nl", /\b(nl|nld|dutch)\b/],
    ];
    const base = name.replace(/\.[^.]+$/, "").replace(/[._\-\[\]\(\)]+/g, " ");
    for (const [code, re] of PATTERNS) {
      if (re.test(base)) {
        setSubLang(code);
        setAutoDetected(true);
        return;
      }
    }
    setAutoDetected(false);
  }, [subFile]);


  const isShortVideo = useMemo(() => !!v?.is_short, [v]);

  if (!v) return <div className="text-zinc-500">Loading...</div>;
  if (user && v.uploader_id !== user.id && user.role !== "admin") {
    return <div className="text-zinc-400">You can only edit your own videos.</div>;
  }

  const save = async (patch) => {
    const { data } = await api.patch(`/videos/${id}`, patch);
    setV(data); toast.success("Saved");
  };

  const effectiveLang = () => {
    if (subLang === "other") return (subLangCustom || "").trim().toLowerCase().slice(0, 8);
    return subLang;
  };

  const addSubtitle = async (e) => {
    e.preventDefault();
    if (!subFile) return toast.error("Pick a subtitle file");
    if ((v.subtitles || []).length >= 10) return toast.error("Maximum 10 subtitles");
    const lang = effectiveLang();
    if (!lang) return toast.error("Pick or enter a language code");
    setBusy(true);
    const fd = new FormData();
    fd.append("file", subFile);
    fd.append("language", lang);
    fd.append("label", subLabel || lang.toUpperCase());
    try {
      await api.post(`/videos/${id}/subtitles`, fd, { headers: { "Content-Type": "multipart/form-data" } });
      toast.success("Subtitle added");
      setSubFile(null);
      // Reset the file input so the same file can be re-picked if needed
      const fileInput = document.querySelector('input[data-testid="sub-file"]');
      if (fileInput) fileInput.value = "";
      await load();
    } catch (err) {
      toast.error(err.response?.data?.detail || "Upload failed");
    } finally { setBusy(false); }
  };

  const delSubtitle = async (sid) => {
    if (!window.confirm("Delete this subtitle?")) return;
    await api.delete(`/videos/${id}/subtitles/${sid}`);
    await load();
  };

  const setDefaultSub = async (sid) => {
    // Re-order so the chosen sub is first — the player auto-shows the first track.
    const subs = v.subtitles || [];
    const idx = subs.findIndex((s) => s.id === sid);
    if (idx <= 0) return;
    const reordered = [subs[idx], ...subs.filter((_, i) => i !== idx)];
    await api.patch(`/videos/${id}`, { subtitles: reordered });
    await load();
    toast.success("Default subtitle updated");
  };

  const reextractEmbedded = async () => {
    setBusy(true);
    try {
      const { data } = await api.post(`/videos/${id}/extract-embedded-subs`);
      if (data.added > 0) {
        toast.success(`${data.added} subtitrare(i) noi extrase din fișierul sursă.`);
      } else if (data.extracted > 0) {
        toast.info(`${data.extracted} subtitrare(i) găsite, dar toate erau deja prezente.`);
      } else {
        toast.info(data.message || "Nicio subtitrare text găsită în sursă.");
      }
      await load();
    } catch (err) {
      toast.error(err.response?.data?.detail || "Re-extracting failed");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="max-w-3xl mx-auto" data-testid="edit-video-page">
      <Button variant="ghost" onClick={() => nav(-1)} className="mb-3"><ArrowLeft size={14} className="mr-2" /> Back</Button>
      <h1 className="text-3xl font-bold font-heading mb-6">Edit Video</h1>

      <div className="bg-zinc-900 border border-zinc-800 rounded-xl p-6 space-y-4">
        <div><Label>Title</Label><Input value={v.title} onChange={(e) => setV({ ...v, title: e.target.value })} onBlur={() => save({ title: v.title })} className="bg-zinc-950 border-zinc-800" data-testid="edit-title" /></div>
        <div><Label>Description</Label><Textarea value={v.description || ""} onChange={(e) => setV({ ...v, description: e.target.value })} onBlur={() => save({ description: v.description })} className="bg-zinc-950 border-zinc-800" data-testid="edit-description" /></div>
        <div>
          <div className="flex items-center justify-between mb-1">
            <Label>Sinopsis (SEO)</Label>
            <AiSynopsisButton videoId={v.id} onGenerated={(txt) => { setV({ ...v, synopsis: txt }); save({ synopsis: txt }); }} />
          </div>
          <Textarea
            rows={6}
            value={v.synopsis || ""}
            onChange={(e) => setV({ ...v, synopsis: e.target.value })}
            onBlur={() => save({ synopsis: v.synopsis })}
            placeholder="Rezumat detaliat al episodului — cel puțin 150 cuvinte unice pentru SEO. Ex: personaje, teme, evenimente cheie. NU copia-lipi de pe alt site."
            className="bg-zinc-950 border-zinc-800"
            data-testid="edit-synopsis"
          />
          <p className="text-xs text-zinc-500 mt-1">
            {(v.synopsis || "").split(/\s+/).filter(Boolean).length} cuvinte · min. 150 recomandat pentru Google
          </p>
        </div>
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
        <div className="flex items-center justify-between bg-zinc-950 border border-zinc-800 rounded-md p-3">
          <Label className="m-0">Marked as Shorts (vertical 9:16)</Label>
          <Switch
            checked={isShortVideo}
            onCheckedChange={(val) => { setV({ ...v, is_short: val }); save({ is_short: val }); }}
            data-testid="edit-is-short"
          />
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
        <div className="flex items-center justify-between mb-4 flex-wrap gap-2">
          <div className="flex items-center gap-2">
            <FileText size={18} className="text-rose-500" />
            <h2 className="text-xl font-semibold font-heading">Subtitles</h2>
          </div>
          <div className="flex items-center gap-2 flex-wrap">
            <Button
              type="button"
              size="sm"
              variant="outline"
              onClick={reextractEmbedded}
              disabled={busy}
              data-testid="reextract-embedded-btn"
              title="Re-run automatic extraction of subtitles embedded in the source .mkv/.mp4"
            >
              {busy ? "..." : "Re-extract embedded"}
            </Button>
            <span className="text-xs text-zinc-500">{(v.subtitles || []).length}/100</span>
          </div>
        </div>
        <form onSubmit={addSubtitle} className="grid grid-cols-1 sm:grid-cols-4 gap-2 items-end mb-4">
          <div className="sm:col-span-1">
            <Label>Language</Label>
            <Select value={subLang} onValueChange={setSubLang}>
              <SelectTrigger className="bg-zinc-950 border-zinc-800" data-testid="sub-lang"><SelectValue /></SelectTrigger>
              <SelectContent className="max-h-72">
                {(allLangs.length ? allLangs : COMMON_LANGS).map((l) => (
                  <SelectItem key={l.code} value={l.code}>{l.label}</SelectItem>
                ))}
                <SelectItem value="other">Other / custom</SelectItem>
              </SelectContent>
            </Select>
            {autoDetected && (
              <p className="text-[10px] text-emerald-400 mt-1">Limbă detectată automat din nume fișier</p>
            )}
            {subLang === "other" && (
              <Input
                value={subLangCustom}
                onChange={(e) => setSubLangCustom(e.target.value)}
                placeholder="ISO 639 code (e.g. nl)"
                className="bg-zinc-950 border-zinc-800 mt-1"
                maxLength={8}
                data-testid="sub-lang-custom"
              />
            )}
          </div>
          <div className="sm:col-span-1">
            <Label>Label</Label>
            <Input
              value={subLabel}
              onChange={(e) => setSubLabel(e.target.value)}
              placeholder="Română"
              className="bg-zinc-950 border-zinc-800"
              data-testid="sub-label"
            />
          </div>
          <div className="sm:col-span-1">
            <Label>File (.srt / .ass / .vtt)</Label>
            <Input
              type="file"
              accept=".srt,.ass,.vtt"
              onChange={(e) => setSubFile(e.target.files?.[0] || null)}
              className="bg-zinc-950 border-zinc-800"
              data-testid="sub-file"
            />
          </div>
          <Button type="submit" disabled={busy || !subFile} className="pro-gradient text-white border-0 disabled:opacity-50" data-testid="sub-add">
            <Plus size={14} className="mr-1" /> {busy ? "Uploading…" : "Add"}
          </Button>
        </form>
        <p className="text-xs text-zinc-500 mb-3">.srt and .ass files are auto-converted to WebVTT by the server. Subtitrările încorporate în fișierul video (MKV / MP4) sunt extrase și adăugate automat. Primul subtitlu din listă este afișat implicit în player.</p>
        <div className="space-y-2">
          {(v.subtitles || []).map((s, i) => (
            <div key={s.id} className="flex items-center justify-between bg-zinc-950 border border-zinc-800 rounded-md p-3" data-testid={`sub-${s.id}`}>
              <div className="flex items-center gap-2 flex-wrap">
                {i === 0 && <Star size={14} className="text-amber-400 fill-amber-400" />}
                <span className="font-semibold">{s.label}</span>
                <span className="text-xs text-zinc-500">({s.language || "und"}{s.format ? ` · ${s.format}` : ""})</span>
                {i === 0 && <span className="text-[10px] uppercase tracking-wider text-amber-400 bg-amber-400/10 px-1.5 py-0.5 rounded">default</span>}
                {s.source === "embedded" && (
                  <span className="text-[10px] uppercase tracking-wider text-sky-300 bg-sky-400/10 border border-sky-400/30 px-1.5 py-0.5 rounded" title="Extras automat din fișierul video">
                    extras
                  </span>
                )}
              </div>
              <div className="flex items-center gap-1">
                {i !== 0 && (
                  <Button size="sm" variant="outline" onClick={() => setDefaultSub(s.id)} className="border-zinc-700 hover:bg-zinc-800" data-testid={`sub-default-${s.id}`}>
                    <StarOff size={12} className="mr-1" /> Make default
                  </Button>
                )}
                <Button size="sm" variant="destructive" onClick={() => delSubtitle(s.id)} data-testid={`sub-del-${s.id}`}><Trash2 size={14} /></Button>
              </div>
            </div>
          ))}
          {(v.subtitles || []).length === 0 && <p className="text-zinc-500 text-sm">No subtitles yet — upload .srt, .ass or .vtt above.</p>}
        </div>
      </div>
    </div>
  );
}

/**
 * Compact button next to the Synopsis textarea.  Fires an LLM generation,
 * shows the preview in a small modal and lets the admin accept or discard.
 */
function AiSynopsisButton({ videoId, onGenerated }) {
  const [busy, setBusy] = useState(false);
  const [preview, setPreview] = useState(null);
  const [remaining, setRemaining] = useState(null);

  const generate = async () => {
    setBusy(true);
    try {
      const { data } = await api.post(`/admin/videos/${videoId}/generate-synopsis`, {});
      setPreview(data);
      // Refresh remaining quota
      const q = await api.get("/admin/videos/synopsis-quota").catch(() => null);
      if (q?.data) setRemaining(q.data.remaining);
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Eroare la generare");
    } finally {
      setBusy(false);
    }
  };

  const accept = () => {
    if (preview) {
      onGenerated(preview.synopsis);
      toast.success(`Sinopsis salvat (${preview.word_count} cuvinte)`);
    }
    setPreview(null);
  };

  return (
    <>
      <Button
        type="button"
        size="sm"
        variant="outline"
        disabled={busy}
        onClick={generate}
        className="border-violet-500/40 text-violet-300 hover:bg-violet-500/10"
        data-testid="ai-generate-synopsis-btn"
      >
        <Sparkles size={12} className="mr-1" />
        {busy ? "Generez…" : "Generează cu AI"}
      </Button>

      {preview && (
        <div className="fixed inset-0 z-50 bg-black/70 flex items-center justify-center p-4" onClick={() => setPreview(null)}>
          <div className="bg-zinc-900 border border-zinc-700 rounded-lg max-w-2xl w-full p-5 space-y-4" onClick={(e) => e.stopPropagation()}>
            <div className="flex items-center justify-between">
              <h3 className="text-lg font-bold flex items-center gap-2">
                <Sparkles size={18} className="text-violet-400" /> Sinopsis generat
              </h3>
              <span className="text-xs text-zinc-500">{preview.word_count} cuvinte · {preview.model}</span>
            </div>
            <p className="text-sm text-zinc-200 whitespace-pre-wrap leading-relaxed bg-zinc-950 rounded p-3 border border-zinc-800 max-h-80 overflow-y-auto" data-testid="ai-synopsis-preview">
              {preview.synopsis}
            </p>
            {remaining !== null && (
              <p className="text-xs text-zinc-500">Cotă zilnică rămasă: <strong>{remaining}</strong> generări</p>
            )}
            <div className="flex justify-end gap-2">
              <Button variant="outline" onClick={() => setPreview(null)} data-testid="ai-synopsis-discard">
                <X size={14} className="mr-1" /> Anulează
              </Button>
              <Button variant="outline" onClick={generate} disabled={busy} data-testid="ai-synopsis-regenerate">
                <Sparkles size={14} className="mr-1" /> Regenerează
              </Button>
              <Button onClick={accept} className="pro-gradient text-white border-0" data-testid="ai-synopsis-accept">
                <Check size={14} className="mr-1" /> Acceptă & Salvează
              </Button>
            </div>
          </div>
        </div>
      )}
    </>
  );
}
