import React, { useEffect, useState } from "react";
import { Link, useLocation } from "react-router-dom";
import {
  Folder, Home as HomeIcon, Flame, Shuffle, Smartphone, ListVideo,
  Upload as UploadIcon, Shield, Mail, X, Languages,
} from "lucide-react";
import api, { mediaUrl } from "@/lib/api";
import { useAuth } from "@/contexts/AuthContext";
import { useT } from "@/contexts/LanguageContext";
import { categoryLabel } from "@/i18n";

export default function LeftSidebar({ mobileOpen = false, onClose }) {
  const [cats, setCats] = useState([]);
  const { pathname } = useLocation();
  const { user } = useAuth();
  const { t, lang, setLang, supported, siteCfg } = useT();

  useEffect(() => {
    api.get("/categories").then((r) => setCats(r.data)).catch(() => {});
  }, []);

  // Auto-close mobile drawer on route change
  useEffect(() => { if (mobileOpen) onClose?.(); /* eslint-disable-next-line */ }, [pathname]);

  const navItems = [
    { to: "/", label: t("nav.home"), Icon: HomeIcon, testid: "nav-home" },
    { to: "/popular", label: t("nav.popular"), Icon: Flame, testid: "nav-popular" },
    { to: "/discover", label: t("nav.discover"), Icon: Shuffle, testid: "nav-discover" },
    { to: "/shorts", label: t("nav.shorts"), Icon: Smartphone, testid: "nav-shorts" },
    { to: "/drama-shorts", label: t("nav.dramaShorts") || "Drama Shorts", Icon: Smartphone, testid: "nav-drama-shorts" },
    { to: "/anime", label: "Anime", Icon: Smartphone, testid: "nav-anime" },
    { to: "/all-episodes", label: t("nav.allEpisodes"), Icon: ListVideo, testid: "nav-all-episodes" },
    { to: "/contact", label: t("nav.contact"), Icon: Mail, testid: "nav-contact" },
  ];
  if (user) navItems.push({ to: "/upload", label: t("nav.upload"), Icon: UploadIcon, testid: "nav-upload" });
  if (user?.role === "admin") navItems.push({ to: "/admin", label: t("nav.adminPanel"), Icon: Shield, testid: "nav-admin" });

  const activeCls = "bg-zinc-800/70 text-zinc-50";
  const baseCls = "flex items-center gap-3 px-4 py-2.5 rounded-md text-zinc-400 hover:text-zinc-50 hover:bg-zinc-800/50 transition-colors text-sm";

  const sidebarInner = (
    <>
      <div className="flex items-center justify-between px-2 py-3 mb-2">
        <Link to="/" className="flex items-center gap-2 min-w-0" data-testid="brand-link">
          {siteCfg?.logo_url ? (
            <img
              src={mediaUrl(siteCfg.logo_url)}
              alt={siteCfg.title || "StreamHub"}
              className="h-9 max-w-[180px] object-contain"
              data-testid="brand-logo-img"
            />
          ) : (
            <>
              <div className="h-8 w-8 rounded-md pro-gradient flex items-center justify-center font-heading font-bold text-white">S</div>
              <span className="font-heading font-bold text-xl tracking-tight truncate">{siteCfg?.title || "StreamHub"}</span>
            </>
          )}
        </Link>
        <button
          onClick={onClose}
          className="lg:hidden p-1.5 rounded-md text-zinc-400 hover:text-zinc-100 hover:bg-zinc-800"
          aria-label={t("site.closeMenu")}
          data-testid="mobile-close-btn"
        >
          <X size={18} />
        </button>
      </div>

      <div className="text-xs font-bold uppercase tracking-[0.2em] text-zinc-600 px-4 py-2">{t("nav.browse")}</div>
      {navItems.map(({ to, label, Icon, testid }) => {
        const isActive = to === "/" ? pathname === "/" : pathname === to || pathname.startsWith(to + "/");
        return (
          <Link key={to} to={to} className={`${baseCls} ${isActive ? activeCls : ""}`} data-testid={testid}>
            <Icon size={16} />
            <span>{label}</span>
          </Link>
        );
      })}

      <div className="text-xs font-bold uppercase tracking-[0.2em] text-zinc-600 px-4 py-2 mt-4">{t("nav.categories")}</div>
      {cats.length === 0 && <div className="px-4 py-2 text-xs text-zinc-600">{t("nav.noCategories")}</div>}
      {cats.map((c) => (
        <Link key={c.id} to={`/category/${c.id}`} className={baseCls} data-testid={`cat-${c.slug}`}>
          <Folder size={16} />
          <span className="truncate">{categoryLabel(c, lang)}</span>
        </Link>
      ))}

      {/* Language picker — visible on every page */}
      <div className="mt-auto pt-4 px-2">
        <div className="flex items-center gap-2 px-2 mb-2 text-xs text-zinc-500">
          <Languages size={12} /> {t("site.language")}
        </div>
        <div className="flex gap-1 px-2" data-testid="lang-switcher">
          {supported.map((l) => (
            <button
              key={l.code}
              onClick={() => setLang(l.code)}
              className={`flex-1 px-2 py-1 text-xs font-medium rounded-md transition-colors ${
                lang === l.code
                  ? "bg-rose-500/90 text-white"
                  : "bg-zinc-900 text-zinc-400 hover:bg-zinc-800 hover:text-zinc-100"
              }`}
              data-testid={`lang-${l.code}`}
            >
              {l.label}
            </button>
          ))}
        </div>
      </div>
    </>
  );

  return (
    <>
      {/* Desktop sidebar */}
      <aside
        data-testid="left-sidebar"
        className="hidden lg:flex fixed left-0 top-0 h-screen w-[240px] border-r border-zinc-800 bg-zinc-950/90 backdrop-blur-xl p-4 flex-col gap-1 overflow-y-auto custom-scrollbar z-30"
      >
        {sidebarInner}
      </aside>

      {/* Mobile drawer */}
      {mobileOpen && (
        <>
          <button
            aria-label="Close menu"
            onClick={onClose}
            className="lg:hidden fixed inset-0 bg-black/60 z-40 animate-fade-in"
            data-testid="mobile-nav-backdrop"
          />
          <aside
            data-testid="mobile-left-sidebar"
            className="lg:hidden fixed left-0 top-0 h-screen w-[260px] max-w-[80vw] border-r border-zinc-800 bg-zinc-950 p-4 flex flex-col gap-1 overflow-y-auto custom-scrollbar z-50 animate-slide-in-left"
          >
            {sidebarInner}
          </aside>
        </>
      )}
    </>
  );
}
