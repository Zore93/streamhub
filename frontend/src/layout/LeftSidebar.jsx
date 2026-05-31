import React, { useEffect, useState } from "react";
import { Link, useLocation } from "react-router-dom";
import { Folder, Home as HomeIcon, Flame, Shuffle, Upload as UploadIcon, Shield } from "lucide-react";
import api from "@/lib/api";
import { useAuth } from "@/contexts/AuthContext";

export default function LeftSidebar() {
  const [cats, setCats] = useState([]);
  const { pathname, search } = useLocation();
  const { user } = useAuth();

  useEffect(() => {
    api.get("/categories").then((r) => setCats(r.data)).catch(() => {});
  }, []);

  const navItems = [
    { to: "/", label: "Home", Icon: HomeIcon },
    { to: "/?section=popular", label: "Popular", Icon: Flame },
    { to: "/?section=random", label: "Discover", Icon: Shuffle },
  ];
  if (user) navItems.push({ to: "/upload", label: "Upload", Icon: UploadIcon });
  if (user?.role === "admin") navItems.push({ to: "/admin", label: "Admin Panel", Icon: Shield });

  const activeCls = "bg-zinc-800/70 text-zinc-50";
  const baseCls = "flex items-center gap-3 px-4 py-2.5 rounded-md text-zinc-400 hover:text-zinc-50 hover:bg-zinc-800/50 transition-colors text-sm";

  return (
    <aside
      data-testid="left-sidebar"
      className="fixed left-0 top-0 h-screen w-[240px] border-r border-zinc-800 bg-zinc-950/90 backdrop-blur-xl p-4 flex flex-col gap-1 overflow-y-auto custom-scrollbar z-30"
    >
      <Link to="/" className="flex items-center gap-2 px-2 py-3 mb-2" data-testid="brand-link">
        <div className="h-8 w-8 rounded-md pro-gradient flex items-center justify-center font-heading font-bold text-white">S</div>
        <span className="font-heading font-bold text-xl tracking-tight">StreamHub</span>
      </Link>

      <div className="text-xs font-bold uppercase tracking-[0.2em] text-zinc-600 px-4 py-2">Browse</div>
      {navItems.map(({ to, label, Icon }) => {
        const isActive = to === "/" ? pathname === "/" && !search : pathname + search === to || (to.includes("?") && search === to.split("?")[1].replace("?", ""));
        return (
          <Link key={to} to={to} className={`${baseCls} ${isActive ? activeCls : ""}`} data-testid={`nav-${label.toLowerCase()}`}>
            <Icon size={16} />
            <span>{label}</span>
          </Link>
        );
      })}

      <div className="text-xs font-bold uppercase tracking-[0.2em] text-zinc-600 px-4 py-2 mt-4">Categories</div>
      {cats.length === 0 && <div className="px-4 py-2 text-xs text-zinc-600">No categories</div>}
      {cats.map((c) => (
        <Link key={c.id} to={`/category/${c.id}`} className={baseCls} data-testid={`cat-${c.slug}`}>
          <Folder size={16} />
          <span className="truncate">{c.name}</span>
        </Link>
      ))}
    </aside>
  );
}
