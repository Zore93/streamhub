import React, { useEffect, useState } from "react";
import api from "@/lib/api";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Switch } from "@/components/ui/switch";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { toast } from "sonner";
import { useAuth } from "@/contexts/AuthContext";
import { Trash2, Plus, RefreshCw, Eye, Heart, MessageCircle, Users, Video as VideoIcon, Crown } from "lucide-react";

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
          <TabsTrigger value="settings" data-testid="tab-settings">Settings</TabsTrigger>
        </TabsList>
        <TabsContent value="dashboard"><Dashboard /></TabsContent>
        <TabsContent value="videos"><VideosTab /></TabsContent>
        <TabsContent value="users"><UsersTab /></TabsContent>
        <TabsContent value="categories"><CategoriesTab /></TabsContent>
        <TabsContent value="packages"><PackagesTab /></TabsContent>
        <TabsContent value="announcements"><AnnouncementsTab /></TabsContent>
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
  const [vids, setVids] = useState([]);
  const load = () => api.get("/admin/videos").then((r) => setVids(r.data));
  useEffect(() => { load(); }, []);
  const del = async (id) => {
    if (!window.confirm("Delete?")) return;
    await api.delete(`/videos/${id}`);
    load();
  };
  return (
    <div className="mt-6 space-y-2" data-testid="admin-videos">
      {vids.map((v) => (
        <div key={v.id} className="bg-zinc-900 border border-zinc-800 rounded-lg p-3 flex items-center justify-between gap-3">
          <div className="flex-1 min-w-0">
            <div className="font-semibold truncate">{v.title}</div>
            <div className="text-xs text-zinc-500">@{v.uploader_username} · {v.status} · {v.views} views · {v.access_tier}</div>
          </div>
          <Button size="sm" variant="destructive" onClick={() => del(v.id)} data-testid={`del-vid-${v.id}`}><Trash2 size={14} /></Button>
        </div>
      ))}
      {vids.length === 0 && <p className="text-zinc-500">No videos.</p>}
    </div>
  );
}

function UsersTab() {
  const [users, setUsers] = useState([]);
  const [banDur, setBanDur] = useState({});
  const [banDays, setBanDays] = useState({});
  const load = () => api.get("/admin/users").then((r) => setUsers(r.data));
  useEffect(() => { load(); }, []);

  const ban = async (u) => {
    const duration = banDur[u.id] || "1day";
    const body = { duration, custom_days: parseInt(banDays[u.id] || 1) };
    await api.post(`/admin/users/${u.id}/ban`, body);
    toast.success("Banned");
    load();
  };
  const unban = async (u) => { await api.post(`/admin/users/${u.id}/unban`); load(); };
  const setRole = async (u, role) => { await api.post(`/admin/users/${u.id}/role`, { role }); load(); };

  return (
    <div className="mt-6 space-y-2" data-testid="admin-users">
      {users.map((u) => (
        <div key={u.id} className="bg-zinc-900 border border-zinc-800 rounded-lg p-3 flex items-center justify-between gap-3 flex-wrap">
          <div className="flex-1 min-w-0">
            <div className="font-semibold truncate">@{u.username} <span className="text-xs text-zinc-500">{u.email}</span></div>
            <div className="text-xs text-zinc-500">role: {u.role} · pro: {String(!!u.is_pro)} · banned: {u.banned_until ? u.banned_until.slice(0, 16) : "no"}</div>
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
        </div>
      ))}
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
  const githubUpdate = async () => {
    try { const { data } = await api.post("/admin/github/update"); toast.success("Pull executed"); console.log(data); }
    catch (e) { toast.error(e.response?.data?.detail || "Failed"); }
  };
  return (
    <div className="mt-6 space-y-6 max-w-3xl" data-testid="admin-settings">
      <Section title="FFmpeg & Uploads">
        <Field label="Concurrent transcodes"><Input type="number" value={s.ffmpeg_concurrency} onChange={(e) => upd("ffmpeg_concurrency", parseInt(e.target.value) || 1)} className="bg-zinc-950 border-zinc-800" /></Field>
        <Field label="Max upload size (MB)"><Input type="number" value={s.max_upload_size_mb} onChange={(e) => upd("max_upload_size_mb", parseInt(e.target.value) || 100)} className="bg-zinc-950 border-zinc-800" /></Field>
        <Field label="Allow user uploads"><Switch checked={s.allow_user_uploads} onCheckedChange={(v) => upd("allow_user_uploads", v)} /></Field>
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
        <Field label="SMTP host"><Input value={s.smtp_host} onChange={(e) => upd("smtp_host", e.target.value)} className="bg-zinc-950 border-zinc-800" /></Field>
        <Field label="SMTP port"><Input type="number" value={s.smtp_port} onChange={(e) => upd("smtp_port", parseInt(e.target.value) || 587)} className="bg-zinc-950 border-zinc-800" /></Field>
        <Field label="SMTP user"><Input value={s.smtp_user} onChange={(e) => upd("smtp_user", e.target.value)} className="bg-zinc-950 border-zinc-800" /></Field>
        <Field label="SMTP password"><Input type="password" value={s.smtp_password} onChange={(e) => upd("smtp_password", e.target.value)} className="bg-zinc-950 border-zinc-800" /></Field>
        <Field label="From address"><Input value={s.smtp_from} onChange={(e) => upd("smtp_from", e.target.value)} className="bg-zinc-950 border-zinc-800" /></Field>
        <Field label="Use TLS"><Switch checked={s.smtp_use_tls} onCheckedChange={(v) => upd("smtp_use_tls", v)} /></Field>
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
        <p className="text-xs text-zinc-500 col-span-2">When enabled, signed URLs are issued by CloudFront instead of S3 presign. Pair with a CloudFront distribution whose origin is your Wasabi bucket (with bucket public access restricted via OAI / signed-URL behavior). Also set <code>wasabi_public_base_url</code> to your CloudFront URL so newly uploaded assets serve through CloudFront.</p>
      </Section>
      <Section title="Contact form">
        <Field label="Contact email"><Input type="email" value={s.contact_email || ""} onChange={(e) => upd("contact_email", e.target.value)} placeholder="contact@yourdomain.com" className="bg-zinc-950 border-zinc-800" data-testid="contact-email-setting" /></Field>
        <p className="text-xs text-zinc-500">Messages from /contact are sent to this address (requires SMTP to be enabled).</p>
      </Section>
      <Section title="GitHub auto-update">
        <Field label="Repo URL"><Input value={s.github_repo} onChange={(e) => upd("github_repo", e.target.value)} className="bg-zinc-950 border-zinc-800" placeholder="https://github.com/you/repo.git" /></Field>
        <Field label="Branch"><Input value={s.github_branch} onChange={(e) => upd("github_branch", e.target.value)} className="bg-zinc-950 border-zinc-800" /></Field>
        <Field label="Token"><Input type="password" value={s.github_token} onChange={(e) => upd("github_token", e.target.value)} className="bg-zinc-950 border-zinc-800" /></Field>
        <Button variant="outline" onClick={githubUpdate} data-testid="gh-update"><RefreshCw size={14} className="mr-2" /> Pull updates</Button>
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
function Field({ label, children }) {
  return (
    <div className="grid grid-cols-2 gap-4 items-center">
      <Label>{label}</Label>
      <div>{children}</div>
    </div>
  );
}
