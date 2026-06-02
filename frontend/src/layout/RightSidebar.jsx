import React, { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { Crown, LogIn, UserPlus, LogOut, User as UserIcon } from "lucide-react";
import { useAuth } from "@/contexts/AuthContext";
import api, { mediaUrl } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { useT } from "@/contexts/LanguageContext";
import LiveChat from "./LiveChat";

export default function RightSidebar({ recommendations = null }) {
  const { user, logout } = useAuth();
  const { t, siteCfg } = useT();
  const [pkgs, setPkgs] = useState([]);

  useEffect(() => {
    api.get("/packages").then((r) => setPkgs(r.data)).catch(() => {});
  }, []);

  // Live chat is only shown on the home/listing pages (not on watch page where
  // we surface recommendations).  Admin can disable chat globally in settings.
  const chatEnabled = !recommendations && (siteCfg?.live_chat_enabled ?? true);

  return (
    <aside
      data-testid="right-sidebar"
      className="hidden lg:block fixed right-0 top-0 h-screen w-[280px] xl:w-[300px] border-l border-zinc-800 bg-zinc-950/90 backdrop-blur-xl p-5 overflow-y-auto custom-scrollbar z-30"
    >
      {/* User block */}
      {user ? (
        <div data-testid="user-block" className="bg-zinc-900/70 border border-zinc-800 rounded-xl p-4 mb-4">
          <div className="flex items-center gap-3">
            <div className="h-12 w-12 rounded-full bg-zinc-800 overflow-hidden flex items-center justify-center">
              {user.avatar_url ? (
                <img src={mediaUrl(user.avatar_url)} alt="" className="h-full w-full object-cover" />
              ) : (
                <UserIcon size={20} className="text-zinc-500" />
              )}
            </div>
            <div className="flex-1 min-w-0">
              <div className="font-semibold truncate text-zinc-50">{user.username}</div>
              <div className="text-xs text-zinc-500 truncate">{user.email}</div>
            </div>
          </div>
          {user.is_pro && (
            <div className="mt-3 px-2 py-1 rounded-md pro-gradient text-xs font-semibold text-white inline-flex items-center gap-1">
              <Crown size={12} /> {t("right.pro")}
            </div>
          )}
          <div className="grid grid-cols-2 gap-2 mt-3">
            <Link to={`/profile/${user.id}`} className="text-xs text-center bg-zinc-800 hover:bg-zinc-700 rounded-md py-2 transition" data-testid="profile-link">
              {t("right.profile")}
            </Link>
            <button onClick={logout} className="text-xs bg-zinc-800 hover:bg-zinc-700 rounded-md py-2 transition flex items-center justify-center gap-1" data-testid="logout-btn">
              <LogOut size={12} /> {t("right.signOut")}
            </button>
          </div>
        </div>
      ) : (
        <div className="bg-zinc-900/70 border border-zinc-800 rounded-xl p-4 mb-4 space-y-2">
          <Link to="/login" className="block">
            <Button className="w-full bg-zinc-50 text-zinc-900 hover:bg-zinc-200" data-testid="signin-btn">
              <LogIn size={14} className="mr-2" /> {t("right.signIn")}
            </Button>
          </Link>
          <Link to="/register" className="block">
            <Button variant="outline" className="w-full border-zinc-700 hover:bg-zinc-800" data-testid="register-btn">
              <UserPlus size={14} className="mr-2" /> {t("right.createAccount")}
            </Button>
          </Link>
        </div>
      )}

      {/* PRO CTA */}
      {!user?.is_pro && (
        <Link to="/pro" data-testid="pro-cta">
          <div className="pro-border-gradient rounded-xl p-5 mb-4 hover:scale-[1.02] transition-transform">
            <div className="flex items-center gap-2 mb-2">
              <Crown className="pro-gradient-text" size={18} />
              <span className="font-heading font-bold text-zinc-50">{t("right.proTitle")}</span>
            </div>
            <p className="text-sm text-zinc-400 mb-3">{t("right.proSubtitle")}</p>
            <Button className="w-full pro-gradient text-white hover:opacity-90 border-0" data-testid="pro-upgrade-btn">
              {t("right.upgradeNow")}
            </Button>
          </div>
        </Link>
      )}

      {/* Live Chat - sits under Go Pro on home/listing pages */}
      {chatEnabled && (
        <LiveChat
          enabled={siteCfg?.live_chat_enabled ?? true}
          guestAllowed={siteCfg?.live_chat_guest_allowed ?? true}
          maxLen={siteCfg?.live_chat_max_message_length ?? 500}
        />
      )}

      {/* Recommendations (only on watch page) */}
      {recommendations && recommendations.length > 0 && (
        <div data-testid="recommendations">
          <div className="text-xs font-bold uppercase tracking-[0.2em] text-zinc-600 mb-3">{t("right.recommended")}</div>
          <div className="space-y-3">
            {recommendations.map((v) => (
              <Link key={v.id} to={`/watch/${v.id}`} className="flex gap-2 group" data-testid={`rec-${v.id}`}>
                <div className="w-24 aspect-video rounded-md overflow-hidden bg-zinc-800 flex-shrink-0 relative">
                  {v.thumbnail_url && (
                    <img src={mediaUrl(v.thumbnail_url)} alt="" className="w-full h-full object-cover group-hover:scale-105 transition-transform" />
                  )}
                  {v.duration_sec > 0 && (
                    <div className="absolute bottom-1 right-1 bg-black/85 text-white text-[10px] leading-none px-1 py-0.5 rounded">
                      {formatRecDuration(v.duration_sec)}
                    </div>
                  )}
                </div>
                <div className="flex-1 min-w-0">
                  <div className="text-sm font-medium line-clamp-2 text-zinc-200 group-hover:text-zinc-50">{v.title}</div>
                  <div className="text-xs text-zinc-500 mt-1">{v.views} {t("right.views")}</div>
                </div>
              </Link>
            ))}
          </div>
        </div>
      )}

      {!recommendations && pkgs.length > 0 && (
        <div className="mt-4">
          <div className="text-xs font-bold uppercase tracking-[0.2em] text-zinc-600 mb-3">{t("right.packages")}</div>
          <div className="space-y-2">
            {pkgs.slice(0, 3).map((p) => (
              <Link key={p.id} to="/pro" className="block bg-zinc-900 border border-zinc-800 rounded-md p-3 hover:bg-zinc-800/60 transition">
                <div className="flex items-center justify-between">
                  <span className="font-semibold text-sm" style={{ color: p.color }}>{p.name}</span>
                  <span className="text-sm font-bold">${p.price}</span>
                </div>
                <div className="text-xs text-zinc-500 mt-1">{p.duration_days} days</div>
              </Link>
            ))}
          </div>
        </div>
      )}
    </aside>
  );
}

function formatRecDuration(s) {
  const m = Math.floor(s / 60);
  const sec = Math.floor(s % 60);
  return `${m}:${String(sec).padStart(2, "0")}`;
}
