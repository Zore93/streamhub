import React, { useEffect, useState } from "react";
import { Outlet } from "react-router-dom";
import LeftSidebar from "./LeftSidebar";
import RightSidebar from "./RightSidebar";
import api from "@/lib/api";
import { Dialog, DialogContent, DialogTitle, DialogDescription, DialogHeader } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";

export function Layout({ recommendations = null, children }) {
  const [announcements, setAnnouncements] = useState([]);
  const [activeAnn, setActiveAnn] = useState(null);

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
      <LeftSidebar />
      <RightSidebar recommendations={recommendations} />
      <main className="ml-[240px] mr-[280px] min-h-screen px-6 sm:px-10 py-8 animate-fade-in" data-testid="main-content">
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
              Close
            </Button>
          </div>
        </DialogContent>
      </Dialog>
    </div>
  );
}
