import React, { useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import api, { mediaUrl } from "@/lib/api";
import Pagination from "@/components/Pagination";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Switch } from "@/components/ui/switch";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { toast } from "sonner";
import { useAuth } from "@/contexts/AuthContext";
import { useT } from "@/contexts/LanguageContext";
import {
  Trash2, Plus, RefreshCw, Eye, Heart, MessageCircle, Users, Video as VideoIcon, Crown,
  Pencil, Ban, ShieldOff, Upload as UploadIcon, ImageOff,
  TrendingUp, Search, AlertTriangle, CheckCircle2, ExternalLink, Send, Sparkles,
} from "lucide-react";

const RES_OPTIONS = ["360p", "720p", "1080p", "2048p", "4096p"];
const BAN_OPTIONS = [
  { v: "1day", l: "1 Day" }, { v: "1week", l: "1 Week" }, { v: "1month", l: "1 Month" },
  { v: "permanent", l: "Permanent" }, { v: "custom", l: "Custom (days)" },
];

export default function Admin() {
  const { user } = useAuth();
  if (!user || user.role !== "admin") return <div className="text-zinc-400">Admin access required.</div>;
  return (
    <div data-testid="admin-page">
      <h1 className="text-3xl font-bold font-heading mb-6">Admin Panel</h1>
      <Tabs defaultValue="dashboard">
        <TabsList className="bg-zinc-900 border border-zinc-800 flex-wrap h-auto">
          <TabsTrigger value="dashboard" data-testid="tab-dashboard">Dashboard</TabsTrigger>
          <TabsTrigger value="videos" data-testid="tab-videos">Videos</TabsTrigger>
          <TabsTrigger value="users" data-testid="tab-users">Users</TabsTrigger>
          <TabsTrigger value="categories" data-testid="tab-categories">Categories</TabsTrigger>
          <TabsTrigger value="shorts_series" data-testid="tab-shorts-series">Serii Shorts</TabsTrigger>
          <TabsTrigger value="packages" data-testid="tab-packages">Packages</TabsTrigger>
          <TabsTrigger value="packages_vip" data-testid="tab-packages-vip">Packages VIP</TabsTrigger>
          <TabsTrigger value="frames" data-testid="tab-frames">Cadre Avatar</TabsTrigger>
          <TabsTrigger value="announcements" data-testid="tab-announcements">Announcements</TabsTrigger>
          <TabsTrigger value="chat" data-testid="tab-chat">Live Chat</TabsTrigger>
          <TabsTrigger value="seo" data-testid="tab-seo">SEO</TabsTrigger>
          <TabsTrigger value="settings" data-testid="tab-settings">Settings</TabsTrigger>
        </TabsList>
        <TabsContent value="dashboard"><Dashboard /></TabsContent>
        <TabsContent value="videos"><VideosTab /></TabsContent>
        <TabsContent value="users"><UsersTab /></TabsContent>
        <TabsContent value="categories"><CategoriesTab /></TabsContent>
        <TabsContent value="shorts_series"><ShortsSeriesTab /></TabsContent>
        <TabsContent value="packages"><PackagesTab tier="pro" /></TabsContent>
        <TabsContent value="packages_vip"><PackagesTab tier="vip" /></TabsContent>
        <TabsContent value="frames"><FramesTab /></TabsContent>
        <TabsContent value="announcements"><AnnouncementsTab /></TabsContent>
        <TabsContent value="chat"><ChatModerationTab /></TabsContent>
        <TabsContent value="seo"><SEODashboardTab /></TabsContent>
        <TabsContent value="settings"><SettingsTab /></TabsContent>
      </Tabs>
    </div>
  );
}

function StatCard({ icon: Icon, label, value }) {
  return (
    <div className="bg-zinc-900 border border-zinc-800 rounded-xl p-5">
      <div className="flex items-center justify-between mb-2">
        <span className="text-xs uppercase tracking-widest text-zinc-500">{label}</span>
        <Icon size={18} className="text-rose-500" />
      </div>
      <div className="text-3xl font-bold font-heading">{value}</div>
    </div>
  );
}

function Dashboard() {
  const [s, setS] = useState(null);
  useEffect(() => { api.get("/admin/stats").then((r) => setS(r.data)); }, []);
  if (!s) return <div className="text-zinc-500">Loading...</div>;
  return (
    <div className="grid grid-cols-2 lg:grid-cols-3 gap-4 mt-6" data-testid="dashboard">
      <StatCard icon={VideoIcon} label="Total Videos" value={s.total_videos} />
      <StatCard icon={Users} label="Total Users" value={s.total_users} />
      <StatCard icon={Eye} label="Total Views" value={s.total_views} />
      <StatCard icon={Crown} label="PRO Users" value={s.total_pro_users} />
      <StatCard icon={Heart} label="Total Likes" value={s.total_likes} />
      <StatCard icon={MessageCircle} label="Total Comments" value={s.total_comments} />
    </div>
  );
}

