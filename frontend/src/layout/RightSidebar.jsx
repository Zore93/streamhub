import React, { useEffect, useState } from "react";
import { Link, useLocation } from "react-router-dom";
import { Crown, LogIn, UserPlus, LogOut, User as UserIcon, X, ShoppingBag, Coins, Film, Eye, Heart, MessageCircle } from "lucide-react";
import { useAuth } from "@/contexts/AuthContext";
import api, { mediaUrl } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { useT } from "@/contexts/LanguageContext";
import FramedAvatar from "@/components/FramedAvatar";
import DiscordWidget from "@/components/DiscordWidget";
import LiveChat from "./LiveChat";

export default function RightSidebar({ recommendations = null, mobileOpen = false, onMobileClose }) {
  const { user, logout } = useAuth();
  const { t, siteCfg } = useT();
  const [pkgs, setPkgs] = useState([]);
  const { pathname } = useLocation();

  useEffect(() => {
    api.get("/packages").then((r) => setPkgs(r.data)).catch(() => {});
  }, []);

  // Auto-close mobile drawer on route change (so picking a package navigates cleanly).
  useEffect(() => { if (mobileOpen) onMobileClose?.(); /* eslint-disable-next-line */ }, [pathname]);

  // Live chat is only shown on the home/listing pages (not on watch page where
  // we surface recommendations).  Admin can disable chat globally in settings.
  const chatEnabled = !recommendations && (siteCfg?.live_chat_enabled ?? true);

  const body = <RightSidebarBody
    user={user}
    logout={logout}
    t={t}
    pkgs={pkgs}
    chatEnabled={chatEnabled}
    siteCfg={siteCfg}
    recommendations={recommendations}
    onMobileClose={onMobileClose}
    showCloseButton={mobileOpen}
    selectedFrame={user?.selected_frame || null}
  />;

  return (
    <>
      {/* Desktop right rail */}
      <aside
        data-testid="right-sidebar"
        className="hidden lg:block fixed right-0 top-0 h-screen w-[280px] xl:w-[300px] border-l border-zinc-800 bg-zinc-950/90 backdrop-blur-xl p-5 overflow-y-auto custom-scrollbar z-30"
      >
        {body}
      </aside>

      {/* Mobile drawer (account / login / PRO / chat) */}
      {mobileOpen && (
        <>
          <button
            aria-label="Close account panel"
            onClick={onMobileClose}
            className="lg:hidden fixed inset-0 bg-black/60 z-40 animate-fade-in"
            data-testid="mobile-account-backdrop"
          />
          <aside
            data-testid="mobile-right-sidebar"
            className="lg:hidden fixed right-0 top-0 h-screen w-[300px] max-w-[85vw] border-l border-zinc-800 bg-zinc-950 p-5 overflow-y-auto custom-scrollbar z-50 animate-slide-in-right"
          >
            {body}
          </aside>
        </>
      )}
    </>
  );
}

