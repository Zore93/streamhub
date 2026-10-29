import React, { useEffect, useRef, useState } from "react";
import { useParams, useNavigate } from "react-router-dom";
import api, { mediaUrl, BACKEND_URL } from "@/lib/api";
import { useAuth } from "@/contexts/AuthContext";
import { Layout } from "@/layout/Layout";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Copy, Send, Users, Film, Loader2, Globe, Lock } from "lucide-react";
import { toast } from "sonner";

/**
 * Watch Party room — anyone can join via /party/:code. We play a plain HTML5
 * <video> and sync `play`, `pause`, `seek` events across all members in the
 * room via WebSocket. A chat panel sits on the right.
 *
 * Layout: full-width (no right sidebar). Video is a large 2/3 column, chat is
 * a 1/3 column that stays with the video regardless of state (so the room
 * feels equally spacious before and after joining).
 */
export default function WatchParty() {
  const { code } = useParams();
  const navigate = useNavigate();
  const { user } = useAuth();

  const videoRef = useRef(null);
  const wsRef = useRef(null);
  const suppressRef = useRef(false); // true while applying a remote sync event
  const chatEndRef = useRef(null);

  const [party, setParty] = useState(null);
  const [video, setVideo] = useState(null);
  const [members, setMembers] = useState([]);
  const [chatLog, setChatLog] = useState([]);
  const [chatInput, setChatInput] = useState("");
  const [name, setName] = useState(user?.username || "");
  const [joined, setJoined] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  // 1) Load party + video
  useEffect(() => {
    let alive = true;
    api.get(`/parties/${code}`)
      .then((r) => {
        if (!alive) return;
        setParty(r.data.party);
        setVideo(r.data.video);
      })
      .catch((e) => {
        if (!alive) return;
        setError(e?.response?.data?.detail || "Camera nu există sau a expirat.");
      })
      .finally(() => alive && setLoading(false));
    return () => { alive = false; };
  }, [code]);

  // 2) Open WebSocket after the user picks a name & taps "Intră"
  const connect = () => {
    if (!name.trim()) {
      toast.error("Alege un nume");
      return;
    }
    const base = BACKEND_URL || window.location.origin;
    const url = new URL(`/api/parties/${code}/ws`, base);
    url.protocol = url.protocol === "https:" ? "wss:" : "ws:";
    let ws;
    try { ws = new WebSocket(url.toString()); } catch { return; }
    wsRef.current = ws;
    ws.onopen = () => {
      ws.send(JSON.stringify({ type: "join", name: name.trim() }));
      setJoined(true);
    };
    ws.onmessage = (ev) => {
      try {
        const m = JSON.parse(ev.data);
        if (m.type === "members") setMembers(m.list || []);
        else if (m.type === "chat") setChatLog((p) => [...p.slice(-199), m]);
        else if (m.type === "sync") applyRemoteSync(m);
        else if (m.type === "error") {
          toast.error(m.message || "Watch party error");
          try { ws.close(); } catch { /* ignore */ }
        }
      } catch { /* ignore malformed messages */ }
    };
    ws.onclose = () => setJoined(false);
    ws.onerror = () => { try { ws.close(); } catch { /* ignore */ } };
  };

  useEffect(() => () => {
    try { wsRef.current?.close(); } catch { /* ignore */ }
  }, []);

  // Scroll chat to bottom when new messages arrive
  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [chatLog.length]);

  // Apply a remote sync event WITHOUT re-broadcasting it
  const applyRemoteSync = (m) => {
    const el = videoRef.current;
    if (!el) return;
    suppressRef.current = true;
    try {
      if (typeof m.t === "number" && Math.abs((el.currentTime || 0) - m.t) > 0.6) {
        el.currentTime = m.t;
      }
      if (m.action === "play" && el.paused) el.play().catch(() => {});
      else if (m.action === "pause" && !el.paused) el.pause();
    } finally {
      setTimeout(() => { suppressRef.current = false; }, 150);
    }
  };

  // Local playback events → broadcast to room
  const emit = (action) => {
    if (suppressRef.current) return;
    const ws = wsRef.current;
    if (!ws || ws.readyState !== WebSocket.OPEN) return;
    const t = videoRef.current?.currentTime || 0;
    ws.send(JSON.stringify({ type: "sync", action, t }));
  };

  const sendChat = (e) => {
    e.preventDefault();
    const text = chatInput.trim();
    if (!text) return;
    const ws = wsRef.current;
    if (!ws || ws.readyState !== WebSocket.OPEN) return;
    ws.send(JSON.stringify({ type: "chat", text }));
    setChatInput("");
  };

  const copyLink = () => {
    const url = `${window.location.origin}/party/${code}`;
    navigator.clipboard?.writeText(url).then(
      () => toast.success("Link copiat!"),
      () => toast.error("Nu am putut copia"),
    );
  };

  // Choose a playable URL — prefer highest rendition
  const playUrl = React.useMemo(() => {
    if (!video) return null;
    const rends = video.renditions || [];
    if (!rends.length) return null;
    return mediaUrl(rends[rends.length - 1].url);
  }, [video]);

  if (loading) {
    return (
      <Layout fullWidth={true}>
        <div className="flex items-center justify-center py-20 text-zinc-400">
          <Loader2 size={28} className="animate-spin mr-2" /> Se încarcă camera…
        </div>
      </Layout>
    );
  }
  if (error) {
    return (
      <Layout fullWidth={true}>
        <div className="text-center py-16">
          <h2 className="text-2xl font-bold mb-2">Watch Party indisponibil</h2>
          <p className="text-zinc-400 mb-6">{error}</p>
          <Button onClick={() => navigate("/")}>Înapoi la pagina principală</Button>
        </div>
      </Layout>
    );
  }

  const isPublic = party?.is_public !== false;

  return (
    <Layout fullWidth={true}>
      <div className="max-w-[1800px] mx-auto" data-testid="watch-party-page">
        {/* ─── Header ────────────────────────────────────────────── */}
        <div className="flex items-center justify-between mb-5 flex-wrap gap-3">
          <div className="min-w-0 flex-1">
            <div className="text-xs uppercase tracking-wider text-fuchsia-400 flex items-center gap-2 mb-1">
              <Users size={14} />
              <span>Watch Party · {members.length} membri</span>
              {isPublic ? (
                <span className="inline-flex items-center gap-1 text-emerald-300 bg-emerald-500/10 border border-emerald-500/30 rounded-full px-2 py-0.5 text-[10px]">
                  <Globe size={10} /> PUBLIC
                </span>
              ) : (
                <span className="inline-flex items-center gap-1 text-zinc-300 bg-zinc-800 border border-zinc-700 rounded-full px-2 py-0.5 text-[10px]">
                  <Lock size={10} /> PRIVAT
                </span>
              )}
            </div>
            <h1 className="text-2xl sm:text-3xl font-bold line-clamp-1" data-testid="party-video-title">
              {video?.title}
            </h1>
          </div>
          <div className="flex items-center gap-2">
            <code className="bg-zinc-900 border border-zinc-800 px-3 py-2 rounded font-mono text-sm tracking-wider" data-testid="party-code">{code}</code>
            <Button variant="outline" size="sm" className="border-zinc-700" onClick={copyLink} data-testid="party-copy-link">
              <Copy size={14} className="mr-1.5" /> Copiază link
            </Button>
          </div>
        </div>

        {/* ─── Video + Chat grid ─────────────────────────────────── */}
        <div className="grid grid-cols-1 lg:grid-cols-[minmax(0,1fr)_380px] xl:grid-cols-[minmax(0,1fr)_420px] gap-5">
          {/* ─── Video column ─────────────────────────────────── */}
          <div className="aspect-video bg-black rounded-xl overflow-hidden relative border border-zinc-800 shadow-2xl shadow-fuchsia-950/20">
            {!joined ? (
              <div className="absolute inset-0 flex flex-col items-center justify-center text-center px-6 bg-gradient-to-br from-black via-fuchsia-950/30 to-black">
                <Film size={56} className="text-fuchsia-400 mb-4" />
                <h3 className="text-3xl font-bold mb-2">Intră în cameră</h3>
                <p className="text-zinc-300 mb-6 text-base max-w-md">
                  Alege un nume afișat celorlalți din watch party.
                </p>
                <div className="flex gap-2 w-full max-w-md">
                  <Input
                    value={name}
                    onChange={(e) => setName(e.target.value)}
                    placeholder="Numele tău"
                    className="bg-zinc-900 border-zinc-700 h-12 text-base"
                    data-testid="party-name"
                    onKeyDown={(e) => e.key === "Enter" && connect()}
                  />
                  <Button
                    onClick={connect}
                    className="pro-gradient text-white border-0 h-12 px-6 text-base"
                    data-testid="party-join"
                  >
                    Intră
                  </Button>
                </div>
              </div>
            ) : playUrl ? (
              <video
                ref={videoRef}
                src={playUrl}
                className="w-full h-full object-contain bg-black"
                controls
                onPlay={() => emit("play")}
                onPause={() => emit("pause")}
                onSeeked={() => emit("seek")}
                data-testid="party-video"
              />
            ) : (
              <div className="absolute inset-0 flex items-center justify-center text-zinc-500">
                Videoclipul nu este disponibil pentru redare publică.
              </div>
            )}
          </div>

          {/* ─── Chat column ──────────────────────────────────── */}
          <aside
            className="bg-zinc-900 border border-zinc-800 rounded-xl flex flex-col h-[560px] lg:h-auto lg:max-h-[calc(100vh-180px)]"
            data-testid="party-chat"
          >
            <div className="px-4 py-3 border-b border-zinc-800 text-sm font-semibold flex items-center justify-between">
              <span>Chat</span>
              <span className="text-xs text-zinc-500 font-normal">{chatLog.length} mesaje</span>
            </div>
            <div className="px-3 py-2 border-b border-zinc-800 text-xs text-zinc-400 flex flex-wrap gap-1 min-h-[36px]">
              {members.length === 0 ? (
                <span className="italic">Niciun membru conectat</span>
              ) : members.map((n, i) => (
                <span key={i} className="bg-zinc-800 px-2 py-0.5 rounded-full">{n}</span>
              ))}
            </div>
            <div className="flex-1 overflow-y-auto px-3 py-3 space-y-2 text-sm">
              {chatLog.map((m, i) => (
                <div key={i} className="flex gap-2 items-baseline">
                  <span className="text-fuchsia-400 font-semibold">{m.name}</span>
                  <span className="text-zinc-200 break-words">{m.text}</span>
                </div>
              ))}
              {chatLog.length === 0 && (
                <div className="text-zinc-500 italic text-xs text-center py-10">
                  Scrie primul mesaj din watch party…
                </div>
              )}
              <div ref={chatEndRef} />
            </div>
            {joined && (
              <form onSubmit={sendChat} className="px-3 py-2 border-t border-zinc-800 flex gap-2">
                <Input
                  value={chatInput}
                  onChange={(e) => setChatInput(e.target.value)}
                  placeholder="Scrie un mesaj…"
                  className="bg-zinc-950 border-zinc-800 h-10"
                  data-testid="party-chat-input"
                  maxLength={500}
                />
                <Button size="sm" type="submit" className="pro-gradient text-white border-0" data-testid="party-chat-send">
                  <Send size={14} />
                </Button>
              </form>
            )}
          </aside>
        </div>
      </div>
    </Layout>
  );
}