function VideosTab() {
  const [items, setItems] = useState([]);
  const [total, setTotal] = useState(0);
  const [skip, setSkip] = useState(0);
  const [loading, setLoading] = useState(false);
  const [q, setQ] = useState("");
  const [debouncedQ, setDebouncedQ] = useState("");
  const [tier, setTier] = useState("");      // "" | free | pro
  const [statusF, setStatusF] = useState(""); // "" | ready | processing | failed
  const [shortF, setShortF] = useState("");   // "" | "short" | "video"
  const [selected, setSelected] = useState(new Set());
  const [bulkBusy, setBulkBusy] = useState(false);
  const [quota, setQuota] = useState(null);
  const PAGE = 50;

  useEffect(() => {
    api.get("/admin/videos/synopsis-quota").then((r) => setQuota(r.data)).catch(() => {});
  }, []);

  // Debounce
  useEffect(() => {
    const id = setTimeout(() => setDebouncedQ(q.trim()), 350);
    return () => clearTimeout(id);
  }, [q]);

  const load = async (nextSkip = 0, append = false) => {
    setLoading(true);
    try {
      const p = new URLSearchParams({ skip: String(nextSkip), limit: String(PAGE) });
      if (debouncedQ) p.set("q", debouncedQ);
      if (tier) p.set("access_tier", tier);
      if (statusF) p.set("status_filter", statusF);
      if (shortF === "short") p.set("is_short", "true");
      else if (shortF === "video") p.set("is_short", "false");
      const { data } = await api.get(`/admin/videos?${p.toString()}`);
      setTotal(data.total);
      setSkip(nextSkip);
      setItems((prev) => append ? [...prev, ...data.items] : data.items);
    } finally { setLoading(false); }
  };

  // Reset + fetch on every filter change
  const filterKey = `${debouncedQ}|${tier}|${statusF}|${shortF}`;
  const lastKey = useRef(null);
  useEffect(() => {
    if (lastKey.current === filterKey) return;
    lastKey.current = filterKey;
    load(0, false);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [filterKey]);

  const del = async (id) => {
    if (!window.confirm("Delete?")) return;
    await api.delete(`/videos/${id}`);
    load(skip, false);
  };

  const toggleSelect = (id) => {
    setSelected((prev) => {
      const nx = new Set(prev);
      if (nx.has(id)) nx.delete(id); else nx.add(id);
      return nx;
    });
  };
  const toggleSelectAll = () => {
    setSelected((prev) => {
      if (prev.size === items.length) return new Set();
      return new Set(items.map((i) => i.id));
    });
  };
  const clearSelection = () => setSelected(new Set());

  const bulkGenerateSynopsis = async () => {
    if (selected.size === 0) return;
    const cost = (selected.size * 0.002).toFixed(3);
    if (!window.confirm(
      `Generează sinopsis AI pentru ${selected.size} episoade?\n\n` +
      `• Cost estimat: ~$${cost} (≈${(selected.size * 0.01).toFixed(2)} lei)\n` +
      `• Episoadele cu sinopsis existent vor fi omise\n` +
      `• Cotă zilnică rămasă: ${quota?.remaining ?? "?"}\n\n` +
      `Continuă?`
    )) return;
    setBulkBusy(true);
    try {
      const { data } = await api.post("/admin/videos/generate-synopsis-bulk", {
        video_ids: Array.from(selected),
        skip_existing: true,
      });
      const { success = 0, submitted = 0, skipped = 0 } = data;
      if (skipped > 0) {
        toast.info(`${success}/${submitted} generate · ${skipped} omise (au deja sinopsis)`);
      } else if (success === submitted) {
        toast.success(`✓ ${success}/${submitted} sinopsis salvate`);
      } else {
        toast.warning(`${success}/${submitted} reușite — verifică erorile`);
      }
      clearSelection();
      // Refresh quota
      const q2 = await api.get("/admin/videos/synopsis-quota").catch(() => null);
      if (q2?.data) setQuota(q2.data);
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Eroare la generare bulk");
    } finally {
      setBulkBusy(false);
    }
  };

  const bulkDelete = async () => {
    if (selected.size === 0) return;
    if (!window.confirm(
      `Sigur ștergi ${selected.size} videoclipuri?\n\n` +
      `Această acțiune este ireversibilă.\n\n` +
      `Continuă?`
    )) return;
    setBulkBusy(true);
    const ids = Array.from(selected);
    let ok = 0;
    let fail = 0;
    // Fire deletes with limited concurrency to avoid overwhelming the server.
    const CHUNK = 5;
    for (let i = 0; i < ids.length; i += CHUNK) {
      const chunk = ids.slice(i, i + CHUNK);
      const results = await Promise.allSettled(chunk.map((id) => api.delete(`/videos/${id}`)));
      results.forEach((r) => (r.status === "fulfilled" ? ok++ : fail++));
    }
    setBulkBusy(false);
    clearSelection();
    if (fail === 0) toast.success(`✓ ${ok} videoclipuri șterse`);
    else toast.warning(`${ok}/${ids.length} șterse · ${fail} au eșuat`);
    // Refresh list
    load(0, false);
  };

  const hasMore = items.length < total;
  return (
    <div className="mt-6 space-y-3" data-testid="admin-videos">
      <div className="flex flex-wrap gap-2 items-center">
        <Input
          value={q}
          onChange={(e) => setQ(e.target.value)}
          placeholder="Search by title, uploader, or tag…"
          className="bg-zinc-900 border-zinc-800 max-w-md"
          data-testid="admin-videos-search"
        />
        <Select value={tier || "all"} onValueChange={(v) => setTier(v === "all" ? "" : v)}>
          <SelectTrigger className="bg-zinc-900 border-zinc-800 w-32" data-testid="admin-videos-tier"><SelectValue placeholder="Tier" /></SelectTrigger>
          <SelectContent>
            <SelectItem value="all">All tiers</SelectItem>
            <SelectItem value="free">Free</SelectItem>
            <SelectItem value="pro">PRO</SelectItem>
          </SelectContent>
        </Select>
        <Select value={statusF || "all"} onValueChange={(v) => setStatusF(v === "all" ? "" : v)}>
          <SelectTrigger className="bg-zinc-900 border-zinc-800 w-36" data-testid="admin-videos-status"><SelectValue placeholder="Status" /></SelectTrigger>
          <SelectContent>
            <SelectItem value="all">All statuses</SelectItem>
            <SelectItem value="ready">Ready</SelectItem>
            <SelectItem value="processing">Processing</SelectItem>
            <SelectItem value="failed">Failed</SelectItem>
          </SelectContent>
        </Select>
        <Select value={shortF || "all"} onValueChange={(v) => setShortF(v === "all" ? "" : v)}>
          <SelectTrigger className="bg-zinc-900 border-zinc-800 w-32" data-testid="admin-videos-kind"><SelectValue placeholder="Kind" /></SelectTrigger>
          <SelectContent>
            <SelectItem value="all">Any kind</SelectItem>
            <SelectItem value="video">Long-form</SelectItem>
            <SelectItem value="short">Shorts</SelectItem>
          </SelectContent>
        </Select>
        <div className="text-xs text-zinc-500 ml-auto">
          Showing <strong>{items.length}</strong> of <strong>{total}</strong>
        </div>
      </div>

      {/* Bulk AI synopsis toolbar */}
      {items.length > 0 && (
        <div className="bg-gradient-to-br from-violet-500/10 via-zinc-900 to-fuchsia-500/10 border border-violet-500/30 rounded-lg p-3 flex flex-wrap items-center gap-3">
          <label className="inline-flex items-center gap-2 cursor-pointer">
            <input
              type="checkbox"
              checked={selected.size === items.length && items.length > 0}
              onChange={toggleSelectAll}
              className="w-4 h-4 accent-violet-500"
              data-testid="select-all-videos"
            />
            <span className="text-sm text-zinc-200">Selectează tot ({items.length})</span>
          </label>
          {selected.size > 0 && (
            <>
              <span className="text-sm text-violet-300">
                <strong>{selected.size}</strong> selectate
              </span>
              <Button
                size="sm"
                onClick={bulkGenerateSynopsis}
                disabled={bulkBusy}
                className="pro-gradient text-white border-0"
                data-testid="bulk-generate-synopsis"
              >
                <Sparkles size={14} className="mr-1" />
                {bulkBusy ? "Se generează…" : `Generează sinopsis AI (${selected.size})`}
              </Button>
              <Button
                size="sm"
                variant="destructive"
                onClick={bulkDelete}
                disabled={bulkBusy}
                data-testid="bulk-delete-videos"
              >
                <Trash2 size={14} className="mr-1" />
                {bulkBusy ? "Se procesează…" : `Șterge Videoclipurile Selectate (${selected.size})`}
              </Button>
              <Button size="sm" variant="outline" onClick={clearSelection}>
                Anulează selecție
              </Button>
            </>
          )}
          {quota && (
            <div className="ml-auto text-xs text-zinc-400">
              Cotă zilnică: <strong className={quota.remaining < 10 ? "text-amber-400" : "text-emerald-400"}>{quota.remaining}</strong> / {quota.daily_limit} · {quota.model}
            </div>
          )}
        </div>
      )}

      {items.map((v) => (
        <div key={v.id} className="bg-zinc-900 border border-zinc-800 rounded-lg p-3 flex items-center justify-between gap-3 flex-wrap">
          <input
            type="checkbox"
            checked={selected.has(v.id)}
            onChange={() => toggleSelect(v.id)}
            className="w-4 h-4 accent-violet-500 flex-shrink-0"
            data-testid={`select-vid-${v.id}`}
          />
          <div className="flex-1 min-w-0">
            <div className="font-semibold truncate">{v.title}</div>
            <div className="text-xs text-zinc-500 flex flex-wrap gap-x-2">
              <span>@{v.uploader_username}</span>
              <span>·</span>
              <span className={v.status === "ready" ? "text-emerald-400" : v.status === "failed" ? "text-red-400" : "text-amber-400"}>{v.status}</span>
              <span>·</span>
              <span>{v.views} views</span>
              <span>·</span>
              <span className={v.access_tier === "pro" ? "text-amber-300" : ""}>{v.access_tier}</span>
              {v.is_short && (<><span>·</span><span className="text-fuchsia-300">SHORT</span></>)}
              {v.synopsis && <><span>·</span><span className="text-violet-300 inline-flex items-center gap-0.5"><Sparkles size={10} /> sinopsis</span></>}
            </div>
          </div>
          <Link to={`/edit-video/${v.id}`}>
            <Button size="sm" variant="outline" className="border-zinc-700 hover:bg-zinc-800" data-testid={`edit-vid-${v.id}`}>
              <Pencil size={14} className="mr-1" /> Edit
            </Button>
          </Link>
          <Button size="sm" variant="destructive" onClick={() => del(v.id)} data-testid={`del-vid-${v.id}`}><Trash2 size={14} /></Button>
        </div>
      ))}
      {items.length === 0 && !loading && (
        <p className="text-zinc-500 text-center py-8">No videos match your filters.</p>
      )}
      {hasMore && (
        <div className="flex justify-center pt-4">
          <Button
            variant="outline"
            disabled={loading}
            onClick={() => load(items.length, true)}
            className="border-zinc-700 hover:bg-zinc-800 hidden"
            data-testid="admin-videos-load-more"
          >
            {loading ? "Loading…" : `Load more (${total - items.length} remaining)`}
          </Button>
        </div>
      )}
      <Pagination
        currentPage={Math.floor(skip / PAGE) + 1}
        totalPages={Math.max(1, Math.ceil(total / PAGE))}
        onPageChange={(page) => {
          const nextSkip = Math.max(0, (page - 1) * PAGE);
          load(nextSkip, false);
          window.scrollTo({ top: 0, behavior: "smooth" });
        }}
      />
    </div>
  );
}

function UsersTab() {
  const [users, setUsers] = useState([]);
  const [total, setTotal] = useState(0);
  const [skip, setSkip] = useState(0);
  const [loading, setLoading] = useState(false);
  const [q, setQ] = useState("");
  const [debouncedQ, setDebouncedQ] = useState("");
  const [banDur, setBanDur] = useState({});
  const [banDays, setBanDays] = useState({});
  const [proDur, setProDur] = useState({});
  const [proDays, setProDays] = useState({});
  const [vipDur, setVipDur] = useState({});
  const [vipDays, setVipDays] = useState({});
  const PAGE = 50;

  useEffect(() => {
    const id = setTimeout(() => setDebouncedQ(q.trim()), 350);
    return () => clearTimeout(id);
  }, [q]);

  const load = async (nextSkip = 0, append = false) => {
    setLoading(true);
    try {
      const p = new URLSearchParams({ skip: String(nextSkip), limit: String(PAGE) });
      if (debouncedQ) p.set("q", debouncedQ);
      const { data } = await api.get(`/admin/users?${p.toString()}`);
      setTotal(data.total);
      setSkip(nextSkip);
      setUsers((prev) => append ? [...prev, ...data.items] : data.items);
    } finally { setLoading(false); }
  };

  const lastKey = useRef(null);
  useEffect(() => {
    if (lastKey.current === debouncedQ) return;
    lastKey.current = debouncedQ;
    load(0, false);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [debouncedQ]);

  const reload = () => load(0, false);

  const ban = async (u) => {
    const duration = banDur[u.id] || "1day";
    const body = { duration, custom_days: parseInt(banDays[u.id] || 1) };
    await api.post(`/admin/users/${u.id}/ban`, body);
    toast.success("Banned");
    reload();
  };
  const unban = async (u) => { await api.post(`/admin/users/${u.id}/unban`); reload(); };
  const setRole = async (u, role) => { await api.post(`/admin/users/${u.id}/role`, { role }); reload(); };
  const grantPro = async (u) => {
    const duration = proDur[u.id] || "1month";
    const body = { duration, custom_days: parseInt(proDays[u.id] || 1) };
    await api.post(`/admin/users/${u.id}/grant-pro`, body);
    toast.success("PRO granted");
    reload();
  };
  const revokePro = async (u) => { await api.post(`/admin/users/${u.id}/revoke-pro`); reload(); };
  const grantVip = async (u) => {
    const duration = vipDur[u.id] || "1month";
    const body = { duration, custom_days: parseInt(vipDays[u.id] || 1) };
    await api.post(`/admin/users/${u.id}/grant-vip`, body);
    toast.success("VIP granted");
    reload();
  };
  const revokeVip = async (u) => { await api.post(`/admin/users/${u.id}/revoke-vip`); reload(); };

  const hasMore = users.length < total;
  return (
    <div className="mt-6 space-y-3" data-testid="admin-users">
      <div className="flex flex-wrap gap-2 items-center">
        <Input
          value={q}
          onChange={(e) => setQ(e.target.value)}
          placeholder="Search by username or email…"
          className="bg-zinc-900 border-zinc-800 max-w-md"
          data-testid="admin-users-search"
        />
        <div className="text-xs text-zinc-500 ml-auto">
          Showing <strong>{users.length}</strong> of <strong>{total}</strong>
        </div>
      </div>
      {users.map((u) => (
        <div key={u.id} className="bg-zinc-900 border border-zinc-800 rounded-lg p-4">
          {/* Header: identity + status chips */}
          <div className="flex items-start justify-between gap-3 mb-3 flex-wrap">
            <div className="min-w-0">
              <div className="font-semibold truncate">
                @{u.username} <span className="text-xs text-zinc-500">{u.email}</span>
              </div>
              <div className="flex flex-wrap gap-1.5 mt-1.5 text-[11px]">
                <span className="px-1.5 py-0.5 rounded bg-zinc-800 text-zinc-300">role: {u.role}</span>
                <span className={`px-1.5 py-0.5 rounded ${u.is_pro ? "bg-rose-500/20 text-rose-300 border border-rose-500/30" : "bg-zinc-800 text-zinc-500"}`}>
                  {u.is_pro ? "PRO active" : "not PRO"}
                </span>
                <span className={`px-1.5 py-0.5 rounded ${u.is_vip ? "bg-amber-500/20 text-amber-300 border border-amber-500/40" : "bg-zinc-800 text-zinc-500"}`}>
                  {u.is_vip ? "VIP active" : "not VIP"}
                </span>
                {u.banned_until && (
                  <span className="px-1.5 py-0.5 rounded bg-red-900/40 text-red-300 border border-red-800">
                    banned → {u.banned_until.slice(0, 16)}
                  </span>
                )}
                {u.chat_banned_until && (
                  <span className="px-1.5 py-0.5 rounded bg-orange-900/40 text-orange-300 border border-orange-800">
                    chat-ban → {u.chat_banned_until.slice(0, 16)}
                  </span>
                )}
              </div>
            </div>
            <Button size="sm" variant="outline" onClick={() => setRole(u, u.role === "admin" ? "user" : "admin")} className="shrink-0">
              {u.role === "admin" ? "Demote" : "Promote"}
            </Button>
          </div>

          {/* Actions grid: Ban | PRO | VIP */}
          <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
            {/* Ban block */}
            <div className="bg-zinc-950/60 border border-zinc-800 rounded-md p-2.5">
              <div className="text-[10px] uppercase tracking-wider text-zinc-500 mb-2">Ban</div>
              <div className="flex flex-wrap items-center gap-1.5">
                <Select value={banDur[u.id] || "1day"} onValueChange={(v) => setBanDur({ ...banDur, [u.id]: v })}>
                  <SelectTrigger className="w-28 h-8 bg-zinc-950 border-zinc-800 text-xs"><SelectValue /></SelectTrigger>
                  <SelectContent>{BAN_OPTIONS.map((o) => <SelectItem key={o.v} value={o.v}>{o.l}</SelectItem>)}</SelectContent>
                </Select>
                {banDur[u.id] === "custom" && (
                  <Input type="number" placeholder="Days" value={banDays[u.id] || ""} onChange={(e) => setBanDays({ ...banDays, [u.id]: e.target.value })} className="w-16 h-8 bg-zinc-950 border-zinc-800 text-xs" />
                )}
                <Button size="sm" variant="destructive" className="h-8" onClick={() => ban(u)} data-testid={`ban-${u.id}`}>Ban</Button>
                <Button size="sm" variant="outline" className="h-8" onClick={() => unban(u)}>Unban</Button>
              </div>
            </div>

            {/* PRO block */}
            <div className="bg-rose-950/20 border border-rose-900/40 rounded-md p-2.5">
              <div className="text-[10px] uppercase tracking-wider text-rose-300 mb-2 flex items-center gap-1">
                <Crown size={10} /> PRO
              </div>
              <div className="flex flex-wrap items-center gap-1.5">
                <Select value={proDur[u.id] || "1month"} onValueChange={(v) => setProDur({ ...proDur, [u.id]: v })}>
                  <SelectTrigger className="w-28 h-8 bg-zinc-950 border-zinc-800 text-xs"><SelectValue /></SelectTrigger>
                  <SelectContent>{BAN_OPTIONS.map((o) => <SelectItem key={o.v} value={o.v}>{o.l}</SelectItem>)}</SelectContent>
                </Select>
                {proDur[u.id] === "custom" && (
                  <Input type="number" placeholder="Days" value={proDays[u.id] || ""} onChange={(e) => setProDays({ ...proDays, [u.id]: e.target.value })} className="w-16 h-8 bg-zinc-950 border-zinc-800 text-xs" />
                )}
                <Button size="sm" className="h-8 pro-gradient text-white border-0" onClick={() => grantPro(u)} data-testid={`grant-pro-${u.id}`}>Grant</Button>
                {u.is_pro && <Button size="sm" variant="outline" className="h-8" onClick={() => revokePro(u)} data-testid={`revoke-pro-${u.id}`}>Revoke</Button>}
              </div>
            </div>

            {/* VIP block */}
            <div className="bg-amber-950/20 border border-amber-900/40 rounded-md p-2.5">
              <div className="text-[10px] uppercase tracking-wider text-amber-300 mb-2 flex items-center gap-1">
                <Crown size={10} /> VIP
              </div>
              <div className="flex flex-wrap items-center gap-1.5">
                <Select value={vipDur[u.id] || "1month"} onValueChange={(v) => setVipDur({ ...vipDur, [u.id]: v })}>
                  <SelectTrigger className="w-28 h-8 bg-zinc-950 border-zinc-800 text-xs" data-testid={`vip-dur-${u.id}`}><SelectValue /></SelectTrigger>
                  <SelectContent>{BAN_OPTIONS.map((o) => <SelectItem key={o.v} value={o.v}>{o.l}</SelectItem>)}</SelectContent>
                </Select>
                {vipDur[u.id] === "custom" && (
                  <Input type="number" placeholder="Days" value={vipDays[u.id] || ""} onChange={(e) => setVipDays({ ...vipDays, [u.id]: e.target.value })} className="w-16 h-8 bg-zinc-950 border-zinc-800 text-xs" />
                )}
                <Button size="sm" className="h-8 vip-gradient text-black font-bold border-0" onClick={() => grantVip(u)} data-testid={`grant-vip-${u.id}`}>Grant</Button>
                {u.is_vip && <Button size="sm" variant="outline" className="h-8" onClick={() => revokeVip(u)} data-testid={`revoke-vip-${u.id}`}>Revoke</Button>}
              </div>
            </div>
          </div>
        </div>
      ))}
      {users.length === 0 && !loading && (
        <p className="text-zinc-500 text-center py-8">No users match your search.</p>
      )}
      {hasMore && (
        <div className="flex justify-center pt-4">
          <Button
            variant="outline"
            disabled={loading}
            onClick={() => load(users.length, true)}
            className="border-zinc-700 hover:bg-zinc-800"
            data-testid="admin-users-load-more"
          >
            {loading ? "Loading…" : `Load more (${total - users.length} remaining)`}
          </Button>
        </div>
      )}
    </div>
  );
}

function CategoriesTab() {
  const [cats, setCats] = useState([]);
  const [name, setName] = useState("");
  const [nameEn, setNameEn] = useState("");
  const [editingId, setEditingId] = useState(null);
  const [editName, setEditName] = useState("");
  const [editNameEn, setEditNameEn] = useState("");
  const load = () => api.get("/categories").then((r) => setCats(r.data));
  useEffect(() => { load(); }, []);
  const create = async () => {
    if (!name.trim()) return;
    await api.post("/categories", { name, name_en: nameEn });
    setName(""); setNameEn(""); load();
  };
  const startEdit = (c) => {
    setEditingId(c.id);
    setEditName(c.name);
    setEditNameEn(c.name_en || "");
  };
  const saveEdit = async () => {
    await api.patch(`/categories/${editingId}`, { name: editName, name_en: editNameEn });
    setEditingId(null); setEditName(""); setEditNameEn("");
    load();
  };
  const del = async (id) => { await api.delete(`/categories/${id}`); load(); };
  return (
    <div className="mt-6" data-testid="admin-categories">
      <div className="grid sm:grid-cols-3 gap-2 mb-4">
        <Input value={name} onChange={(e) => setName(e.target.value)} placeholder="Name (RO)" className="bg-zinc-900 border-zinc-800" data-testid="new-cat-name" />
        <Input value={nameEn} onChange={(e) => setNameEn(e.target.value)} placeholder="Name (EN)" className="bg-zinc-900 border-zinc-800" data-testid="new-cat-name-en" />
        <Button onClick={create} data-testid="add-cat-btn" className="pro-gradient text-white border-0"><Plus size={14} className="mr-1" /> Add</Button>
      </div>
      <div className="space-y-2">
        {cats.map((c) => (
          <div key={c.id} className="bg-zinc-900 border border-zinc-800 rounded-md p-3" data-testid={`cat-row-${c.id}`}>
            {editingId === c.id ? (
              <div className="grid sm:grid-cols-3 gap-2 items-center">
                <Input value={editName} onChange={(e) => setEditName(e.target.value)} placeholder="Name (RO)" className="bg-zinc-950 border-zinc-800" />
                <Input value={editNameEn} onChange={(e) => setEditNameEn(e.target.value)} placeholder="Name (EN)" className="bg-zinc-950 border-zinc-800" />
                <div className="flex gap-2">
                  <Button size="sm" onClick={saveEdit} className="pro-gradient text-white border-0" data-testid={`cat-save-${c.id}`}>Save</Button>
                  <Button size="sm" variant="outline" onClick={() => setEditingId(null)}>Cancel</Button>
                </div>
              </div>
            ) : (
              <div className="flex justify-between items-center">
                <div>
                  <span className="font-medium">{c.name}</span>
                  {c.name_en && <span className="text-zinc-500 text-sm ml-2">/ {c.name_en}</span>}
                  {!c.name_en && <span className="text-amber-500/70 text-xs ml-2">(no EN translation)</span>}
                </div>
                <div className="flex gap-2">
                  <Button size="sm" variant="outline" onClick={() => startEdit(c)} data-testid={`cat-edit-${c.id}`}><Pencil size={14} /></Button>
                  <Button size="sm" variant="destructive" onClick={() => del(c.id)}><Trash2 size={14} /></Button>
                </div>
              </div>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}
function ShortsSeriesTab() {
  const [list, setList] = useState([]);
  const [form, setForm] = useState({ name: "", slug: "", description: "", cover_thumbnail: "", tags: "", active: true, sort_order: 0 });
  const load = () => api.get("/shorts-series/all").then((r) => setList(r.data));
  useEffect(() => { load(); }, []);

  const create = async () => {
    if (!form.name.trim()) return toast.error("Nume obligatoriu");
    try {
      await api.post("/shorts-series", {
        name: form.name.trim(),
        slug: form.slug.trim() || undefined,
        description: form.description,
        cover_thumbnail: form.cover_thumbnail.trim(),
        tags: form.tags.split(",").map((t) => t.trim()).filter(Boolean),
        active: form.active,
        sort_order: parseInt(form.sort_order) || 0,
      });
      setForm({ name: "", slug: "", description: "", cover_thumbnail: "", tags: "", active: true, sort_order: 0 });
      toast.success("Serie creată");
      load();
    } catch (e) {
      toast.error(e.response?.data?.detail || "Eroare");
    }
  };

  const patch = async (id, upd) => {
    try {
      await api.patch(`/shorts-series/${id}`, upd);
      load();
    } catch (e) {
      toast.error(e.response?.data?.detail || "Eroare");
    }
  };

  const del = async (s) => {
    if (!window.confirm(`Ștergi seria "${s.name}"?\n${s.episode_count > 0 ? `Cele ${s.episode_count} episoade vor rămâne, dar nu vor mai fi legate de această serie.` : ""}`)) return;
    await api.delete(`/shorts-series/${s.id}`);
    toast.success("Serie ștearsă");
    load();
  };

  return (
    <div className="mt-6 space-y-6" data-testid="admin-shorts-series">
      <div className="bg-zinc-900 border border-zinc-800 rounded-xl p-4">
        <div className="font-semibold mb-3">Serie Shorts nouă ({list.length})</div>
        <div className="grid grid-cols-2 gap-3">
          <Input placeholder="Nume (ex: Compilații funny)" value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} className="bg-zinc-950 border-zinc-800" data-testid="new-series-name" />
          <Input placeholder="Slug (opțional — auto)" value={form.slug} onChange={(e) => setForm({ ...form, slug: e.target.value })} className="bg-zinc-950 border-zinc-800" data-testid="new-series-slug" />
          <Input placeholder="URL cover thumbnail (portret 2:3 recomandat)" value={form.cover_thumbnail} onChange={(e) => setForm({ ...form, cover_thumbnail: e.target.value })} className="bg-zinc-950 border-zinc-800 col-span-2" data-testid="new-series-cover" />
          <Input placeholder="Tag-uri (separate prin virgulă)" value={form.tags} onChange={(e) => setForm({ ...form, tags: e.target.value })} className="bg-zinc-950 border-zinc-800" data-testid="new-series-tags" />
          <Input type="number" placeholder="Sort order (0)" value={form.sort_order} onChange={(e) => setForm({ ...form, sort_order: e.target.value })} className="bg-zinc-950 border-zinc-800" />
          <Textarea placeholder="Descriere" value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })} className="bg-zinc-950 border-zinc-800 col-span-2" />
        </div>
        <div className="flex items-center gap-3 mt-3">
          <Switch checked={form.active} onCheckedChange={(v) => setForm({ ...form, active: v })} />
          <span className="text-xs text-zinc-400">Activă (vizibilă pe /shorts)</span>
          <Button onClick={create} className="ml-auto pro-gradient text-white border-0" data-testid="new-series-btn">
            Adaugă serie
          </Button>
        </div>
      </div>
      {list.map((s) => (
        <div key={s.id} className="bg-zinc-900 border border-zinc-800 rounded-xl p-4" data-testid={`series-row-${s.id}`}>
          <div className="flex gap-4">
            <div className="w-16 shrink-0">
              {s.cover_thumbnail ? (
                <img src={s.cover_thumbnail} alt={s.name} className="w-16 aspect-[2/3] object-cover rounded border border-zinc-800" />
              ) : (
                <div className="w-16 aspect-[2/3] rounded border border-dashed border-zinc-700 flex items-center justify-center text-zinc-600 text-xs">no cover</div>
              )}
              <label className="mt-1.5 flex items-center justify-center gap-1 text-[10px] cursor-pointer text-zinc-400 hover:text-zinc-100 bg-zinc-950 border border-zinc-800 rounded py-1" data-testid={`series-cover-upload-${s.id}`}>
                <UploadIcon size={10} /> Cover
                <input
                  type="file"
                  accept="image/*"
                  className="hidden"
                  onChange={async (e) => {
                    const file = e.target.files?.[0];
                    if (!file) return;
                    if (file.size > 8 * 1024 * 1024) return toast.error("Max 8 MB");
                    try {
                      const fd = new FormData();
                      fd.append("file", file);
                      const { data } = await api.post(`/shorts-series/${s.id}/cover`, fd, {
                        headers: { "Content-Type": "multipart/form-data" },
                      });
                      toast.success("Cover urcat pe Wasabi");
                      // Update in-place so the preview refreshes without a full reload
                      setList((prev) => prev.map((x) => x.id === s.id ? { ...x, cover_thumbnail: data.cover_thumbnail } : x));
                    } catch (err) {
                      toast.error(err.response?.data?.detail || "Eroare încărcare");
                    } finally {
                      e.target.value = "";
                    }
                  }}
                />
              </label>
            </div>
            <div className="flex-1 min-w-0">
              <div className="flex items-start justify-between gap-3">
                <div className="min-w-0">
                  <div className="font-semibold text-zinc-100 truncate">{s.name}</div>
                  <div className="text-xs text-zinc-500">slug: <code className="text-zinc-400">/{s.slug}</code> · {s.episode_count} episoade · order {s.sort_order}</div>
                  {s.tags?.length > 0 && (
                    <div className="text-[11px] text-zinc-500 mt-1 line-clamp-1">{s.tags.join(" · ")}</div>
                  )}
                </div>
                <div className="flex items-center gap-2 shrink-0">
                  <Switch checked={s.active} onCheckedChange={(v) => patch(s.id, { active: v })} data-testid={`series-active-${s.id}`} />
                  <Button size="sm" variant="destructive" onClick={() => del(s)} data-testid={`series-del-${s.id}`}><Trash2 size={14} /></Button>
                </div>
              </div>
              <div className="grid grid-cols-2 md:grid-cols-4 gap-2 mt-3">
                <Input defaultValue={s.name} onBlur={(e) => e.target.value !== s.name && patch(s.id, { name: e.target.value })} className="bg-zinc-950 border-zinc-800 h-8 text-xs" placeholder="Nume" />
                <Input defaultValue={s.slug} onBlur={(e) => e.target.value !== s.slug && patch(s.id, { slug: e.target.value })} className="bg-zinc-950 border-zinc-800 h-8 text-xs" placeholder="Slug" />
                <Input defaultValue={s.cover_thumbnail || ""} onBlur={(e) => e.target.value !== (s.cover_thumbnail || "") && patch(s.id, { cover_thumbnail: e.target.value })} className="bg-zinc-950 border-zinc-800 h-8 text-xs md:col-span-2" placeholder="Cover URL" />
                <Textarea defaultValue={s.description || ""} onBlur={(e) => e.target.value !== (s.description || "") && patch(s.id, { description: e.target.value })} className="bg-zinc-950 border-zinc-800 text-xs col-span-2 md:col-span-4" placeholder="Descriere" rows={2} />
              </div>
            </div>
          </div>
        </div>
      ))}
      {list.length === 0 && (
        <p className="text-sm text-zinc-500 text-center py-6" data-testid="shorts-series-empty">
          Nu există serii Shorts. Creează prima mai sus.
        </p>
      )}
    </div>
  );
}



function PackagesTab({ tier = "pro" }) {
  const isVip = tier === "vip";
  const label = isVip ? "VIP" : "PRO";
  const defaultColor = isVip ? "#f59e0b" : "#f43f5e";
  const gradientCls = isVip ? "vip-gradient text-black" : "pro-gradient text-white";
  const [pks, setPks] = useState([]);
  const [form, setForm] = useState({ name: "", description: "", color: defaultColor, price: 9.99, currency: "usd", duration_days: 30, active: true, sort_order: 0 });
  const load = () => api.get(`/packages/all?tier=${tier}`).then((r) => setPks(r.data));
  useEffect(() => { load(); setForm((f) => ({ ...f, color: defaultColor })); /* eslint-disable-next-line */ }, [tier]);
  const create = async () => {
    if (!form.name.trim()) return toast.error("Nume obligatoriu");
    try {
      await api.post("/packages", {
        ...form,
        tier,
        price: parseFloat(form.price),
        duration_days: parseInt(form.duration_days),
      });
      setForm({ ...form, name: "", description: "" });
      toast.success(`Pachet ${label} creat`);
      load();
    } catch (e) {
      toast.error(e.response?.data?.detail || "Eroare");
    }
  };
  const upd = async (id, patch) => { await api.patch(`/packages/${id}`, patch); load(); };
  const del = async (id) => {
    if (!window.confirm(`Șterge acest pachet ${label}?`)) return;
    await api.delete(`/packages/${id}`);
    load();
  };
  return (
    <div className="mt-6 space-y-6" data-testid={`admin-packages-${tier}`}>
      <div className="bg-zinc-900 border border-zinc-800 rounded-xl p-4">
        <div className="font-semibold mb-3">Pachet {label} nou ({pks.length})</div>
        <div className="grid grid-cols-2 gap-3">
          <Input placeholder="Nume" value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} className="bg-zinc-950 border-zinc-800" data-testid={`new-pkg-${tier}-name`} />
          <Input type="color" value={form.color} onChange={(e) => setForm({ ...form, color: e.target.value })} className="bg-zinc-950 border-zinc-800 h-10" />
          <Input type="number" step="0.01" placeholder="Preț" value={form.price} onChange={(e) => setForm({ ...form, price: e.target.value })} className="bg-zinc-950 border-zinc-800" data-testid={`new-pkg-${tier}-price`} />
          <Input type="number" placeholder="Durată (zile)" value={form.duration_days} onChange={(e) => setForm({ ...form, duration_days: e.target.value })} className="bg-zinc-950 border-zinc-800" data-testid={`new-pkg-${tier}-days`} />
          <Textarea placeholder="Descriere" value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })} className="bg-zinc-950 border-zinc-800 col-span-2" />
        </div>
        <Button onClick={create} className={`mt-3 ${gradientCls} border-0`} data-testid={`new-pkg-${tier}-btn`}>Adaugă pachet {label}</Button>
      </div>
      {pks.map((p) => (
        <div key={p.id} className="bg-zinc-900 border border-zinc-800 rounded-xl p-4 flex justify-between items-center" data-testid={`pkg-row-${p.id}`}>
          <div>
            <div className="font-semibold flex items-center gap-2" style={{ color: p.color }}>
              {p.name} — ${p.price}
              <span className={`text-[10px] uppercase tracking-wider px-1.5 py-0.5 rounded ${isVip ? "bg-amber-500/20 text-amber-300 border border-amber-500/40" : "bg-rose-500/20 text-rose-300 border border-rose-500/40"}`}>{label}</span>
            </div>
            <div className="text-xs text-zinc-500">{p.duration_days} zile · activ: {String(p.active)}</div>
          </div>
          <div className="flex gap-2 items-center">
            <Switch checked={p.active} onCheckedChange={(v) => upd(p.id, { active: v })} data-testid={`pkg-active-${p.id}`} />
            <Button size="sm" variant="destructive" onClick={() => del(p.id)} data-testid={`pkg-del-${p.id}`}><Trash2 size={14} /></Button>
          </div>
        </div>
      ))}
      {pks.length === 0 && (
        <p className="text-sm text-zinc-500" data-testid={`admin-packages-${tier}-empty`}>
          Nu există pachete {label}. Creează primul mai sus.
        </p>
      )}
    </div>
  );
}