function RightSidebarBody({ user, logout, t, pkgs, chatEnabled, siteCfg, recommendations, onMobileClose, showCloseButton, selectedFrame }) {
  return (
    <>
      {showCloseButton && (
        <div className="flex justify-end mb-2 lg:hidden">
          <button
            onClick={onMobileClose}
            className="p-1.5 rounded-md text-zinc-400 hover:text-zinc-100 hover:bg-zinc-800"
            aria-label="Close"
            data-testid="mobile-account-close"
          >
            <X size={18} />
          </button>
        </div>
      )}
      {/* User block */}
      {user ? (
        <div data-testid="user-block" className="bg-zinc-900/70 border border-zinc-800 rounded-xl p-4 mb-4">
          <div className="flex items-center gap-3">
            <FramedAvatar
              src={user.avatar_url}
              username={user.username}
              size={48}
              frame={selectedFrame}
            />
            <div className="flex-1 min-w-0">
              <div className="font-semibold truncate text-zinc-50">{user.username}</div>
              <div className="text-xs text-amber-300 inline-flex items-center gap-1 mt-0.5" data-testid="sidebar-coins">
                <Coins size={12} /> {user.coins || 0} {t("common.coins")}
              </div>
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
          <Link
            to="/shop"
            className="mt-2 flex items-center justify-center gap-1.5 text-xs font-medium bg-gradient-to-r from-amber-500/20 to-rose-500/20 border border-amber-500/40 text-amber-100 hover:from-amber-500/30 hover:to-rose-500/30 rounded-md py-2 transition"
            data-testid="shop-link"
          >
            <ShoppingBag size={12} /> {t("shop.shopNav")}
          </Link>
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
      {!user?.is_pro && !user?.is_vip && (
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

      {/* VIP CTA — separate card, gold theme */}
      {!user?.is_vip && (
        <Link to="/vip" data-testid="vip-cta">
          <div className="vip-border-gradient rounded-xl p-5 mb-4 hover:scale-[1.02] transition-transform">
            <div className="flex items-center gap-2 mb-2">
              <Crown className="vip-gradient-text" size={18} />
              <span className="font-heading font-bold text-zinc-50">{t("right.vipTitle")}</span>
            </div>
            <p className="text-sm text-zinc-400 mb-3">{t("right.vipSubtitle")}</p>
            <Button className="w-full vip-gradient text-black font-bold hover:opacity-90 border-0" data-testid="vip-upgrade-btn">
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

      {/* Discord widget - appears under chat on home/listing pages */}
      {!recommendations && (siteCfg?.discord_widget_enabled ?? true) && (siteCfg?.discord_invite_url || siteCfg?.discord_guild_id) && (
        <DiscordWidget
          guildId={siteCfg?.discord_guild_id || ""}
          inviteUrl={siteCfg?.discord_invite_url || ""}
        />
      )}

      {/* Live site stats — under Discord, only on home/listing pages */}
      {!recommendations && <SiteStatsWidget />}

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
    </>
  );
}

function formatRecDuration(s) {
  const m = Math.floor(s / 60);
  const sec = Math.floor(s % 60);
  return `${m}:${String(sec).padStart(2, "0")}`;
}

/** Compact "1.2K" / "3.4M" formatter for the stats widget. */
function abbreviate(n) {
  const num = Number(n) || 0;
  if (num < 1000) return String(num);
  if (num < 1_000_000) return `${(num / 1000).toFixed(num < 10_000 ? 1 : 0).replace(/\.0$/, "")}K`;
  if (num < 1_000_000_000) return `${(num / 1_000_000).toFixed(num < 10_000_000 ? 1 : 0).replace(/\.0$/, "")}M`;
  return `${(num / 1_000_000_000).toFixed(1).replace(/\.0$/, "")}B`;
}

/**
 * Live site stats block — polls /api/stats every 30s.
 * Rendered under the Discord widget on the home / listing pages only.
 */
function SiteStatsWidget() {
  const { t } = useT();
  const [stats, setStats] = useState(null);

  useEffect(() => {
    let alive = true;
    const load = () => {
      api.get("/stats")
        .then((r) => { if (alive) setStats(r.data); })
        .catch(() => {});
    };
    load();
    const id = setInterval(load, 30_000);
    return () => { alive = false; clearInterval(id); };
  }, []);

  if (!stats) return null;

  const rows = [
    { icon: Film,           label: t("stats.videos"),   value: stats.total_videos,   color: "text-rose-400" },
    { icon: Eye,            label: t("stats.views"),    value: stats.total_views,    color: "text-sky-400" },
    { icon: Heart,          label: t("stats.likes"),    value: stats.total_likes,    color: "text-pink-400" },
    { icon: MessageCircle,  label: t("stats.comments"), value: stats.total_comments, color: "text-emerald-400" },
  ];

  return (
    <div className="bg-zinc-900/60 border border-zinc-800 rounded-xl p-4 mb-4" data-testid="site-stats">
      <div className="text-xs font-bold uppercase tracking-[0.2em] text-zinc-500 mb-3">
        {t("stats.title")}
      </div>
      <div className="grid grid-cols-2 gap-3">
        {rows.map(({ icon: Icon, label, value, color }) => (
          <div key={label} className="flex items-start gap-2">
            <Icon size={16} className={`${color} mt-0.5 shrink-0`} />
            <div className="min-w-0">
              <div className="text-lg font-bold text-zinc-100 leading-tight" title={String(value)}>
                {abbreviate(value)}
              </div>
              <div className="text-[10px] uppercase tracking-wider text-zinc-500 truncate">
                {label}
              </div>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
