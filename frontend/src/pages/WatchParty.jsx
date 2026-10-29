import React, { useEffect, useRef, useState } from "react";
import { useParams, useNavigate } from "react-router-dom";
import api, { mediaUrl, BACKEND_URL } from "@/lib/api";
import { useAuth } from "@/contexts/AuthContext";
import { Layout } from "@/layout/Layout";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Copy, Send, Users, Film, Loader2, Globe, Lock, Crown, Play } from "lucide-react";
import { toast } from "sonner";

/**
 * Watch Party room — anyone can join via /party/:code. The video playback is
 * driven ONLY by the room's host (the first member to connect). Everyone
 * else is a viewer who auto-syncs to the host's playback timestamp when they
 * join and every time the host plays / pauses / seeks.
 *
 * Logged-in users auto-join using their username — no name picker shown.
 * Guests still get a name input.
 */
export default function WatchParty() {
  const { code } = useParams();
  const navigate = useNavigate();
  const { user } = useAuth();

  const videoRef = useRef(null);
  const wsRef = useRef(null);
  const suppressRef = useRef(false);         // true while applying a remote sync
  const chatEndRef = useRef(null);
  const pendingSyncRef = useRef(null);       // sync received before <video> mounted

  const [party, setParty] = useState(null);
  const [video, setVideo] = useState(null);
  const [members, setMembers] = useState([]); // [{name, is_host}]
  const [chatLog, setChatLog] = useState([]);
  const [chatInput, setChatInput] = useState("");
  const [guestName, setGuestName] = useState("");
  const [joined, setJoined] = useState(false);
  const [isHost, setIsHost] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [needsStartTap, setNeedsStartTap] = useState(false); // for autoplay-block

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

  // 2) Open the websocket. Logged-in users auto-connect once the party loads.
  const connect = (nameOverride) => {
    const effectiveName = (nameOverride ?? (user?.username || guestName)).trim();
    if (!effectiveName) {
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
      ws.send(JSON.stringify({ type: "join", name: effectiveName }));
      setJoined(true);
    };
    ws.onmessage = (ev) => {
      try {
        const m = JSON.parse(ev.data);
        if (m.type === "members") setMembers(m.list || []);
        else if (m.type === "chat") setChatLog((p) => [...p.slice(-199), m]);
        else if (m.type === "you") setIsHost(!!m.is_host);
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

  // Auto-join flow for logged-in users: once we have the party loaded AND
  // the user is logged in, kick off the WS without the name picker.
  useEffect(() => {
    if (!party || joined || !user?.username) return;
    connect(user.username);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [party, user?.username]);

  useEffect(() => () => {
    try { wsRef.current?.close(); } catch { /* ignore */ }
  }, []);

  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [chatLog.length]);

  // Apply a remote sync event WITHOUT re-broadcasting it. If the <video>
  // isn't mounted yet (user hasn't yet started), stash the state and apply
  // once it does mount.
  const applyRemoteSync = (m) => {
    const el = videoRef.current;
    if (!el) {
      pendingSyncRef.current = m;
      return;
    }
    suppressRef.current = true;
    try {
      if (typeof m.t === "number" && Math.abs((el.currentTime || 0) - m.t) > 0.6) {
        el.currentTime = m.t;
      }
      if (m.action === "play" && el.paused) {
        el.play().catch(() => {
          // Browser blocked autoplay — show the "tap to start" overlay.
          setNeedsStartTap(true);
        });
      } else if (m.action === "pause" && !el.paused) {
        el.pause();
      }
    } finally {
      setTimeout(() => { suppressRef.current = false; }, 150);
    }
  };

  // When the <video> mounts, apply any sync we stashed earlier.
  const onVideoRefSet = (el) => {
    videoRef.current = el;
    if (el && pendingSyncRef.current) {
      const pending = pendingSyncRef.current;
      pendingSyncRef.current = null;
      // Give the browser a tick to attach the src.
      setTimeout(() => applyRemoteSync(pending), 50);
    }
  };

  // Local playback events → broadcast to room (host only). Non-hosts: the
  // native controls are hidden, so these handlers mostly fire during the
  // host's actions.
  const emit = (action) => {
    if (!isHost) return;
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

  // "Tap to start" handler — satisfies browser gesture requirement for autoplay.
  const handleStartTap = () => {
    const el = videoRef.current;
    if (!el) return;
    el.play().then(
      () => setNeedsStartTap(false),
      () => toast.error("Nu am putut porni videoclipul"),
    );
  };

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
          <h2 className="text-2xl font-bold mb-2">Camera indisponibilă</h2>
          <p className="text-zinc-400 mb-6">{error}</p>
          <Button onClick={() => navigate("/")}>Înapoi la pagina principală</Button>
        </div>
      </Layout>
    );
  }

  const isPublic = party?.is_public !== false;
  // We hide the "Intră în cameră" screen entirely for logged-in users since
  // auto-join handles it. Guests still see it.
  const showGuestJoinScreen = !joined && !user?.username;

  return (
    <Layout fullWidth={true}>
      <div className="max-w-[1800px] mx-auto" data-testid="watch-party-page">
        {/* ─── Header ────────────────────────────────────────────── */}
        <div className="flex items-center justify-between mb-5 flex-wrap gap-3">
          <div className="min-w-0 flex-1">
            <div className="text-xs uppercase tracking-wider text-fuchsia-400 flex items-center gap-2 mb-1">
              <Users size={14} />
              <span>Vizionare în grup · {members.length} membri</span>
              {isPublic ? (
                <span className="inline-flex items-center gap-1 text-emerald-300 bg-emerald-500/10 border border-emerald-500/30 rounded-full px-2 py-0.5 text-[10px]">
                  <Globe size={10} /> PUBLIC
                </span>
              ) : (
                <span className="inline-flex items-center gap-1 text-zinc-300 bg-zinc-800 border border-zinc-700 rounded-full px-2 py-0.5 text-[10px]">
                  <Lock size={10} /> PRIVAT
                </span>
              )}
              {isHost && (
                <span className="inline-flex items-center gap-1 text-amber-200 bg-amber-500/15 border border-amber-500/40 rounded-full px-2 py-0.5 text-[10px]" data-testid="party-host-badge">
                  <Crown size={10} /> TU EȘTI GAZDA
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
            {showGuestJoinScreen ? (
              <div className="absolute inset-0 flex flex-col items-center justify-center text-center px-6 bg-gradient-to-br from-black via-fuchsia-950/30 to-black">
                <Film size={56} className="text-fuchsia-400 mb-4" />
                <h3 className="text-3xl font-bold mb-2">Intră în cameră</h3>
                <p className="text-zinc-300 mb-6 text-base max-w-md">
                  Alege un nume afișat celorlalți.
                </p>
                <div className="flex gap-2 w-full max-w-md">
                  <Input
                    value={guestName}
                    onChange={(e) => setGuestName(e.target.value)}
                    placeholder="Numele tău"
                    className="bg-zinc-900 border-zinc-700 h-12 text-base"
                    data-testid="party-name"
                    onKeyDown={(e) => e.key === "Enter" && connect()}
                  />
                  <Button
                    onClick={() => connect()}
                    className="pro-gradient text-white border-0 h-12 px-6 text-base"
                    data-testid="party-join"
                  >
                    Intră
                  </Button>
                </div>
              </div>
            ) : !joined ? (
              <div className="absolute inset-0 flex flex-col items-center justify-center text-center text-zinc-400">
                <Loader2 size={32} className="animate-spin mb-3" />
                Se conectează la cameră…
              </div>
            ) : playUrl ? (
              <>
                <video
                  ref={onVideoRefSet}
                  src={playUrl}
                  className="w-full h-full object-contain bg-black"
                  controls={isHost}
                  controlsList="nodownload"
                  disablePictureInPicture={!isHost}
                  onPlay={() => emit("play")}
                  onPause={() => emit("pause")}
                  onSeeked={() => emit("seek")}
                  onContextMenu={(e) => !isHost && e.preventDefault()}
                  data-testid="party-video"
                />
                {!isHost && (
                  <div className="absolute top-3 left-3 bg-black/70 backdrop-blur-sm text-zinc-200 text-[11px] font-semibold px-2.5 py-1 rounded border border-zinc-700 pointer-events-none" data-testid="party-viewer-badge">
                    Sincronizat cu gazda
                  </div>
                )}
                {needsStartTap && (
                  <button
                    type="button"
                    onClick={handleStartTap}
                    className="absolute inset-0 flex flex-col items-center justify-center bg-black/85 backdrop-blur-sm text-white text-center p-6 group"
                    data-testid="party-start-tap"
                  >
                    <div className="w-20 h-20 rounded-full bg-rose-500 flex items-center justify-center mb-4 group-hover:scale-110 transition-transform shadow-xl shadow-rose-500/40">
                      <Play size={36} fill="currentColor" />
                    </div>
                    <div className="text-xl font-bold mb-1">Apasă pentru a vedea</div>
                    <div className="text-sm text-zinc-300">
                      Browser-ul necesită o acțiune pentru a porni sunetul.
                    </div>
                  </button>
                )}
              </>
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
                <span className="italic">Nimeni încă în cameră.</span>
              ) : (
                members.map((m, i) => (
                  <span
                    key={`${m.name}-${i}`}
                    className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full ${
                      m.is_host
                        ? "bg-amber-500/15 text-amber-200 border border-amber-500/30"
                        : "bg-zinc-800 text-zinc-300"
                    }`}
                  >
                    {m.is_host && <Crown size={9} />} {m.name}
                  </span>
                ))
              )}
            </div>
            <div className="flex-1 overflow-y-auto px-3 py-2 space-y-1.5" data-testid="party-chat-log">
              {chatLog.length === 0 && joined && (
                <div className="text-xs text-zinc-500 italic text-center py-8">
                  Niciun mesaj încă. Zi "salut" ✌️
                </div>
              )}
              {chatLog.map((m, i) => (
                <div key={i} className="text-sm leading-snug">
                  <span className="font-semibold text-fuchsia-300 mr-1">{m.name}:</span>
                  <span className="text-zinc-200">{m.text}</span>
                </div>
              ))}
              <div ref={chatEndRef} />
            </div>
            {joined && (
              <form
                onSubmit={sendChat}
                className="p-2 border-t border-zinc-800 flex gap-1.5"
                data-testid="party-chat-form"
              >
                <Input
                  value={chatInput}
                  onChange={(e) => setChatInput(e.target.value)}
                  placeholder="Mesaj…"
                  maxLength={500}
                  className="bg-zinc-950 border-zinc-800 h-9 text-sm"
                  data-testid="party-chat-input"
                />
                <Button type="submit" size="sm" className="pro-gradient text-white border-0 px-3">
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
