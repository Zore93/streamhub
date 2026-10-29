import React, { useEffect, useState } from "react";
import { useParams, useNavigate } from "react-router-dom";
import api from "@/lib/api";
import { Layout } from "@/layout/Layout";
import SiteHead from "@/components/SiteHead";
import VideoCard from "@/components/VideoCard";
import { Flame, TrendingUp } from "lucide-react";
import { VERTICAL_TABS } from "./TopWeekly";

export default function Trending() {
  const { vertical: urlVertical } = useParams();
  const navigate = useNavigate();
  const [vertical, setVertical] = useState(urlVertical || "hentai");
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    setLoading(true);
    api.get(`/trending?vertical=${vertical}&limit=20`)
      .then((r) => setItems(r.data.items || []))
      .catch(() => setItems([]))
      .finally(() => setLoading(false));
  }, [vertical]);

  const changeTab = (id) => {
    setVertical(id);
    navigate(`/trending/${id}`, { replace: true });
  };

  const label = VERTICAL_TABS.find((t) => t.id === vertical)?.label || vertical;

  return (
    <Layout>
      <SiteHead
        title={`Trending acum — ${label}`}
        description={`Cele mai urmărite ${label.toLowerCase()} chiar acum. Clasament actualizat în timp real.`}
      />
      <div data-testid="trending-page">
        <div className="flex items-center gap-3 mb-4">
          <div className="h-10 w-10 rounded-lg bg-gradient-to-br from-rose-500 to-fuchsia-500 flex items-center justify-center">
            <Flame size={20} className="text-white" />
          </div>
          <div>
            <h1 className="text-2xl sm:text-3xl font-bold">Trending acum</h1>
            <p className="text-xs text-zinc-500">Ce urmăresc toți în ultimele 48h</p>
          </div>
        </div>

        <div className="flex flex-wrap gap-2 mb-6 border-b border-zinc-800 pb-3">
          {VERTICAL_TABS.map((tab) => (
            <button
              key={tab.id}
              onClick={() => changeTab(tab.id)}
              className={`px-3 py-1.5 rounded-full text-sm font-medium transition-colors ${
                vertical === tab.id
                  ? "bg-rose-500 text-white"
                  : "bg-zinc-900 text-zinc-300 hover:bg-zinc-800"
              }`}
              data-testid={`trending-tab-${tab.id}`}
            >
              {tab.label}
            </button>
          ))}
        </div>

        {loading ? (
          <div className="text-zinc-500 py-10 text-center">Se încarcă…</div>
        ) : items.length === 0 ? (
          <div className="text-zinc-500 py-10 text-center" data-testid="trending-empty">
            Niciun videoclip în trending pentru {label} în ultimele 48h.
          </div>
        ) : (
          <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-4" data-testid="trending-grid">
            {items.map((v) => (
              <div key={v.id}>
                <VideoCard v={v} />
                <div className="mt-1 text-xs text-rose-300 flex items-center gap-1">
                  <TrendingUp size={11} /> {v.window_views} vizualizări în 48h
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </Layout>
  );
}
