import React, { useEffect, useState } from "react";
import { Outlet } from "react-router-dom";
import { Menu, X } from "lucide-react";
import LeftSidebar from "./LeftSidebar";
import RightSidebar from "./RightSidebar";
import api from "@/lib/api";
import { Dialog, DialogContent, DialogTitle, DialogDescription, DialogHeader } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { useT } from "@/contexts/LanguageContext";

export function Layout({ recommendations = null, children }) {
  const { t } = useT();
  const [announcements, setAnnouncements] = useState([]);
  const [activeAnn, setActiveAnn] = useState(null);
  const [navOpen, setNavOpen] = useState(false);

  useEffect(() => {
    api.get("/announcements/active").then((r) => {
      const dismissed = JSON.parse(localStorage.getItem("dismissedAnnouncements") || "[]");
      const filtered = r.data.filter((a) => !dismissed.includes(a.id));
      setAnnouncements(filtered);
      if (filtered[0]) setActiveAnn(filtered[0]);
    }).catch(() => {});
  }, []);

  const closeAnn = () => {
    if (!activeAnn) return;
    const dismissed = JSON.parse(localStorage.getItem("dismissedAnnouncements") || "[]");
    dismissed.push(activeAnn.id);
    localStorage.setItem("dismissedAnnouncements", JSON.stringify(dismissed));
    const next = announcements.filter((a) => a.id !== activeAnn.id);
    setAnnouncements(next);
    setActiveAnn(next[0] || null);
  };

  return (
    <div className="min-h-screen bg-zinc-950 text-zinc-100">
      {/* Mobile top bar */}
      <header
        className="lg:hidden sticky top-0 z-40 h-14 bg-zinc-950/95 backdrop-blur-xl border-b border-zinc-800 flex items-center justify-between px-3"
        data-testid="mobile-topbar"
      >
        <button
          onClick={() => setNavOpen(true)}
          className="p-2 rounded-md text-zinc-300 hover:bg-zinc-800"
          aria-label={t("site.openMenu")}
          data-testid="mobile-menu-btn"
        >
          <Menu size={22} />
        </button>
        <a href="/" className="flex items-center gap-2 mx-auto" data-testid="mobile-brand">
          <div className="h-7 w-7 rounded-md pro-gradient flex items-center justify-center font-heading font-bold text-white text-sm">S</div>
          <span className="font-heading font-bold text-base">StreamHub</span>
        </a>
        <div className="w-9" /> {/* spacer to keep brand centered */}
      </header>

      <LeftSidebar mobileOpen={navOpen} onClose={() => setNavOpen(false)} />
      <RightSidebar recommendations={recommendations} />

      <main
        className="lg:ml-[240px] lg:mr-[280px] xl:mr-[300px] min-h-screen px-4 sm:px-6 lg:px-10 py-6 lg:py-8 animate-fade-in"
        data-testid="main-content"
      >
        {children || <Outlet />}
      </main>

      <Dialog open={!!activeAnn} onOpenChange={(o) => !o && closeAnn()}>
        <DialogContent className="bg-zinc-900 border-zinc-800 max-w-md" data-testid="announcement-modal">
          <DialogHeader>
            <DialogTitle className="text-2xl font-heading">{activeAnn?.title}</DialogTitle>
            <DialogDescription className="text-zinc-400 whitespace-pre-line pt-2">
              {activeAnn?.content}
            </DialogDescription>
          </DialogHeader>
          <div className="flex justify-end mt-4">
            <Button onClick={closeAnn} className="pro-gradient text-white border-0" data-testid="announcement-close">
              {t("common.close")}
            </Button>
          </div>
        </DialogContent>
      </Dialog>
    </div>
  );
}