function FramesTab() {
  const [frames, setFrames] = useState([]);
  const [creating, setCreating] = useState({ name: "", effect_key: "neon-ring", color_primary: "#f43f5e", color_secondary: "#fb7185", rarity: "common", price_coins: 100, active: true, sort_order: 0 });
  const [busy, setBusy] = useState(false);
  const EFFECTS = [
    "neon-ring", "dashed-rotate", "soft-glow", "conic-rotate", "stars-orbit",
    "pulse-shadow", "aurora-shift", "fire", "electric", "particles",
    "hologram", "glitch", "gold-shimmer", "diamond-shimmer", "fire-ring",
    "frost-ring", "hearts-orbit", "moon-glow", "crown-orbit", "demonic",
    "galaxy", "sun-rays", "phoenix", "dragon-scales", "petals",
    "cyberpunk", "matrix", "lava", "cosmos-supreme",
  ];

  const load = () => api.get("/admin/frames").then((r) => setFrames(r.data));
  useEffect(() => { load(); }, []);

  const create = async () => {
    if (!creating.name.trim()) return toast.error("Nume obligatoriu");
    setBusy(true);
    try {
      await api.post("/admin/frames", creating);
      setCreating({ ...creating, name: "" });
      toast.success("Cadru creat");
      load();
    } catch (e) {
      toast.error(e.response?.data?.detail || "Eroare");
    } finally { setBusy(false); }
  };

  const upd = async (id, patch) => {
    await api.patch(`/admin/frames/${id}`, patch);
    load();
  };
  const del = async (id) => {
    if (!window.confirm("Șterge acest cadru? Va fi eliminat și din inventarul utilizatorilor.")) return;
    await api.delete(`/admin/frames/${id}`);
    toast.success("Șters");
    load();
  };

  const seedDefaults = async () => {
    setBusy(true);
    try {
      const { data } = await api.post("/admin/frames/seed");
      toast.success(`${data.inserted} cadre adăugate (total: ${data.total})`);
      load();
    } finally { setBusy(false); }
  };

  return (
    <div className="mt-6 space-y-4" data-testid="admin-frames">
      <div className="bg-zinc-900 border border-zinc-800 rounded-xl p-4">
        <div className="flex items-center justify-between mb-3 flex-wrap gap-2">
          <h3 className="font-semibold">Cadre Avatar — {frames.length} total</h3>
          <Button onClick={seedDefaults} variant="outline" size="sm" disabled={busy} data-testid="seed-frames-btn">
            Adaugă cele 50 implicite
          </Button>
        </div>
        <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 gap-2">
          <Input placeholder="Nume cadru" value={creating.name} onChange={(e) => setCreating({ ...creating, name: e.target.value })} className="bg-zinc-950 border-zinc-800" data-testid="new-frame-name" />
          <select
            value={creating.effect_key}
            onChange={(e) => setCreating({ ...creating, effect_key: e.target.value })}
            className="bg-zinc-950 border border-zinc-800 rounded-md px-3 py-2 text-sm"
            data-testid="new-frame-effect"
          >
            {EFFECTS.map((e) => <option key={e} value={e}>{e}</option>)}
          </select>
          <select
            value={creating.rarity}
            onChange={(e) => setCreating({ ...creating, rarity: e.target.value })}
            className="bg-zinc-950 border border-zinc-800 rounded-md px-3 py-2 text-sm"
          >
            <option value="common">common</option>
            <option value="rare">rare</option>
            <option value="epic">epic</option>
            <option value="legendary">legendary</option>
          </select>
          <div className="flex gap-2">
            <Input type="color" value={creating.color_primary} onChange={(e) => setCreating({ ...creating, color_primary: e.target.value })} className="bg-zinc-950 border-zinc-800 w-16" />
            <Input type="color" value={creating.color_secondary} onChange={(e) => setCreating({ ...creating, color_secondary: e.target.value })} className="bg-zinc-950 border-zinc-800 w-16" />
            <Input type="number" placeholder="Preț (monede)" value={creating.price_coins} onChange={(e) => setCreating({ ...creating, price_coins: parseInt(e.target.value || "0") })} className="bg-zinc-950 border-zinc-800" data-testid="new-frame-price" />
          </div>
          <Button onClick={create} disabled={busy} className="pro-gradient text-white border-0" data-testid="new-frame-create">
            <Plus size={14} className="mr-1" /> Creează
          </Button>
        </div>
      </div>

      <div className="overflow-x-auto">
        <table className="w-full text-sm" data-testid="frames-table">
          <thead>
            <tr className="text-zinc-400 text-left border-b border-zinc-800">
              <th className="py-2 px-2">Nume</th>
              <th className="py-2 px-2">Efect</th>
              <th className="py-2 px-2">Raritate</th>
              <th className="py-2 px-2">Culori</th>
              <th className="py-2 px-2">Preț</th>
              <th className="py-2 px-2">Activ</th>
              <th className="py-2 px-2"></th>
            </tr>
          </thead>
          <tbody>
            {frames.map((f) => (
              <tr key={f.id} className="border-b border-zinc-900 hover:bg-zinc-900/50" data-testid={`frame-row-${f.id}`}>
                <td className="py-2 px-2">
                  <Input
                    defaultValue={f.name}
                    onBlur={(e) => e.target.value !== f.name && upd(f.id, { name: e.target.value })}
                    className="bg-zinc-950 border-zinc-800 h-8"
                  />
                </td>
                <td className="py-2 px-2">
                  <select
                    defaultValue={f.effect_key}
                    onChange={(e) => upd(f.id, { effect_key: e.target.value })}
                    className="bg-zinc-950 border border-zinc-800 rounded-md px-2 py-1 text-xs"
                  >
                    {EFFECTS.map((e) => <option key={e} value={e}>{e}</option>)}
                  </select>
                </td>
                <td className="py-2 px-2">
                  <select
                    defaultValue={f.rarity}
                    onChange={(e) => upd(f.id, { rarity: e.target.value })}
                    className="bg-zinc-950 border border-zinc-800 rounded-md px-2 py-1 text-xs"
                  >
                    <option value="common">common</option>
                    <option value="rare">rare</option>
                    <option value="epic">epic</option>
                    <option value="legendary">legendary</option>
                  </select>
                </td>
                <td className="py-2 px-2">
                  <div className="flex gap-1">
                    <input type="color" defaultValue={f.color_primary} onBlur={(e) => e.target.value !== f.color_primary && upd(f.id, { color_primary: e.target.value })} className="h-7 w-10 rounded border border-zinc-800 bg-zinc-950" />
                    <input type="color" defaultValue={f.color_secondary} onBlur={(e) => e.target.value !== f.color_secondary && upd(f.id, { color_secondary: e.target.value })} className="h-7 w-10 rounded border border-zinc-800 bg-zinc-950" />
                  </div>
                </td>
                <td className="py-2 px-2">
                  <Input
                    type="number"
                    defaultValue={f.price_coins}
                    onBlur={(e) => parseInt(e.target.value) !== f.price_coins && upd(f.id, { price_coins: parseInt(e.target.value || "0") })}
                    className="bg-zinc-950 border-zinc-800 h-8 w-24"
                    data-testid={`frame-price-${f.id}`}
                  />
                </td>
                <td className="py-2 px-2">
                  <Switch checked={f.active} onCheckedChange={(v) => upd(f.id, { active: v })} />
                </td>
                <td className="py-2 px-2">
                  <Button size="sm" variant="destructive" onClick={() => del(f.id)} data-testid={`delete-frame-${f.id}`}>
                    <Trash2 size={14} />
                  </Button>
                </td>
              </tr>
            ))}
            {frames.length === 0 && (
              <tr><td colSpan={7} className="text-zinc-500 py-6 text-center">Niciun cadru. Apasă „Adaugă cele 50 implicite”.</td></tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}


function AnnouncementsTab() {
  const [list, setList] = useState([]);
  const [form, setForm] = useState({ title: "", content: "", active: true });
  const load = () => api.get("/announcements").then((r) => setList(r.data));
  useEffect(() => { load(); }, []);
  const create = async () => { await api.post("/announcements", form); setForm({ title: "", content: "", active: true }); load(); };
  const upd = async (id, patch) => { await api.patch(`/announcements/${id}`, patch); load(); };
  const del = async (id) => { await api.delete(`/announcements/${id}`); load(); };
  return (
    <div className="mt-6 space-y-4" data-testid="admin-announcements">
      <div className="bg-zinc-900 border border-zinc-800 rounded-xl p-4 space-y-3">
        <Input placeholder="Title" value={form.title} onChange={(e) => setForm({ ...form, title: e.target.value })} className="bg-zinc-950 border-zinc-800" />
        <Textarea placeholder="Content" value={form.content} onChange={(e) => setForm({ ...form, content: e.target.value })} className="bg-zinc-950 border-zinc-800" />
        <Button onClick={create} className="pro-gradient text-white border-0" data-testid="new-ann-btn">Create</Button>
      </div>
      {list.map((a) => (
        <div key={a.id} className="bg-zinc-900 border border-zinc-800 rounded-xl p-4 flex justify-between items-start">
          <div className="flex-1">
            <div className="font-semibold">{a.title}</div>
            <div className="text-sm text-zinc-400 whitespace-pre-line">{a.content}</div>
          </div>
          <div className="flex items-center gap-2">
            <Switch checked={a.active} onCheckedChange={(v) => upd(a.id, { active: v })} />
            <Button size="sm" variant="destructive" onClick={() => del(a.id)}><Trash2 size={14} /></Button>
          </div>
        </div>
      ))}
    </div>
  );
}

function ChatModerationTab() {
  const [bans, setBans] = useState({ users: [], guests: [] });
  const [msgs, setMsgs] = useState([]);

  const load = async () => {
    const [b, m] = await Promise.all([
      api.get("/admin/chat/bans"),
      api.get("/chat/messages?limit=100"),
    ]);
    setBans(b.data);
    setMsgs(m.data.slice().reverse()); // newest first
  };
  useEffect(() => { load(); }, []);

  const unbanUser = async (uid) => { await api.post(`/admin/chat/unban-user/${uid}`); load(); };
  const unbanGuest = async (gs) => { await api.post(`/admin/chat/unban-guest/${gs}`); load(); };
  const delMsg = async (id) => { await api.delete(`/admin/chat/messages/${id}`); load(); };
  const banFromMsg = async (m) => {
    const reason = window.prompt("Reason?", "spam");
    if (reason === null) return;
    if (m.user_id) {
      await api.post(`/admin/chat/ban-user/${m.user_id}`, { duration: "1week", reason });
    } else if (m.guest_session) {
      await api.post(`/admin/chat/ban-guest/${m.guest_session}`, { duration: "1week", reason });
    }
    load();
  };

  return (
    <div className="mt-6 space-y-6" data-testid="admin-chat-moderation">
      <div className="bg-zinc-900 border border-zinc-800 rounded-xl p-4">
        <h3 className="font-semibold mb-3">Recent messages (last 100)</h3>
        <div className="max-h-96 overflow-y-auto custom-scrollbar space-y-1.5">
          {msgs.map((m) => (
            <div key={m.id} className="flex items-start gap-2 text-sm border-b border-zinc-800/60 pb-1.5" data-testid={`mod-msg-${m.id}`}>
              <span className={`font-semibold ${m.role === "admin" ? "text-rose-400" : m.is_pro ? "text-amber-300" : "text-zinc-200"}`}>
                {m.username}
              </span>
              <span className="text-[10px] text-zinc-600">{m.role}{m.guest_session ? ` · ${m.guest_session.slice(0, 12)}…` : ""}</span>
              <span className="text-zinc-300 flex-1 break-words">{m.content}</span>
              <button onClick={() => banFromMsg(m)} className="text-zinc-500 hover:text-amber-400" title="Ban from chat"><Ban size={14} /></button>
              <button onClick={() => delMsg(m.id)} className="text-zinc-500 hover:text-red-400" title="Delete"><Trash2 size={14} /></button>
            </div>
          ))}
          {msgs.length === 0 && <div className="text-zinc-500 text-sm">No messages yet.</div>}
        </div>
      </div>

      <div className="bg-zinc-900 border border-zinc-800 rounded-xl p-4">
        <h3 className="font-semibold mb-3">Banned users ({bans.users.length})</h3>
        {bans.users.map((u) => (
          <div key={u.id} className="flex items-center justify-between bg-zinc-950 border border-zinc-800 rounded-md p-2 mb-1">
            <div className="text-sm">
              <span className="font-semibold">@{u.username}</span>
              <span className="text-xs text-zinc-500 ml-2">until {u.chat_banned_until?.slice(0, 16) || "permanent"} — {u.chat_banned_reason || "-"}</span>
            </div>
            <Button size="sm" variant="outline" onClick={() => unbanUser(u.id)}><ShieldOff size={12} className="mr-1" /> Unban</Button>
          </div>
        ))}
        {bans.users.length === 0 && <div className="text-zinc-500 text-sm">No banned users.</div>}
      </div>

      <div className="bg-zinc-900 border border-zinc-800 rounded-xl p-4">
        <h3 className="font-semibold mb-3">Banned guest sessions ({bans.guests.length})</h3>
        {bans.guests.map((g) => (
          <div key={g.guest_session} className="flex items-center justify-between bg-zinc-950 border border-zinc-800 rounded-md p-2 mb-1">
            <div className="text-sm">
              <code className="text-xs">{g.guest_session}</code>
              <span className="text-xs text-zinc-500 ml-2">until {g.banned_until?.slice(0, 16) || "permanent"} — {g.reason || "-"}</span>
            </div>
            <Button size="sm" variant="outline" onClick={() => unbanGuest(g.guest_session)}><ShieldOff size={12} className="mr-1" /> Unban</Button>
          </div>
        ))}
        {bans.guests.length === 0 && <div className="text-zinc-500 text-sm">No banned guests.</div>}
      </div>
    </div>
  );
}

function SettingsTab() {
  const [s, setS] = useState(null);
  const [pristine, setPristine] = useState(null);
  useEffect(() => {
    api.get("/admin/settings").then((r) => { setS(r.data); setPristine(r.data); });
  }, []);
  if (!s) return <div className="text-zinc-500">Loading...</div>;
  const upd = (k, v) => setS({ ...s, [k]: v });
  const dirty = pristine && JSON.stringify(s) !== JSON.stringify(pristine);
  const save = async () => {
    const { data } = await api.patch("/admin/settings", s);
    setS(data);
    setPristine(data);
    toast.success("Settings saved");
  };
  const reset = () => setS(pristine);
  const toggleRes = (r) => {
    const cur = s.enabled_resolutions || [];
    upd("enabled_resolutions", cur.includes(r) ? cur.filter((x) => x !== r) : [...cur, r]);
  };
  return (
    <div className="mt-6 space-y-6 max-w-3xl pb-24" data-testid="admin-settings">
      {/* Sticky save bar — always visible while editing settings */}
      <div className={`sticky top-0 z-30 -mx-4 px-4 py-2.5 backdrop-blur-md border-b transition-all ${dirty ? "bg-rose-500/15 border-rose-500/50" : "bg-zinc-900/80 border-zinc-800"}`}>
        <div className="flex items-center justify-between gap-2 max-w-3xl mx-auto">
          <span className="text-xs text-zinc-300">
            {dirty ? <span className="text-rose-300 font-semibold">● Modificări nesalvate</span> : <span className="text-zinc-500">Toate setările sunt salvate</span>}
          </span>
          <div className="flex gap-2">
            {dirty && <Button onClick={reset} size="sm" variant="ghost" data-testid="reset-settings">Anulează</Button>}
            <Button onClick={save} size="sm" disabled={!dirty} className="pro-gradient text-white border-0" data-testid="save-settings">
              Salvează toate setările
            </Button>
          </div>
        </div>
      </div>
      <Section title="Localization">
        <Field label="Default site language">
          <Select value={s.default_language || "ro"} onValueChange={(v) => upd("default_language", v)}>
            <SelectTrigger className="bg-zinc-950 border-zinc-800" data-testid="default-language-select"><SelectValue /></SelectTrigger>
            <SelectContent>
              <SelectItem value="ro">Română</SelectItem>
              <SelectItem value="en">English</SelectItem>
            </SelectContent>
          </Select>
        </Field>
        <p className="text-xs text-zinc-500">First-time visitors see the site in this language. Each visitor can switch later via the sidebar.</p>
      </Section>
      <Section title="Shorts">
        <Field label="Max Shorts duration (seconds)">
          <Input type="number" min={5} max={600} value={s.shorts_max_duration_sec ?? 60} onChange={(e) => upd("shorts_max_duration_sec", parseInt(e.target.value) || 60)} className="bg-zinc-950 border-zinc-800" data-testid="shorts-max-dur" />
        </Field>
        <p className="text-xs text-zinc-500">Videos shorter than this and vertical (9:16) are auto-classified as Shorts on upload.</p>
      </Section>
      <Section title="Live Chat">
        <Field label="Enable live chat"><Switch checked={!!s.live_chat_enabled} onCheckedChange={(v) => upd("live_chat_enabled", v)} data-testid="chat-enable-toggle" /></Field>
        <Field label="Allow guests to chat"><Switch checked={!!s.live_chat_guest_allowed} onCheckedChange={(v) => upd("live_chat_guest_allowed", v)} /></Field>
        <Field label="Max message length"><Input type="number" value={s.live_chat_max_message_length ?? 500} onChange={(e) => upd("live_chat_max_message_length", parseInt(e.target.value) || 500)} className="bg-zinc-950 border-zinc-800" /></Field>
        <Field label="Rate limit window (seconds)"><Input type="number" value={s.live_chat_rate_limit_seconds ?? 3} onChange={(e) => upd("live_chat_rate_limit_seconds", parseInt(e.target.value) || 3)} className="bg-zinc-950 border-zinc-800" /></Field>
      </Section>
      <Section title="Economie Monede">
        <Field label="Monede per Like (prima dată)">
          <Input type="number" min={0} value={s.coins_per_like ?? 1} onChange={(e) => upd("coins_per_like", parseInt(e.target.value) || 0)} className="bg-zinc-950 border-zinc-800" data-testid="coins-per-like" />
        </Field>
        <Field label="Monede per Comentariu">
          <Input type="number" min={0} value={s.coins_per_comment ?? 2} onChange={(e) => upd("coins_per_comment", parseInt(e.target.value) || 0)} className="bg-zinc-950 border-zinc-800" data-testid="coins-per-comment" />
        </Field>
        <Field label="Limită zilnică comentarii recompensate / video">
          <Input type="number" min={0} value={s.coins_comment_daily_cap_per_video ?? 10} onChange={(e) => upd("coins_comment_daily_cap_per_video", parseInt(e.target.value) || 0)} className="bg-zinc-950 border-zinc-800" data-testid="coins-cap-per-video" />
        </Field>
        <p className="text-xs text-zinc-500">Like-urile sunt recompensate o singură dată pe video (anti-farming). Setează la 0 pentru a dezactiva.</p>
      </Section>
      <Section title="Legacy migration">
        <Field label="Mark migrated legacy videos as PRO-only">
          <Switch checked={!!s.legacy_videos_pro_only} onCheckedChange={(v) => upd("legacy_videos_pro_only", v)} data-testid="legacy-pro-toggle" />
        </Field>
        <p className="text-xs text-zinc-500">When importing legacy databases via the migration tool, the imported videos default to PRO-only access.</p>
        <LegacyShortsControls />
      </Section>
      <Section title="FFmpeg & Uploads">
        <Field label="Concurrent transcodes"><Input type="number" value={s.ffmpeg_concurrency} onChange={(e) => upd("ffmpeg_concurrency", parseInt(e.target.value) || 1)} className="bg-zinc-950 border-zinc-800" /></Field>
        <Field label="Max upload size (MB)"><Input type="number" value={s.max_upload_size_mb} onChange={(e) => upd("max_upload_size_mb", parseInt(e.target.value) || 100)} className="bg-zinc-950 border-zinc-800" data-testid="max-upload-mb" /></Field>
        <Field label="Allow user uploads"><Switch checked={s.allow_user_uploads} onCheckedChange={(v) => upd("allow_user_uploads", v)} /></Field>
        <Field label="Bulk upload (multi-file)"><Switch checked={!!s.bulk_upload_enabled} onCheckedChange={(v) => upd("bulk_upload_enabled", v)} data-testid="bulk-upload-toggle" /></Field>
        <Field label="Bulk upload concurrency (1-6)"><Input type="number" min={1} max={6} value={s.bulk_upload_concurrency ?? 3} onChange={(e) => upd("bulk_upload_concurrency", Math.max(1, Math.min(6, parseInt(e.target.value) || 3)))} className="bg-zinc-950 border-zinc-800" /></Field>
        <Field label="Chunk size (MB) — chunked uploads"><Input type="number" min={1} max={500} value={s.chunk_upload_chunk_size_mb ?? 25} onChange={(e) => upd("chunk_upload_chunk_size_mb", Math.max(1, parseInt(e.target.value) || 25))} className="bg-zinc-950 border-zinc-800" /></Field>
        <Field label="Allow video download (player button)"><Switch checked={!!s.allow_video_download} onCheckedChange={(v) => upd("allow_video_download", v)} data-testid="allow-download-toggle" /></Field>
        <div>
          <Label className="mb-2 block">Enabled resolutions</Label>
          <div className="flex flex-wrap gap-2">
            {RES_OPTIONS.map((r) => (
              <button key={r} onClick={() => toggleRes(r)} className={`px-3 py-1.5 rounded-md border text-sm ${s.enabled_resolutions?.includes(r) ? "bg-rose-500 border-rose-500 text-white" : "bg-zinc-950 border-zinc-800 text-zinc-400"}`} data-testid={`res-${r}`}>
                {r}
              </button>
            ))}
          </div>
        </div>
      </Section>
      <Section title="Storage">
        <Field label="Backend">
          <Select value={s.storage_backend} onValueChange={(v) => upd("storage_backend", v)}>
            <SelectTrigger className="bg-zinc-950 border-zinc-800"><SelectValue /></SelectTrigger>
            <SelectContent><SelectItem value="local">Local</SelectItem><SelectItem value="wasabi">Wasabi S3</SelectItem></SelectContent>
          </Select>
        </Field>
        <Field label="Wasabi access key"><Input value={s.wasabi_access_key} onChange={(e) => upd("wasabi_access_key", e.target.value)} className="bg-zinc-950 border-zinc-800" /></Field>
        <Field label="Wasabi secret key"><Input type="password" value={s.wasabi_secret_key} onChange={(e) => upd("wasabi_secret_key", e.target.value)} className="bg-zinc-950 border-zinc-800" /></Field>
        <Field label="Wasabi bucket"><Input value={s.wasabi_bucket} onChange={(e) => upd("wasabi_bucket", e.target.value)} className="bg-zinc-950 border-zinc-800" /></Field>
        <Field label="Wasabi region"><Input value={s.wasabi_region} onChange={(e) => upd("wasabi_region", e.target.value)} className="bg-zinc-950 border-zinc-800" /></Field>
        <Field label="Wasabi endpoint"><Input value={s.wasabi_endpoint} onChange={(e) => upd("wasabi_endpoint", e.target.value)} className="bg-zinc-950 border-zinc-800" /></Field>
        <Field label="Public base URL (optional CDN)"><Input value={s.wasabi_public_base_url || ""} onChange={(e) => upd("wasabi_public_base_url", e.target.value)} className="bg-zinc-950 border-zinc-800" placeholder="https://cdn.example.com/bucket" /></Field>
        <Button variant="outline" onClick={async () => {
          try { const { data } = await api.post("/admin/wasabi/test"); data.ok ? toast.success(data.message) : toast.error(data.message); }
          catch (e) { toast.error(e.response?.data?.detail || "Failed"); }
        }} data-testid="test-wasabi"><RefreshCw size={14} className="mr-2" /> Test Wasabi connection</Button>
      </Section>
      <Section title="SMTP / Email verification">
        <Field label="Require email verification"><Switch checked={s.require_email_verification} onCheckedChange={(v) => upd("require_email_verification", v)} /></Field>
        <Field label="SMTP enabled"><Switch checked={s.smtp_enabled} onCheckedChange={(v) => upd("smtp_enabled", v)} /></Field>
        <Field label="SMTP host"><Input value={s.smtp_host} onChange={(e) => upd("smtp_host", e.target.value)} className="bg-zinc-950 border-zinc-800" placeholder="smtp.gmail.com" /></Field>
        <Field label="SMTP port"><Input type="number" value={s.smtp_port} onChange={(e) => upd("smtp_port", parseInt(e.target.value) || 587)} className="bg-zinc-950 border-zinc-800" placeholder="587 (STARTTLS) or 465 (SSL)" /></Field>
        <Field label="Security">
          <Select
            value={s.smtp_security || "auto"}
            onValueChange={(v) => upd("smtp_security", v === "auto" ? "" : v)}
          >
            <SelectTrigger className="bg-zinc-950 border-zinc-800" data-testid="smtp-security-select"><SelectValue /></SelectTrigger>
            <SelectContent>
              <SelectItem value="auto">Auto (recommended)</SelectItem>
              <SelectItem value="starttls">STARTTLS (port 587)</SelectItem>
              <SelectItem value="ssl">SSL / implicit TLS (port 465)</SelectItem>
              <SelectItem value="none">None (plaintext)</SelectItem>
            </SelectContent>
          </Select>
        </Field>
        <Field label="SMTP user"><Input value={s.smtp_user} onChange={(e) => upd("smtp_user", e.target.value)} className="bg-zinc-950 border-zinc-800" placeholder="your.address@gmail.com" /></Field>
        <Field label="SMTP password"><Input type="password" value={s.smtp_password} onChange={(e) => upd("smtp_password", e.target.value)} className="bg-zinc-950 border-zinc-800" placeholder="Gmail: 16-char App Password" /></Field>
        <Field label="From address"><Input value={s.smtp_from} onChange={(e) => upd("smtp_from", e.target.value)} className="bg-zinc-950 border-zinc-800" placeholder="zore.zore1993@gmail.com" /></Field>
        <SmtpTestControls contactEmail={s.contact_email} />
        <p className="text-xs text-zinc-500 col-span-2">
          <strong>Gmail tip:</strong> enable 2-Step Verification, then create an{" "}
          <a className="text-rose-400 hover:text-rose-300 underline" href="https://myaccount.google.com/apppasswords" target="_blank" rel="noreferrer">App Password</a>
          {" "}for "Mail" — paste it as the SMTP password (spaces are stripped automatically).
          Use port <strong>587 + STARTTLS</strong> <em>or</em> port <strong>465 + SSL</strong>, not both.
        </p>
      </Section>
      <Section title="Stripe">
        <Field label="Stripe secret key (leave blank to use env)"><Input type="password" value={s.stripe_secret_key} onChange={(e) => upd("stripe_secret_key", e.target.value)} className="bg-zinc-950 border-zinc-800" /></Field>
        <Field label="Stripe publishable key"><Input value={s.stripe_publishable_key} onChange={(e) => upd("stripe_publishable_key", e.target.value)} className="bg-zinc-950 border-zinc-800" /></Field>
      </Section>
      <Section title="Signed URL Protection (Pro videos)">
        <Field label="Signed URL TTL (seconds)">
          <Input type="number" value={s.signed_url_ttl_seconds || 300} onChange={(e) => upd("signed_url_ttl_seconds", parseInt(e.target.value) || 300)} className="bg-zinc-950 border-zinc-800" />
        </Field>
        <p className="text-xs text-zinc-500">Pro-tier video URLs are signed/presigned and expire after this many seconds. Short TTL = more piracy protection. Recommended: 300 (5 minutes).</p>
      </Section>
      <Section title="CloudFront (advanced — overrides S3 presign)">
        <Field label="Use CloudFront"><Switch checked={!!s.cloudfront_enabled} onCheckedChange={(v) => upd("cloudfront_enabled", v)} /></Field>
        <Field label="CloudFront domain"><Input value={s.cloudfront_domain || ""} onChange={(e) => upd("cloudfront_domain", e.target.value)} placeholder="d123abcd.cloudfront.net" className="bg-zinc-950 border-zinc-800" /></Field>
        <Field label="Key Pair ID"><Input value={s.cloudfront_key_pair_id || ""} onChange={(e) => upd("cloudfront_key_pair_id", e.target.value)} className="bg-zinc-950 border-zinc-800" /></Field>
        <div className="col-span-2"><Label>Private key (PEM)</Label>
          <Textarea rows={6} value={s.cloudfront_private_key || ""} onChange={(e) => upd("cloudfront_private_key", e.target.value)} placeholder="-----BEGIN RSA PRIVATE KEY-----..." className="bg-zinc-950 border-zinc-800 font-mono text-xs" /></div>
        <p className="text-xs text-zinc-500 col-span-2">When enabled, signed URLs are issued by CloudFront instead of S3 presign.</p>
      </Section>
      <Section title="Contact form">
        <Field label="Contact email"><Input type="email" value={s.contact_email || ""} onChange={(e) => upd("contact_email", e.target.value)} placeholder="contact@yourdomain.com" className="bg-zinc-950 border-zinc-800" data-testid="contact-email-setting" /></Field>
        <p className="text-xs text-zinc-500">Messages from /contact are sent to this address (requires SMTP to be enabled).</p>
      </Section>
      <Section title="✨ AI Synopsis (SEO)">
        <Field label="Enable AI synopsis generation">
          <Switch
            checked={s.ai_synopsis_enabled ?? true}
            onCheckedChange={(v) => upd("ai_synopsis_enabled", v)}
            data-testid="ai-synopsis-enabled"
          />
        </Field>
        <Field label="Emergent LLM Key">
          <Input
            type="password"
            value={s.emergent_llm_key || ""}
            onChange={(e) => upd("emergent_llm_key", e.target.value)}
            placeholder="sk-emergent-…"
            className="bg-zinc-950 border-zinc-800 font-mono"
            autoComplete="off"
            data-testid="emergent-llm-key"
          />
        </Field>
        <p className="text-xs text-zinc-500">
          Obții cheia din <a href="https://app.emergent.sh/profile/universal-key" target="_blank" rel="noreferrer" className="text-violet-400 hover:underline">Emergent → Profile → Universal Key</a>. Cheia se stochează în MongoDB și este folosită doar server-side (nu apare în răspunsuri API).
        </p>
        <Field label="Daily generation limit">
          <Input
            type="number"
            min="1" max="1000"
            value={s.ai_synopsis_daily_limit ?? 50}
            onChange={(e) => upd("ai_synopsis_daily_limit", parseInt(e.target.value || 50))}
            className="bg-zinc-950 border-zinc-800 w-32"
            data-testid="ai-synopsis-limit"
          />
        </Field>
        <Field label="Model">
          <Select value={s.ai_synopsis_model || "claude-haiku-4-5-20251001"} onValueChange={(v) => upd("ai_synopsis_model", v)}>
            <SelectTrigger className="bg-zinc-950 border-zinc-800 max-w-md" data-testid="ai-synopsis-model"><SelectValue /></SelectTrigger>
            <SelectContent>
              <SelectItem value="claude-haiku-4-5-20251001">Claude Haiku 4.5 (recomandat · ~$0.002/generare)</SelectItem>
              <SelectItem value="gemini-3-flash-preview">Gemini 3 Flash (cel mai ieftin · ~$0.0007/generare)</SelectItem>
              <SelectItem value="claude-sonnet-4-6">Claude Sonnet 4.6 (calitate max · ~$0.02/generare)</SelectItem>
              <SelectItem value="gpt-5.4-mini">GPT-5.4 Mini (~$0.003/generare)</SelectItem>
            </SelectContent>
          </Select>
        </Field>
        <p className="text-xs text-zinc-500">
          Folosește Emergent Universal LLM Key. Balanță și top-up: Profile → Universal Key.
          Sinopsis-urile generate se salvează automat pentru bulk; per-video ai preview + accept.
        </p>
      </Section>
      <Section title="💬 Discord community">
        <Field label="Enable Discord widget">
          <Switch
            checked={s.discord_widget_enabled ?? true}
            onCheckedChange={(v) => upd("discord_widget_enabled", v)}
            data-testid="discord-enabled-switch"
          />
        </Field>
        <Field label="Invite URL">
          <Input
            value={s.discord_invite_url || ""}
            onChange={(e) => upd("discord_invite_url", e.target.value)}
            placeholder="https://discord.gg/5dGdSbzT4E"
            className="bg-zinc-950 border-zinc-800"
            data-testid="discord-invite-input"
          />
        </Field>
        <Field label="Server (Guild) ID">
          <Input
            value={s.discord_guild_id || ""}
            onChange={(e) => upd("discord_guild_id", e.target.value)}
            placeholder="e.g. 1234567890123456789"
            className="bg-zinc-950 border-zinc-800"
            data-testid="discord-guild-input"
          />
        </Field>
        <div className="text-xs text-zinc-500 space-y-1">
          <p>
            <strong>How to enable the embed widget</strong> (shows live members + #general):
          </p>
          <ol className="list-decimal list-inside pl-2 space-y-0.5">
            <li>In Discord, open <em>Server Settings → Widget</em> and toggle <strong>Enable Server Widget</strong>.</li>
            <li>Copy the <em>Server ID</em> from <em>Server Settings → Widget</em> (or right-click the server icon → "Copy Server ID" with developer mode on) and paste above.</li>
            <li>Save. If guild ID is empty, users see a simple "Join our Discord" card linking to the invite URL.</li>
          </ol>
        </div>
      </Section>
      <Section title="Site / SEO">
        <Field label="Site title"><Input value={s.site_title || ""} onChange={(e) => upd("site_title", e.target.value)} className="bg-zinc-950 border-zinc-800" data-testid="site-title-input" /></Field>
        <Field label="Description"><Input value={s.site_description || ""} onChange={(e) => upd("site_description", e.target.value)} className="bg-zinc-950 border-zinc-800" /></Field>
        <div className="col-span-2">
          <Label>Home page hero text (overrides translation)</Label>
          <Textarea
            rows={2}
            value={s.home_hero_text || ""}
            onChange={(e) => upd("home_hero_text", e.target.value)}
            className="bg-zinc-950 border-zinc-800"
            placeholder="Watch hentai subtitled in Romanian in 1080P - 4096P quality."
            data-testid="home-hero-input"
          />
          <p className="text-xs text-zinc-500 mt-1">Apare în header-ul homepage-ului. Lasă gol pentru a folosi traducerea implicită.</p>
        </div>
        <Field label="Favicon URL"><Input value={s.site_favicon_url || ""} onChange={(e) => upd("site_favicon_url", e.target.value)} className="bg-zinc-950 border-zinc-800" placeholder="https://.../favicon.ico" /></Field>
        <Field label="Canonical URL"><Input value={s.site_canonical_url || ""} onChange={(e) => upd("site_canonical_url", e.target.value)} className="bg-zinc-950 border-zinc-800" placeholder="https://gleague.eu" /></Field>
        <Field label="Default OG image (for link previews)"><Input value={s.site_og_image || ""} onChange={(e) => upd("site_og_image", e.target.value)} className="bg-zinc-950 border-zinc-800" placeholder="https://.../share.png or path on Wasabi" /></Field>
        <SiteLogoControls
          current={s.site_logo_url}
          onChange={(url) => upd("site_logo_url", url)}
        />
        <Field label="SEO keywords"><Input value={s.site_seo_keywords || ""} onChange={(e) => upd("site_seo_keywords", e.target.value)} className="bg-zinc-950 border-zinc-800" placeholder="videos, streaming, ..." /></Field>
        <div className="col-span-2"><Label>Additional &lt;meta&gt; tags (raw HTML)</Label>
          <Textarea rows={3} value={s.site_seo_meta || ""} onChange={(e) => upd("site_seo_meta", e.target.value)} className="bg-zinc-950 border-zinc-800 font-mono text-xs" placeholder='<meta property="og:image" content="...">' /></div>
      </Section>
      <Section title="Auth security">
        <Field label="Min password length"><Input type="number" value={s.min_password_length || 8} onChange={(e) => upd("min_password_length", parseInt(e.target.value) || 8)} className="bg-zinc-950 border-zinc-800" /></Field>
        <Field label="Require complexity (letter+digit+symbol)"><Switch checked={!!s.require_password_complexity} onCheckedChange={(v) => upd("require_password_complexity", v)} /></Field>
        <Field label="Login attempts before lockout"><Input type="number" value={s.login_rate_limit_max || 5} onChange={(e) => upd("login_rate_limit_max", parseInt(e.target.value) || 5)} className="bg-zinc-950 border-zinc-800" /></Field>
        <Field label="Lockout window (seconds)"><Input type="number" value={s.login_rate_limit_window || 300} onChange={(e) => upd("login_rate_limit_window", parseInt(e.target.value) || 300)} className="bg-zinc-950 border-zinc-800" /></Field>
      </Section>
      <Section title="GitHub auto-update">
        <GithubUpdateControls />
      </Section>
      <Section title="Disk maintenance">
        <PendingUploadsCard />
      </Section>
    </div>
  );
}


function PendingUploadsCard() {
  const [info, setInfo] = useState(null);
  const [busy, setBusy] = useState(false);
  const load = () => api.get("/admin/uploads/pending").then((r) => setInfo(r.data));
  useEffect(() => { load(); }, []);
  const cleanup = async (force) => {
    if (!window.confirm(force ? "Șterge TOATE upload-urile în așteptare?" : "Șterge upload-urile abandonate (>24h)?")) return;
    setBusy(true);
    try {
      const { data } = await api.post("/admin/uploads/cleanup", { force });
      toast.success(`${data.purged} upload(uri) șterse`);
      load();
    } finally { setBusy(false); }
  };
  if (!info) return <div className="text-xs text-zinc-500 col-span-2">Loading...</div>;
  const totalMB = Math.round((info.total_bytes || 0) / (1024 * 1024));
  return (
    <div className="col-span-2 bg-zinc-950 border border-zinc-800 rounded-md p-3 space-y-3" data-testid="pending-uploads-card">
      <div className="flex items-center justify-between flex-wrap gap-2">
        <div>
          <p className="text-sm font-semibold text-zinc-100">Upload-uri în așteptare</p>
          <p className="text-xs text-zinc-500">
            {info.count} în total · {info.stale_count} abandonate (>24h) · {totalMB} MB pe disc
          </p>
        </div>
        <div className="flex gap-2 flex-wrap">
          <Button size="sm" variant="outline" onClick={() => load()} disabled={busy}>Reîmprospătează</Button>
          <Button size="sm" onClick={() => cleanup(false)} disabled={busy || info.stale_count === 0} data-testid="cleanup-stale-btn">
            Șterge cele abandonate ({info.stale_count})
          </Button>
          <Button size="sm" variant="destructive" onClick={() => cleanup(true)} disabled={busy || info.count === 0}>
            Șterge TOATE
          </Button>
        </div>
      </div>
      {info.items?.length > 0 && (
        <div className="max-h-48 overflow-y-auto border border-zinc-800 rounded">
          <table className="w-full text-xs">
            <thead className="bg-zinc-900 text-zinc-400 sticky top-0">
              <tr><th className="text-left p-2">Fișier</th><th className="text-left p-2">User</th><th className="text-right p-2">Progres</th><th className="text-right p-2">Vârstă</th></tr>
            </thead>
            <tbody>
              {info.items.map((it) => {
                const pct = it.total_size ? Math.round((it.received_size / it.total_size) * 100) : 0;
                return (
                  <tr key={it.upload_id} className={`border-t border-zinc-900 ${it.stale ? "text-amber-300" : ""}`}>
                    <td className="p-2 truncate max-w-[12rem]">{it.filename}</td>
                    <td className="p-2 text-zinc-500 truncate max-w-[6rem]">{(it.user_id || "?").slice(0, 8)}</td>
                    <td className="p-2 text-right">{pct}% · {Math.round(it.received_size / 1024 / 1024)} MB</td>
                    <td className="p-2 text-right">{it.age_hours}h</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

function Section({ title, children }) {
  return (
    <div className="bg-zinc-900 border border-zinc-800 rounded-xl p-5 space-y-4">
      <div className="font-heading font-semibold text-lg">{title}</div>
      {children}
    </div>
  );
}

function SmtpTestControls({ contactEmail }) {
  const [to, setTo] = useState(contactEmail || "");
  const [busy, setBusy] = useState(false);
  useEffect(() => {
    if (contactEmail && !to) setTo(contactEmail);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [contactEmail]);
  const send = async () => {
    if (!to.trim()) { toast.error("Enter a recipient email"); return; }
    setBusy(true);
    try {
      const { data } = await api.post("/admin/smtp/test", { to: to.trim() });
      toast.success(`✓ Test email sent to ${data.sent_to}`);
    } catch (err) {
      toast.error(err.response?.data?.detail || "SMTP test failed", { duration: 10000 });
    } finally { setBusy(false); }
  };
  return (
    <div className="col-span-2 bg-zinc-950 border border-zinc-800 rounded-md p-3 space-y-2" data-testid="smtp-test-controls">
      <Label className="m-0">Send a test email (uses the SMTP settings currently saved)</Label>
      <div className="flex flex-wrap gap-2">
        <Input
          value={to}
          onChange={(e) => setTo(e.target.value)}
          placeholder="recipient@example.com"
          className="bg-zinc-900 border-zinc-800 flex-1 min-w-[200px]"
          data-testid="smtp-test-to"
        />
        <Button onClick={send} disabled={busy} className="pro-gradient text-white border-0" data-testid="smtp-test-send">
          {busy ? "Sending…" : "Send test email"}
        </Button>
      </div>
      <p className="text-xs text-zinc-500">If it fails, the toast shows the exact SMTP error so you can diagnose (wrong password, wrong port, firewall, etc.).</p>
    </div>
  );
}

function SiteLogoControls({ current, onChange }) {
  const { refreshSiteCfg } = useT();
  const [busy, setBusy] = useState(false);
  const [file, setFile] = useState(null);

  const upload = async (e) => {
    e?.preventDefault();
    if (!file) return;
    setBusy(true);
    try {
      const fd = new FormData();
      fd.append("file", file);
      const { data } = await api.post("/admin/site/logo", fd, {
        headers: { "Content-Type": "multipart/form-data" },
      });
      onChange?.(data.site_logo_url);
      await refreshSiteCfg();
      toast.success("Logo updated");
      setFile(null);
    } catch (err) {
      toast.error(err.response?.data?.detail || "Upload failed");
    } finally {
      setBusy(false);
    }
  };

  const reset = async () => {
    if (!window.confirm("Reset to the default 'S + StreamHub' wordmark?")) return;
    setBusy(true);
    try {
      await api.delete("/admin/site/logo");
      onChange?.("");
      await refreshSiteCfg();
      toast.success("Logo reset");
    } catch (err) {
      toast.error(err.response?.data?.detail || "Failed");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="col-span-2 bg-zinc-950 border border-zinc-800 rounded-md p-4 space-y-3" data-testid="site-logo-controls">
      <Label className="m-0 block">Brand logo (replaces "S + StreamHub" in the left sidebar)</Label>
      <div className="flex items-center gap-4">
        <div
          className="h-16 w-44 bg-zinc-900 border border-zinc-800 rounded-md flex items-center justify-center overflow-hidden"
          data-testid="site-logo-preview"
        >
          {current ? (
            <img src={mediaUrl(current)} alt="Logo preview" className="max-h-full max-w-full object-contain" />
          ) : (
            <div className="flex items-center gap-2 text-zinc-500 text-sm">
              <div className="h-7 w-7 rounded-md pro-gradient flex items-center justify-center font-heading font-bold text-white">S</div>
              <span className="font-heading font-bold">StreamHub</span>
            </div>
          )}
        </div>
        <form onSubmit={upload} className="flex-1 flex flex-wrap items-center gap-2">
          <Input
            type="file"
            accept="image/png,image/jpeg,image/webp,image/gif,image/svg+xml"
            onChange={(e) => setFile(e.target.files?.[0] || null)}
            className="bg-zinc-900 border-zinc-800 flex-1 min-w-[200px]"
            data-testid="site-logo-file"
          />
          <Button
            type="submit"
            disabled={busy || !file}
            className="pro-gradient text-white border-0 disabled:opacity-50"
            data-testid="site-logo-upload"
          >
            <UploadIcon size={14} className="mr-1" />
            {busy ? "Uploading…" : "Upload"}
          </Button>
          {current && (
            <Button
              type="button"
              variant="outline"
              onClick={reset}
              disabled={busy}
              className="border-zinc-700 hover:bg-zinc-800"
              data-testid="site-logo-reset"
            >
              <ImageOff size={14} className="mr-1" /> Reset
            </Button>
          )}
        </form>
      </div>
      <p className="text-xs text-zinc-500">
        Recommended: a horizontal PNG/SVG with transparent background, ~600×120px. The sidebar
        renders it at 36 px tall (h-9) and caps width at 180 px.
      </p>
    </div>
  );
}

function LegacyShortsControls() {
  const [stats, setStats] = useState(null);
  const [busy, setBusy] = useState(false);

  const load = async () => {
    try {
      const { data } = await api.get("/admin/videos/legacy-stats");
      setStats(data);
    } catch (e) {
      console.error(e);
    }
  };
  useEffect(() => { load(); }, []);

  const mark = async (mode, on) => {
    // mode: "shorts" | "pro" ; on: boolean
    const labels = {
      "shorts-true":  ["Shorts", "/admin/videos/mark-legacy-as-shorts"],
      "shorts-false": ["regular Videos", "/admin/videos/mark-legacy-as-videos"],
      "pro-true":     ["PRO-only", "/admin/videos/mark-legacy-as-pro"],
      "pro-false":    ["free", "/admin/videos/mark-legacy-as-free"],
    };
    const [verb, url] = labels[`${mode}-${on}`];
    if (!window.confirm(`Mark ALL ${stats?.total_legacy ?? 0} migrated legacy videos as ${verb}? This affects every video that came from your legacy DB migration.`)) return;
    setBusy(true);
    try {
      const { data } = await api.post(url);
      toast.success(`Updated ${data.modified} of ${data.matched} legacy videos`);
      await load();
    } catch (e) {
      toast.error(e.response?.data?.detail || "Failed");
    } finally { setBusy(false); }
  };

  if (!stats) return null;
  return (
    <div className="bg-zinc-950 border border-zinc-800 rounded-md p-3 space-y-3 mt-3" data-testid="legacy-shorts-controls">
      <div className="text-sm space-y-1">
        <div>
          <span className="font-semibold">Migrated catalogue:</span>{" "}
          <span className="text-zinc-300">{stats.total_legacy} total</span>
        </div>
        {stats.total_legacy > 0 && (
          <div className="text-xs text-zinc-400">
            <span className="text-fuchsia-300">{stats.legacy_as_shorts} as Shorts</span>{" "}
            <span className="text-zinc-600">·</span>{" "}
            <span>{stats.legacy_as_videos} as long-form videos</span>{" "}
            <span className="text-zinc-600">·</span>{" "}
            <span className="text-amber-300">{stats.legacy_as_pro} PRO-only</span>{" "}
            <span className="text-zinc-600">·</span>{" "}
            <span>{stats.legacy_as_free} free</span>
          </div>
        )}
      </div>
      {stats.total_legacy > 0 && (
        <>
          <div className="flex flex-wrap gap-2">
            <Button
              size="sm"
              variant="outline"
              disabled={busy}
              onClick={() => mark("shorts", true)}
              className="border-zinc-700 hover:bg-zinc-800"
              data-testid="mark-legacy-shorts"
            >
              Mark all legacy as Shorts
            </Button>
            <Button
              size="sm"
              variant="outline"
              disabled={busy}
              onClick={() => mark("shorts", false)}
              className="border-zinc-700 hover:bg-zinc-800"
              data-testid="mark-legacy-videos"
            >
              Mark all legacy as long-form videos
            </Button>
          </div>
          <div className="flex flex-wrap gap-2">
            <Button
              size="sm"
              disabled={busy}
              onClick={() => mark("pro", true)}
              className="pro-gradient text-white border-0 disabled:opacity-50"
              data-testid="mark-legacy-pro"
            >
              <Crown size={12} className="mr-1" /> Mark all legacy as PRO-only
            </Button>
            <Button
              size="sm"
              variant="outline"
              disabled={busy}
              onClick={() => mark("pro", false)}
              className="border-zinc-700 hover:bg-zinc-800"
              data-testid="mark-legacy-free"
            >
              Make all legacy free
            </Button>
          </div>
        </>
      )}
      <p className="text-xs text-zinc-500">
        Use the PRO button to gate every imported video behind the subscription paywall —
        same effect as running the migration with the <code>--all-pro</code> flag, but applied
        retroactively. Toggle back any time.
      </p>
    </div>
  );
}

function GithubUpdateControls() {
  const [status, setStatus] = useState(null);
  const [busy, setBusy] = useState(false);
  // Mode: "token" (default — paste URL + PAT) vs "url" (raw URL with embedded creds)
  const [mode, setMode] = useState("token");
  const [showRemoteForm, setShowRemoteForm] = useState(false);
  // Token-mode fields
  const [repoUrl, setRepoUrl] = useState("");
  const [pat, setPat] = useState("");
  // URL-mode fields
  const [remoteUrl, setRemoteUrl] = useState("");
  const [remoteBranch, setRemoteBranch] = useState("main");

  const check = async () => {
    setBusy(true);
    try { const { data } = await api.get("/admin/github/check"); setStatus(data); }
    catch (e) { toast.error(e.response?.data?.detail || "Check failed"); }
    finally { setBusy(false); }
  };
  const update = async () => {
    if (!window.confirm("Pull latest code and rebuild containers? The site may be briefly unavailable.")) return;
    setBusy(true);
    try {
      const { data } = await api.post("/admin/github/update");
      if (data.pull_rc === 0) toast.success("Update applied. Rebuilding…"); else toast.error("git pull failed — see console");
      console.log("[github/update]", data);
      setTimeout(check, 4000);
    } catch (e) {
      toast.error(e.response?.data?.detail || "Update failed");
    } finally { setBusy(false); }
  };
  const saveWithToken = async (e) => {
    e?.preventDefault();
    if (!repoUrl.trim() || !pat.trim()) {
      toast.error("Repo URL and Token are both required");
      return;
    }
    setBusy(true);
    try {
      await api.post("/admin/github/set-remote-with-token", {
        repo_url: repoUrl.trim(),
        token: pat.trim(),
        branch: remoteBranch.trim() || "main",
      });
      toast.success("Remote configured — connectivity verified");
      setShowRemoteForm(false);
      setPat("");
      await check();
    } catch (e) {
      toast.error(e.response?.data?.detail || "Failed to set remote");
    } finally { setBusy(false); }
  };
  const saveRawUrl = async (e) => {
    e?.preventDefault();
    if (!remoteUrl.trim()) return;
    setBusy(true);
    try {
      await api.post("/admin/github/set-remote", { url: remoteUrl.trim(), branch: remoteBranch.trim() || "main" });
      toast.success("Remote configured");
      setShowRemoteForm(false);
      await check();
    } catch (e) {
      toast.error(e.response?.data?.detail || "Failed to set remote");
    } finally { setBusy(false); }
  };
  const unsetRemote = async () => {
    if (!window.confirm("Remove the configured git remote?")) return;
    setBusy(true);
    try {
      await api.delete("/admin/github/remote");
      toast.success("Remote removed");
      await check();
    } catch (e) {
      toast.error(e.response?.data?.detail || "Failed");
    } finally { setBusy(false); }
  };
  useEffect(() => { check(); }, []);

  const hasErrors = status?.errors?.length > 0;
  const needsRemote = !status?.remote_url;

  return (
    <div className="space-y-3" data-testid="github-update-controls">
      {status && (
        <div className="text-sm text-zinc-400 space-y-1">
          <div>Repo path: <code className="text-zinc-200">{status.repo_path}</code></div>
          <div>Remote: <code className="text-zinc-200 break-all">{status.remote_url || "—"}</code></div>
          <div>Branch: <code className="text-zinc-200">{status.branch}</code></div>
          <div>Current: <code className="text-zinc-200">{status.local_commit || "?"}</code> · Latest on origin: <code className="text-zinc-200">{status.remote_commit || "?"}</code></div>
          <div>
            {status.has_update
              ? <span className="text-rose-400">▲ {status.behind} commit(s) behind — update available</span>
              : status.local_commit && status.remote_commit
                ? <span className="text-emerald-400">✓ Up-to-date</span>
                : <span className="text-zinc-500">Status unknown — see diagnostics below</span>}
          </div>
        </div>
      )}
      {hasErrors && (
        <div className="bg-red-950/40 border border-red-900 rounded-md p-3 text-xs text-red-300 space-y-1" data-testid="github-errors">
          <div className="font-semibold text-red-200">Diagnostics</div>
          {status.errors.map((e, i) => <div key={i} className="font-mono break-all">• {e}</div>)}
        </div>
      )}
      <div className="flex flex-wrap gap-2">
        <Button variant="outline" disabled={busy} onClick={check} data-testid="gh-check">
          <RefreshCw size={14} className={`mr-2 ${busy ? "animate-spin" : ""}`} /> Check for updates
        </Button>
        <Button
          disabled={busy || !status?.has_update}
          onClick={update}
          className="pro-gradient text-white border-0 disabled:opacity-50"
          data-testid="gh-update"
        >
          Update
        </Button>
        <Button variant="outline" onClick={() => setShowRemoteForm((s) => !s)} data-testid="gh-config-remote-toggle">
          {needsRemote ? "Configure remote" : "Change remote"}
        </Button>
        {!needsRemote && (
          <Button variant="outline" onClick={unsetRemote} disabled={busy} data-testid="gh-unset-remote">
            Unset remote
          </Button>
        )}
      </div>
      {showRemoteForm && (
        <div className="bg-zinc-950 border border-zinc-800 rounded-md p-3 space-y-3" data-testid="gh-remote-form">
          <div className="flex gap-2" data-testid="gh-mode-tabs">
            <button
              type="button"
              onClick={() => setMode("token")}
              className={`px-3 py-1.5 text-xs rounded-md border ${mode === "token" ? "bg-rose-500 border-rose-500 text-white" : "bg-zinc-900 border-zinc-800 text-zinc-300"}`}
              data-testid="gh-mode-token"
            >
              Repo URL + Personal Access Token (recommended)
            </button>
            <button
              type="button"
              onClick={() => setMode("url")}
              className={`px-3 py-1.5 text-xs rounded-md border ${mode === "url" ? "bg-rose-500 border-rose-500 text-white" : "bg-zinc-900 border-zinc-800 text-zinc-300"}`}
              data-testid="gh-mode-url"
            >
              Raw URL
            </button>
          </div>

          {mode === "token" ? (
            <form onSubmit={saveWithToken} className="space-y-2" data-testid="gh-token-form">
              <Label>Repository URL</Label>
              <Input
                value={repoUrl}
                onChange={(e) => setRepoUrl(e.target.value)}
                placeholder="https://github.com/<owner>/<repo>.git"
                className="bg-zinc-900 border-zinc-800"
                data-testid="gh-token-repo"
              />
              <Label>Personal Access Token (ghp_…)</Label>
              <Input
                type="password"
                autoComplete="new-password"
                value={pat}
                onChange={(e) => setPat(e.target.value)}
                placeholder="ghp_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"
                className="bg-zinc-900 border-zinc-800 font-mono text-xs"
                data-testid="gh-token-pat"
              />
              <Label>Branch</Label>
              <Input
                value={remoteBranch}
                onChange={(e) => setRemoteBranch(e.target.value)}
                placeholder="main"
                className="bg-zinc-900 border-zinc-800"
                data-testid="gh-token-branch"
              />
              <div className="flex gap-2">
                <Button type="submit" disabled={busy || !repoUrl.trim() || !pat.trim()} className="pro-gradient text-white border-0" data-testid="gh-token-save">
                  Save & verify
                </Button>
                <Button type="button" variant="outline" onClick={() => setShowRemoteForm(false)}>Cancel</Button>
              </div>
              <p className="text-xs text-zinc-500">
                The token is embedded into git's on-disk config (never shown back in the UI). We
                fire one <code>git fetch</code> to verify the token before saving, so an invalid
                token gets rejected here instead of failing silently later.
              </p>
              <p className="text-xs text-zinc-500">
                Generate a fine-grained PAT at <code>github.com → Settings → Developer settings →
                Personal access tokens → Fine-grained</code>. Permissions needed: <em>Repository
                contents: Read</em>.
              </p>
            </form>
          ) : (
            <form onSubmit={saveRawUrl} className="space-y-2" data-testid="gh-url-form">
              <Label>Full remote URL (SSH or HTTPS, may embed user:token)</Label>
              <Input
                value={remoteUrl}
                onChange={(e) => setRemoteUrl(e.target.value)}
                placeholder="git@github.com:owner/repo.git  or  https://USER:TOKEN@github.com/owner/repo.git"
                className="bg-zinc-900 border-zinc-800"
                data-testid="gh-remote-url"
              />
              <Label>Branch</Label>
              <Input
                value={remoteBranch}
                onChange={(e) => setRemoteBranch(e.target.value)}
                placeholder="main"
                className="bg-zinc-900 border-zinc-800"
                data-testid="gh-remote-branch"
              />
              <div className="flex gap-2">
                <Button type="submit" disabled={busy || !remoteUrl.trim()} className="pro-gradient text-white border-0" data-testid="gh-remote-save">
                  Save remote
                </Button>
                <Button type="button" variant="outline" onClick={() => setShowRemoteForm(false)}>Cancel</Button>
              </div>
            </form>
          )}
        </div>
      )}
      <p className="text-xs text-zinc-500">If diagnostics report "could not read Username", the backend can't auth to GitHub. Use the token form above (recommended) — the PAT is embedded into the on-disk git remote URL.</p>
    </div>
  );
}

function SEODashboardTab() {
  const [s, setS] = useState({ gsc_service_account_json: "", gsc_site_url: "" });
  const [siteUrl, setSiteUrl] = useState("");
  const [saJson, setSaJson] = useState("");
  const [savingCreds, setSavingCreds] = useState(false);
  const [credsConfigured, setCredsConfigured] = useState(false);
  const [clientEmail, setClientEmail] = useState("");
  const [smokeError, setSmokeError] = useState("");
  const [days, setDays] = useState(28);
  const [loading, setLoading] = useState(false);
  const [data, setData] = useState(null);
  const [error, setError] = useState("");

  const loadSettings = async () => {
    try {
      const res = await api.get("/admin/settings");
      const conf = res.data || {};
      setS(conf);
      setSiteUrl(conf.gsc_site_url || "");
      setCredsConfigured(!!(conf.gsc_service_account_json && conf.gsc_site_url));
    } catch (e) {
      console.error(e);
    }
  };

  const loadDashboard = async (d = days) => {
    setLoading(true);
    setError("");
    setData(null);
    try {
      const res = await api.get(`/admin/seo/dashboard?days=${d}`);
      setData(res.data);
    } catch (e) {
      setError(e?.response?.data?.detail || e.message || "Failed to load dashboard");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { loadSettings(); }, []);
  useEffect(() => {
    if (credsConfigured) loadDashboard(days);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [credsConfigured]);

  const onFileUpload = async (e) => {
    const f = e.target.files?.[0];
    if (!f) return;
    const txt = await f.text();
    setSaJson(txt);
    toast.success(`Loaded ${f.name}`);
  };

  const saveCredentials = async () => {
    if (!siteUrl.trim() || !saJson.trim()) {
      toast.error("Completează site URL și JSON-ul service account.");
      return;
    }
    setSavingCreds(true);
    setSmokeError("");
    setClientEmail("");
    try {
      const res = await api.post("/admin/seo/credentials", {
        site_url: siteUrl.trim(),
        service_account_json: saJson,
      });
      setClientEmail(res.data?.client_email || "");
      setSmokeError(res.data?.smoke_test_error || "");
      if (res.data?.smoke_test_error) {
        toast.warning("Credențiale salvate, dar smoke test eșuat — vezi mesajul de mai jos.");
      } else {
        toast.success("Credențiale Google Search Console salvate cu succes!");
      }
      setCredsConfigured(true);
      setSaJson(""); // wipe local copy after save
      await loadDashboard(days);
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Eroare la salvare");
    } finally {
      setSavingCreds(false);
    }
  };

  const deleteCredentials = async () => {
    if (!window.confirm("Sigur vrei să ștergi credențialele Google Search Console?")) return;
    try {
      await api.delete("/admin/seo/credentials");
      toast.success("Credențiale șterse.");
      setCredsConfigured(false);
      setData(null);
      setSiteUrl("");
      setClientEmail("");
      setSmokeError("");
    } catch (e) {
      toast.error("Eroare la ștergere");
    }
  };

  return (
    <div className="space-y-6">
      <Section title="🔍 Google Search Console — Credențiale">
        <p className="text-xs text-zinc-400">
          Pentru a vedea date SEO reale (clicks, impresii, CTR, poziție), trebuie să configurezi un
          <em> service account</em> Google și să-l adaugi ca utilizator în Search Console.
          <a
            href="https://console.cloud.google.com/iam-admin/serviceaccounts"
            target="_blank" rel="noreferrer"
            className="text-violet-400 hover:underline ml-1"
          >
            Deschide Google Cloud Console <ExternalLink className="inline w-3 h-3" />
          </a>
        </p>
        <ol className="text-xs text-zinc-500 list-decimal list-inside space-y-1 pl-2">
          <li>Creează un proiect Google Cloud (sau folosește unul existent) și activează <strong>Search Console API</strong>.</li>
          <li>Creează un Service Account → Keys → Add Key → JSON. Salvează fișierul.</li>
          <li>În Search Console (search.google.com/search-console) → Settings → Users and permissions → Add user. Adaugă <em>client_email</em>-ul din JSON ca <strong>Owner</strong> sau <strong>Full</strong>.</li>
          <li>Încarcă JSON-ul mai jos și introdu site URL-ul exact așa cum apare în Search Console (ex: <code>https://hentairosub.ro/</code> sau <code>sc-domain:hentairosub.ro</code>).</li>
        </ol>

        <Field label="Site URL (din Search Console)">
          <Input
            value={siteUrl}
            onChange={(e) => setSiteUrl(e.target.value)}
            placeholder="https://hentairosub.ro/  sau  sc-domain:hentairosub.ro"
            className="bg-zinc-950 border-zinc-800"
            data-testid="seo-site-url-input"
          />
        </Field>

        <div className="col-span-2">
          <Label>Service Account JSON</Label>
          <div className="flex gap-2 my-2">
            <input
              type="file"
              accept=".json,application/json"
              onChange={onFileUpload}
              className="text-xs text-zinc-400 file:mr-2 file:py-1 file:px-3 file:rounded file:border-0 file:bg-violet-600 file:text-white file:cursor-pointer"
              data-testid="seo-sa-file"
            />
            <span className="text-xs text-zinc-500 self-center">sau lipește JSON-ul direct mai jos</span>
          </div>
          <Textarea
            rows={6}
            value={saJson}
            onChange={(e) => setSaJson(e.target.value)}
            placeholder='{"type":"service_account","project_id":"...","client_email":"...","private_key":"..."}'
            className="bg-zinc-950 border-zinc-800 font-mono text-xs"
            data-testid="seo-sa-json"
          />
          <p className="text-xs text-zinc-500 mt-1">JSON-ul este stocat în baza de date (settings.gsc_service_account_json). Nu este expus public.</p>
        </div>

        <div className="flex gap-2 flex-wrap">
          <Button
            onClick={saveCredentials}
            disabled={savingCreds || !siteUrl.trim() || !saJson.trim()}
            className="pro-gradient text-white border-0"
            data-testid="seo-save-creds-btn"
          >
            {savingCreds ? "Se salvează…" : "Salvează credențialele"}
          </Button>
          {credsConfigured && (
            <Button variant="outline" onClick={deleteCredentials} data-testid="seo-delete-creds-btn">
              <Trash2 className="w-4 h-4 mr-1" /> Șterge credențialele
            </Button>
          )}
          {credsConfigured && (
            <span className="self-center text-xs flex items-center gap-1 text-emerald-400">
              <CheckCircle2 className="w-4 h-4" /> Configurate · {s.gsc_site_url}
            </span>
          )}
        </div>

        {clientEmail && (
          <p className="text-xs text-emerald-400 break-all">
            <strong>Service Account:</strong> {clientEmail}
          </p>
        )}
        {smokeError && (
          <div className="bg-amber-950/40 border border-amber-700/40 rounded p-3 text-xs text-amber-200 flex gap-2">
            <AlertTriangle className="w-4 h-4 flex-shrink-0 mt-0.5" />
            <div>
              <strong>Smoke test a eșuat:</strong> {smokeError}<br />
              <em className="text-amber-300/70">
                Verifică dacă ai adăugat email-ul service account-ului în Search Console → Settings → Users and permissions.
              </em>
            </div>
          </div>
        )}
      </Section>

      {credsConfigured && (
        <Section title="📊 Metrici Search Console">
          <div className="flex gap-2 items-center flex-wrap">
            <Label className="m-0">Perioadă:</Label>
            <Select value={String(days)} onValueChange={(v) => { const d = parseInt(v); setDays(d); loadDashboard(d); }}>
              <SelectTrigger className="w-32 bg-zinc-950 border-zinc-800" data-testid="seo-days-select"><SelectValue /></SelectTrigger>
              <SelectContent>
                <SelectItem value="7">Ultimele 7 zile</SelectItem>
                <SelectItem value="28">Ultimele 28 zile</SelectItem>
                <SelectItem value="90">Ultimele 90 zile</SelectItem>
              </SelectContent>
            </Select>
            <Button variant="outline" size="sm" onClick={() => loadDashboard(days)} disabled={loading} data-testid="seo-refresh-btn">
              <RefreshCw className={`w-4 h-4 mr-1 ${loading ? "animate-spin" : ""}`} /> Reîmprospătează
            </Button>
            {data && (
              <span className="text-xs text-zinc-500">{data.start_date} → {data.end_date}</span>
            )}
          </div>

          {error && (
            <div className="bg-red-950/40 border border-red-700/40 rounded p-3 text-xs text-red-200 flex gap-2">
              <AlertTriangle className="w-4 h-4 flex-shrink-0 mt-0.5" />
              <div>{error}</div>
            </div>
          )}

          {loading && <p className="text-sm text-zinc-400">Se încarcă datele Search Console…</p>}

          {data && (
            <>
              <div className="grid grid-cols-2 md:grid-cols-4 gap-3" data-testid="seo-totals">
                <MetricCard label="Clicks" value={data.totals.clicks.toLocaleString()} icon={TrendingUp} />
                <MetricCard label="Impresii" value={data.totals.impressions.toLocaleString()} icon={Eye} />
                <MetricCard label="CTR" value={(data.totals.ctr * 100).toFixed(2) + "%"} icon={Search} />
                <MetricCard label="Poziție medie" value={data.totals.position.toFixed(1)} icon={TrendingUp} />
              </div>

              <div className="grid md:grid-cols-2 gap-4 mt-2">
                <div>
                  <h3 className="font-heading text-base mb-2">🔗 Top pagini</h3>
                  <SeoTable
                    rows={data.top_pages}
                    columns={[
                      { key: "page", label: "URL", render: (v) => <a href={v} target="_blank" rel="noreferrer" className="text-violet-400 hover:underline break-all text-xs">{v.replace(data.site_url.replace(/\/$/, ""), "") || "/"}</a> },
                      { key: "clicks", label: "Clk", num: true },
                      { key: "impressions", label: "Imp", num: true },
                      { key: "position", label: "Poz", num: true, format: (v) => v.toFixed(1) },
                    ]}
                    empty="Nicio pagină în clasament încă."
                    testid="seo-top-pages"
                  />
                </div>

                <div>
                  <h3 className="font-heading text-base mb-2">🔎 Top căutări (queries)</h3>
                  <SeoTable
                    rows={data.top_queries}
                    columns={[
                      { key: "query", label: "Query", render: (v) => <span className="text-xs">{v}</span> },
                      { key: "clicks", label: "Clk", num: true },
                      { key: "impressions", label: "Imp", num: true },
                      { key: "position", label: "Poz", num: true, format: (v) => v.toFixed(1) },
                    ]}
                    empty="Nicio căutare înregistrată."
                    testid="seo-top-queries"
                  />
                </div>
              </div>

              <div className="mt-2">
                <div className="flex items-center justify-between mb-2 flex-wrap gap-2">
                  <h3 className="font-heading text-base">
                    🧟 Episoade neindexate <span className="text-zinc-500 text-sm">({data.zombie_count})</span>
                  </h3>
                  {data.zombies && data.zombies.length > 0 && (
                    <BulkIndexButton zombies={data.zombies} onDone={() => loadDashboard(days)} />
                  )}
                </div>
                <p className="text-xs text-zinc-500 mb-2">
                  Episoade publicate care nu au primit nicio impresie Google în perioada selectată.
                  Apasă <strong>„Request indexing"</strong> pentru a notifica Google să recrawl-eze pagina
                  (folosește Google Indexing API · cotă ~200/zi).
                </p>
                {data.zombies && data.zombies.length > 0 ? (
                  <div className="bg-zinc-950 border border-zinc-800 rounded-lg overflow-hidden" data-testid="seo-zombies">
                    <div className="max-h-96 overflow-y-auto">
                      <table className="w-full text-sm">
                        <thead className="bg-zinc-900 sticky top-0">
                          <tr>
                            <th className="text-left p-2 text-xs font-semibold text-zinc-400">Titlu</th>
                            <th className="text-left p-2 text-xs font-semibold text-zinc-400">URL</th>
                            <th className="text-left p-2 text-xs font-semibold text-zinc-400">Publicat</th>
                            <th className="text-right p-2 text-xs font-semibold text-zinc-400">Acțiune</th>
                          </tr>
                        </thead>
                        <tbody>
                          {data.zombies.map((z) => (
                            <tr key={z.video_id} className="border-t border-zinc-800 hover:bg-zinc-900/50">
                              <td className="p-2 text-xs">{z.title}</td>
                              <td className="p-2">
                                <a href={z.url} target="_blank" rel="noreferrer" className="text-violet-400 hover:underline text-xs break-all">
                                  {z.url}
                                </a>
                              </td>
                              <td className="p-2 text-xs text-zinc-500">{(z.created_at || "").slice(0, 10)}</td>
                              <td className="p-2 text-right">
                                <RequestIndexButton url={z.url} />
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  </div>
                ) : (
                  <p className="text-sm text-emerald-400">🎉 Toate episoadele au primit cel puțin o impresie!</p>
                )}
              </div>
            </>
          )}
        </Section>
      )}
    </div>
  );
}

function RequestIndexButton({ url }) {
  const [busy, setBusy] = useState(false);
  const [done, setDone] = useState(false);
  const submit = async () => {
    setBusy(true);
    try {
      const res = await api.post("/admin/seo/request-indexing", { urls: [url] });
      const r = (res.data?.results || [])[0] || {};
      if (r.ok) {
        toast.success("✓ Request indexing trimis. Google va recrawl-a URL-ul.");
        setDone(true);
      } else {
        toast.error(r.error || "Eroare la cerere");
      }
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Eroare la cerere");
    } finally {
      setBusy(false);
    }
  };
  return (
    <Button
      size="sm"
      variant={done ? "outline" : "default"}
      onClick={submit}
      disabled={busy || done}
      className={done ? "" : "pro-gradient text-white border-0"}
      data-testid={`seo-index-btn-${url}`}
    >
      {done ? <><CheckCircle2 className="w-3 h-3 mr-1" /> Trimis</> : <><Send className="w-3 h-3 mr-1" /> {busy ? "..." : "Index"}</>}
    </Button>
  );
}

function BulkIndexButton({ zombies, onDone }) {
  const [busy, setBusy] = useState(false);
  const submit = async () => {
    const urls = zombies.slice(0, 50).map((z) => z.url);
    if (!window.confirm(`Trimite cerere de indexare pentru ${urls.length} URL-uri? (cotă Google ~200/zi)`)) return;
    setBusy(true);
    try {
      const res = await api.post("/admin/seo/request-indexing", { urls });
      const { success = 0, submitted = 0 } = res.data || {};
      if (success === submitted) {
        toast.success(`✓ ${success}/${submitted} URL-uri trimise cu succes`);
      } else if (success > 0) {
        toast.warning(`${success}/${submitted} reușite. Verifică quota Google.`);
      } else {
        toast.error(`Toate cele ${submitted} au eșuat. Verifică Indexing API enabled + permisiuni service account.`);
      }
      onDone?.();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Eroare la cerere");
    } finally {
      setBusy(false);
    }
  };
  return (
    <Button
      size="sm"
      onClick={submit}
      disabled={busy || zombies.length === 0}
      className="pro-gradient text-white border-0"
      data-testid="seo-bulk-index-btn"
    >
      <Send className="w-3 h-3 mr-1" /> {busy ? "Se trimite…" : `Index toate (${Math.min(zombies.length, 50)})`}
    </Button>
  );
}

function MetricCard({ label, value, icon: Icon }) {
  return (
    <div className="bg-zinc-950 border border-zinc-800 rounded-lg p-4">
      <div className="flex items-center justify-between mb-1">
        <span className="text-xs text-zinc-400">{label}</span>
        {Icon ? <Icon className="w-4 h-4 text-violet-400" /> : null}
      </div>
      <div className="text-2xl font-heading font-bold">{value}</div>
    </div>
  );
}

function SeoTable({ rows, columns, empty, testid }) {
  if (!rows || rows.length === 0) {
    return <p className="text-xs text-zinc-500">{empty}</p>;
  }
  return (
    <div className="bg-zinc-950 border border-zinc-800 rounded-lg overflow-hidden" data-testid={testid}>
      <div className="max-h-80 overflow-y-auto">
        <table className="w-full text-sm">
          <thead className="bg-zinc-900 sticky top-0">
            <tr>
              {columns.map((c) => (
                <th key={c.key} className={`p-2 text-xs font-semibold text-zinc-400 ${c.num ? "text-right" : "text-left"}`}>{c.label}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.slice(0, 50).map((r, i) => (
              <tr key={i} className="border-t border-zinc-800 hover:bg-zinc-900/50">
                {columns.map((c) => {
                  const v = r[c.key];
                  const display = c.render ? c.render(v) : (c.format ? c.format(v) : v);
                  return <td key={c.key} className={`p-2 text-xs ${c.num ? "text-right tabular-nums" : ""}`}>{display}</td>;
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function Field({ label, children }) {
  return (
    <div className="grid grid-cols-2 gap-4 items-center">
      <Label>{label}</Label>
      <div>{children}</div>
    </div>
  );
}
