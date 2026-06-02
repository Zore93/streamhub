import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { MessageSquare, Send, Trash2, Ban, UserCircle } from "lucide-react";
import api, { BACKEND_URL, mediaUrl } from "@/lib/api";
import { useAuth } from "@/contexts/AuthContext";
import { useT } from "@/contexts/LanguageContext";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { toast } from "sonner";

const GUEST_SESSION_KEY = "chat_guest_session";
const GUEST_NAME_KEY = "chat_guest_name";

function getOrCreateGuestSession() {
  try {
    let s = localStorage.getItem(GUEST_SESSION_KEY);
    if (!s) {
      s = "guest-" + Math.random().toString(36).slice(2, 10) + "-" + Date.now().toString(36);
      localStorage.setItem(GUEST_SESSION_KEY, s);
    }
    return s;
  } catch {
    return "guest-temp-" + Date.now();
  }
}

function buildWsUrl(path) {
  const base = BACKEND_URL || window.location.origin;
  const url = new URL(path, base);
  url.protocol = url.protocol === "https:" ? "wss:" : "ws:";
  return url.toString();
}

function fmtTime(iso) {
  try {
    const d = new Date(iso);
    return d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
  } catch {
    return "";
  }
}

export default function LiveChat({ enabled = true, guestAllowed = true, maxLen = 500 }) {
  const { user } = useAuth();
  const { t } = useT();
  const [messages, setMessages] = useState([]);
  const [draft, setDraft] = useState("");
  const [guestName, setGuestName] = useState(() => {
    try { return localStorage.getItem(GUEST_NAME_KEY) || ""; } catch { return ""; }
  });
  const [showNamePrompt, setShowNamePrompt] = useState(!user && !guestName);
  const [busy, setBusy] = useState(false);
  const [wsState, setWsState] = useState("connecting");
  const scrollRef = useRef(null);
  const wsRef = useRef(null);

  const guestSession = useMemo(() => getOrCreateGuestSession(), []);

  const scrollToBottom = useCallback(() => {
    const el = scrollRef.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, []);

  // Initial load
  useEffect(() => {
    if (!enabled) return;
    api.get("/chat/messages?limit=50").then((r) => {
      setMessages(r.data);
      setTimeout(scrollToBottom, 50);
    }).catch(() => {});
  }, [enabled, scrollToBottom]);

  // WebSocket connection
  useEffect(() => {
    if (!enabled) return;
    let cancelled = false;
    let retryTimer = null;

    const connect = () => {
      const url = buildWsUrl("/api/chat/ws");
      let ws;
      try { ws = new WebSocket(url); }
      catch { return; }
      wsRef.current = ws;
      setWsState("connecting");
      ws.onopen = () => { if (!cancelled) setWsState("open"); };
      ws.onmessage = (ev) => {
        try {
          const payload = JSON.parse(ev.data);
          if (payload.type === "message") {
            setMessages((prev) => {
              if (prev.some((m) => m.id === payload.data.id)) return prev;
              const next = [...prev, payload.data];
              return next.slice(-200);
            });
            setTimeout(scrollToBottom, 50);
          } else if (payload.type === "delete") {
            setMessages((prev) => prev.filter((m) => m.id !== payload.data.id));
          }
        } catch {}
      };
      ws.onclose = () => {
        if (cancelled) return;
        setWsState("closed");
        // Auto-reconnect with simple backoff
        retryTimer = setTimeout(connect, 3000);
      };
      ws.onerror = () => { try { ws.close(); } catch {} };
    };
    connect();
    return () => {
      cancelled = true;
      if (retryTimer) clearTimeout(retryTimer);
      try { wsRef.current?.close(); } catch {}
    };
  }, [enabled, scrollToBottom]);

  const send = async (e) => {
    e?.preventDefault();
    if (!draft.trim()) return;
    if (!user && !guestName.trim()) {
      setShowNamePrompt(true);
      return;
    }
    setBusy(true);
    try {
      await api.post("/chat/send", {
        content: draft.slice(0, maxLen),
        guest_session: user ? null : guestSession,
        guest_name: user ? null : guestName.trim(),
      });
      setDraft("");
    } catch (err) {
      const detail = err.response?.data?.detail || t("chat.banned", "Failed to send");
      toast.error(detail);
    } finally {
      setBusy(false);
    }
  };

  const saveGuestName = (e) => {
    e?.preventDefault();
    const n = guestName.trim();
    if (!n) return;
    try { localStorage.setItem(GUEST_NAME_KEY, n); } catch {}
    setShowNamePrompt(false);
  };

  const deleteMsg = async (m) => {
    if (!window.confirm(t("chat.deleteMessage", "Delete message?"))) return;
    try {
      await api.delete(`/admin/chat/messages/${m.id}`);
      setMessages((prev) => prev.filter((x) => x.id !== m.id));
    } catch (err) {
      toast.error(err.response?.data?.detail || "Failed");
    }
  };

  const banFromChat = async (m) => {
    const reason = window.prompt(t("chat.banUser", "Reason? (optional)"), "spam");
    if (reason === null) return;
    try {
      if (m.user_id) {
        await api.post(`/admin/chat/ban-user/${m.user_id}`, { duration: "1week", reason });
      } else if (m.guest_session) {
        await api.post(`/admin/chat/ban-guest/${m.guest_session}`, { duration: "1week", reason });
      } else {
        return;
      }
      toast.success("Banned from chat");
    } catch (err) {
      toast.error(err.response?.data?.detail || "Failed");
    }
  };

  if (!enabled) return null;

  return (
    <div className="bg-zinc-900/70 border border-zinc-800 rounded-xl p-3 mt-4" data-testid="live-chat">
      <div className="flex items-center gap-2 mb-2 px-1">
        <MessageSquare size={14} className="text-rose-500" />
        <span className="text-xs font-bold uppercase tracking-[0.18em] text-zinc-300">{t("chat.title")}</span>
        <span className={`ml-auto h-2 w-2 rounded-full ${wsState === "open" ? "bg-emerald-400" : "bg-zinc-600 animate-pulse"}`} title={wsState} />
      </div>

      <div
        ref={scrollRef}
        className="h-56 overflow-y-auto custom-scrollbar pr-1 space-y-1.5 text-sm"
        data-testid="chat-messages"
      >
        {messages.length === 0 && (
          <div className="text-zinc-500 text-xs px-1 py-4 text-center">{t("chat.empty")}</div>
        )}
        {messages.map((m) => (
          <div key={m.id} className="group flex items-start gap-2 px-1 py-0.5 hover:bg-zinc-800/40 rounded" data-testid={`chat-msg-${m.id}`}>
            <div className="h-6 w-6 rounded-full bg-zinc-800 overflow-hidden flex-shrink-0 flex items-center justify-center">
              {m.avatar_url
                ? <img src={mediaUrl(m.avatar_url)} alt="" className="w-full h-full object-cover" />
                : <UserCircle size={14} className="text-zinc-500" />}
            </div>
            <div className="flex-1 min-w-0">
              <div className="flex items-center gap-1 leading-tight">
                <span className={`text-xs font-semibold truncate ${
                  m.role === "admin" ? "text-rose-400" : m.is_pro ? "text-amber-300" : "text-zinc-200"
                }`}>
                  {m.username}
                </span>
                {m.role === "admin" && <span className="text-[9px] bg-rose-500/20 text-rose-300 px-1 rounded">ADMIN</span>}
                {m.role === "guest" && <span className="text-[9px] bg-zinc-700 text-zinc-400 px-1 rounded">guest</span>}
                <span className="text-[10px] text-zinc-600 ml-auto">{fmtTime(m.created_at)}</span>
              </div>
              <div className="text-zinc-300 break-words">{m.content}</div>
            </div>
            {user?.role === "admin" && (
              <div className="opacity-0 group-hover:opacity-100 transition flex items-center gap-1">
                <button onClick={() => banFromChat(m)} className="text-zinc-500 hover:text-amber-400" title={t("chat.banUser")} data-testid={`chat-ban-${m.id}`}>
                  <Ban size={12} />
                </button>
                <button onClick={() => deleteMsg(m)} className="text-zinc-500 hover:text-red-400" title={t("chat.deleteMessage")} data-testid={`chat-del-${m.id}`}>
                  <Trash2 size={12} />
                </button>
              </div>
            )}
          </div>
        ))}
      </div>

      {/* Composer */}
      {!user && !guestAllowed ? (
        <div className="mt-3 text-xs text-zinc-500 text-center">{t("comments.signInToComment")}</div>
      ) : showNamePrompt ? (
        <form onSubmit={saveGuestName} className="mt-3 space-y-2" data-testid="chat-name-form">
          <Input
            value={guestName}
            onChange={(e) => setGuestName(e.target.value)}
            placeholder={t("chat.guestNamePlaceholder")}
            className="bg-zinc-950 border-zinc-800 text-sm h-8"
            maxLength={30}
            data-testid="chat-guest-name-input"
          />
          <Button type="submit" size="sm" className="w-full pro-gradient text-white border-0 h-8 text-xs" data-testid="chat-guest-name-save">
            {t("chat.startChatting")}
          </Button>
        </form>
      ) : (
        <form onSubmit={send} className="mt-3 flex gap-1.5" data-testid="chat-composer">
          <Input
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            placeholder={t("chat.placeholder")}
            className="bg-zinc-950 border-zinc-800 text-sm h-8 flex-1"
            maxLength={maxLen}
            disabled={busy}
            data-testid="chat-input"
          />
          <Button type="submit" size="sm" className="pro-gradient text-white border-0 h-8 px-2" disabled={busy || !draft.trim()} data-testid="chat-send">
            <Send size={12} />
          </Button>
        </form>
      )}
    </div>
  );
}
