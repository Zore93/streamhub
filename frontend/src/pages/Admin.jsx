import React, { useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import api, { mediaUrl } from "@/lib/api";
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
          <TabsTrigger value="packages" data-testid="tab-packages">Packages</TabsTrigger>
          <TabsTrigger value="announcements" data-testid="tab-announcements">Announcements</TabsTrigger>
          <TabsTrigger value="chat" data-testid="tab-chat">Live Chat</TabsTrigger>
          <TabsTrigger value="settings" data-testid="tab-settings">Settings</TabsTrigger>
        </TabsList>
        <TabsContent value="dashboard"><Dashboard /></TabsContent>
        <TabsContent value="videos"><VideosTab /></TabsContent>
        <TabsContent value="users"><UsersTab /></TabsContent>
        <TabsContent value="categories"><CategoriesTab /></TabsContent>
        <TabsContent value="packages"><PackagesTab /></TabsContent>
        <TabsContent value="announcements"><AnnouncementsTab /></TabsContent>
        <TabsContent value="chat"><ChatModerationTab /></TabsContent>
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
  const PAGE = 50;

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
  const lastKey = useRef("");
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

      {items.map((v) => (
        <div key={v.id} className="bg-zinc-900 border border-zinc-800 rounded-lg p-3 flex items-center justify-between gap-3 flex-wrap">
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
            className="border-zinc-700 hover:bg-zinc-800"
            data-testid="admin-videos-load-more"
          >
            {loading ? "Loading…" : `Load more (${total - items.length} remaining)`}
          </Button>
        </div>
      )}
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

  const lastKey = useRef("");
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
        <div key={u.id} className="bg-zinc-900 border border-zinc-800 rounded-lg p-3 flex items-center justify-between gap-3 flex-wrap">
          <div className="flex-1 min-w-0">
            <div className="font-semibold truncate">@{u.username} <span className="text-xs text-zinc-500">{u.email}</span></div>
            <div className="text-xs text-zinc-500">role: {u.role} · pro: {String(!!u.is_pro)} · banned: {u.banned_until ? u.banned_until.slice(0, 16) : "no"} · chat-ban: {u.chat_banned_until ? u.chat_banned_until.slice(0, 16) : "no"}</div>
          </div>
          <Select value={banDur[u.id] || "1day"} onValueChange={(v) => setBanDur({ ...banDur, [u.id]: v })}>
            <SelectTrigger className="w-32 bg-zinc-950 border-zinc-800"><SelectValue /></SelectTrigger>
            <SelectContent>{BAN_OPTIONS.map((o) => <SelectItem key={o.v} value={o.v}>{o.l}</SelectItem>)}</SelectContent>
          </Select>
          {banDur[u.id] === "custom" && (
            <Input type="number" placeholder="Days" value={banDays[u.id] || ""} onChange={(e) => setBanDays({ ...banDays, [u.id]: e.target.value })} className="w-20 bg-zinc-950 border-zinc-800" />
          )}
          <Button size="sm" variant="destructive" onClick={() => ban(u)} data-testid={`ban-${u.id}`}>Ban</Button>
          <Button size="sm" variant="outline" onClick={() => unban(u)}>Unban</Button>
          <Button size="sm" variant="outline" onClick={() => setRole(u, u.role === "admin" ? "user" : "admin")}>{u.role === "admin" ? "Demote" : "Promote"}</Button>
          <div className="flex items-center gap-1 ml-2">
            <Select value={proDur[u.id] || "1month"} onValueChange={(v) => setProDur({ ...proDur, [u.id]: v })}>
              <SelectTrigger className="w-32 bg-zinc-950 border-zinc-800"><SelectValue /></SelectTrigger>
              <SelectContent>{BAN_OPTIONS.map((o) => <SelectItem key={o.v} value={o.v}>{o.l}</SelectItem>)}</SelectContent>
            </Select>
            {proDur[u.id] === "custom" && (
              <Input type="number" placeholder="Days" value={proDays[u.id] || ""} onChange={(e) => setProDays({ ...proDays, [u.id]: e.target.value })} className="w-20 bg-zinc-950 border-zinc-800" />
            )}
            <Button size="sm" className="pro-gradient text-white border-0" onClick={() => grantPro(u)} data-testid={`grant-pro-${u.id}`}>Grant PRO</Button>
            {u.is_pro && <Button size="sm" variant="outline" onClick={() => revokePro(u)} data-testid={`revoke-pro-${u.id}`}>Revoke</Button>}
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
  const load = () => api.get("/categories").then((r) => setCats(r.data));
  useEffect(() => { load(); }, []);
  const create = async () => {
    if (!name.trim()) return;
    await api.post("/categories", { name });
    setName(""); load();
  };
  const del = async (id) => { await api.delete(`/categories/${id}`); load(); };
  return (
    <div className="mt-6" data-testid="admin-categories">
      <div className="flex gap-2 mb-4">
        <Input value={name} onChange={(e) => setName(e.target.value)} placeholder="New category" className="bg-zinc-900 border-zinc-800" data-testid="new-cat-name" />
        <Button onClick={create} data-testid="add-cat-btn"><Plus size={14} /></Button>
      </div>
      <div className="space-y-2">
        {cats.map((c) => (
          <div key={c.id} className="bg-zinc-900 border border-zinc-800 rounded-md p-3 flex justify-between items-center">
            <span>{c.name}</span>
            <Button size="sm" variant="destructive" onClick={() => del(c.id)}><Trash2 size={14} /></Button>
          </div>
        ))}
      </div>
    </div>
  );
}

function PackagesTab() {
  const [pks, setPks] = useState([]);
  const [form, setForm] = useState({ name: "", description: "", color: "#f43f5e", price: 9.99, currency: "usd", duration_days: 30, active: true, sort_order: 0 });
  const load = () => api.get("/packages/all").then((r) => setPks(r.data));
  useEffect(() => { load(); }, []);
  const create = async () => {
    await api.post("/packages", { ...form, price: parseFloat(form.price), duration_days: parseInt(form.duration_days) });
    load();
  };
  const upd = async (id, patch) => { await api.patch(`/packages/${id}`, patch); load(); };
  const del = async (id) => { await api.delete(`/packages/${id}`); load(); };
  return (
    <div className="mt-6 space-y-6" data-testid="admin-packages">
      <div className="bg-zinc-900 border border-zinc-800 rounded-xl p-4">
        <div className="font-semibold mb-3">New Package ({pks.length}/10)</div>
        <div className="grid grid-cols-2 gap-3">
          <Input placeholder="Name" value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} className="bg-zinc-950 border-zinc-800" />
          <Input type="color" value={form.color} onChange={(e) => setForm({ ...form, color: e.target.value })} className="bg-zinc-950 border-zinc-800 h-10" />
          <Input type="number" step="0.01" placeholder="Price" value={form.price} onChange={(e) => setForm({ ...form, price: e.target.value })} className="bg-zinc-950 border-zinc-800" />
          <Input type="number" placeholder="Duration (days)" value={form.duration_days} onChange={(e) => setForm({ ...form, duration_days: e.target.value })} className="bg-zinc-950 border-zinc-800" />
          <Textarea placeholder="Description" value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })} className="bg-zinc-950 border-zinc-800 col-span-2" />
        </div>
        <Button onClick={create} className="mt-3 pro-gradient text-white border-0" disabled={pks.length >= 10} data-testid="new-pkg-btn">Add</Button>
      </div>
      {pks.map((p) => (
        <div key={p.id} className="bg-zinc-900 border border-zinc-800 rounded-xl p-4 flex justify-between items-center">
          <div>
            <div className="font-semibold" style={{ color: p.color }}>{p.name} — ${p.price}</div>
            <div className="text-xs text-zinc-500">{p.duration_days} days · active: {String(p.active)}</div>
          </div>
          <div className="flex gap-2 items-center">
            <Switch checked={p.active} onCheckedChange={(v) => upd(p.id, { active: v })} />
            <Button size="sm" variant="destructive" onClick={() => del(p.id)}><Trash2 size={14} /></Button>
          </div>
        </div>
      ))}
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
  useEffect(() => { api.get("/admin/settings").then((r) => setS(r.data)); }, []);
  if (!s) return <div className="text-zinc-500">Loading...</div>;
  const upd = (k, v) => setS({ ...s, [k]: v });
  const save = async () => {
    const { data } = await api.patch("/admin/settings", s);
    setS(data); toast.success("Settings saved");
  };
  const toggleRes = (r) => {
    const cur = s.enabled_resolutions || [];
    upd("enabled_resolutions", cur.includes(r) ? cur.filter((x) => x !== r) : [...cur, r]);
  };
  return (
    <div className="mt-6 space-y-6 max-w-3xl" data-testid="admin-settings">
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
      <Section title="Legacy migration">
        <Field label="Mark migrated legacy videos as PRO-only">
          <Switch checked={!!s.legacy_videos_pro_only} onCheckedChange={(v) => upd("legacy_videos_pro_only", v)} data-testid="legacy-pro-toggle" />
        </Field>
        <p className="text-xs text-zinc-500">When importing legacy databases via the migration tool, the imported videos default to PRO-only access.</p>
        <LegacyShortsControls />
      </Section>
      <Section title="FFmpeg & Uploads">
        <Field label="Concurrent transcodes"><Input type="number" value={s.ffmpeg_concurrency} onChange={(e) => upd("ffmpeg_concurrency", parseInt(e.target.value) || 1)} className="bg-zinc-950 border-zinc-800" /></Field>
        <Field label="Max upload size (MB)"><Input type="number" value={s.max_upload_size_mb} onChange={(e) => upd("max_upload_size_mb", parseInt(e.target.value) || 100)} className="bg-zinc-950 border-zinc-800" /></Field>
        <Field label="Allow user uploads"><Switch checked={s.allow_user_uploads} onCheckedChange={(v) => upd("allow_user_uploads", v)} /></Field>
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
      <Section title="Site / SEO">
        <Field label="Site title"><Input value={s.site_title || ""} onChange={(e) => upd("site_title", e.target.value)} className="bg-zinc-950 border-zinc-800" data-testid="site-title-input" /></Field>
        <Field label="Description"><Input value={s.site_description || ""} onChange={(e) => upd("site_description", e.target.value)} className="bg-zinc-950 border-zinc-800" /></Field>
        <Field label="Favicon URL"><Input value={s.site_favicon_url || ""} onChange={(e) => upd("site_favicon_url", e.target.value)} className="bg-zinc-950 border-zinc-800" placeholder="https://.../favicon.ico" /></Field>
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
      <Button onClick={save} className="pro-gradient text-white border-0" data-testid="save-settings">Save All Settings</Button>
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

function Field({ label, children }) {
  return (
    <div className="grid grid-cols-2 gap-4 items-center">
      <Label>{label}</Label>
      <div>{children}</div>
    </div>
  );
}
