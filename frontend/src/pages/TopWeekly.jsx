import React, { useEffect, useState } from "react";
import { useParams, useNavigate } from "react-router-dom";
import api from "@/lib/api";
import { Layout } from "@/layout/Layout";
import SiteHead from "@/components/SiteHead";
import VideoCard from "@/components/VideoCard";
import { Flame, Crown, TrendingUp } from "lucide-react";

// ─── Shared vertical tab config used by both /top and /trending ─────────────
export const VERTICAL_TABS = [
  { id: "hentai",   label: "Hentai RoSub" },
  { id: "anime",    label: "Anime" },
  { id: "filme",    label: "Filme RoSub" },
  { id: "seriale",  label: "Seriale TV" },
  { id: "drama",    label: "Drama Shorts" },
  { id: "xxx",      label: "XXX Shorts" },
];

/* ──────────────────────────────────────────────────────────────────────────
 * Current ISO week helper. Mirrors backend `_iso_week_key`.
 * ─────────────────────────────────────────────────────────────────────────*/
function currentIsoWeek() {
  const now = new Date();
  // ISO week numbering: shift date to Thursday of same week, then number weeks
  const target = new Date(Date.UTC(now.getUTCFullYear(), now.getUTCMonth(), now.getUTCDate()));
  const dayNr = (target.getUTCDay() + 6) % 7;
  target.setUTCDate(target.getUTCDate() - dayNr + 3);
  const firstThursday = new Date(Date.UTC(target.getUTCFullYear(), 0, 4));
  const weekNum = 1 + Math.round(((target - firstThursday) / 86400000 - 3 + ((firstThursday.getUTCDay() + 6) % 7)) / 7);
  return `${target.getUTCFullYear()}-W${String(weekNum).padStart(2, "0")}`;
}

export default function TopWeekly() {
  const { week: urlWeek, vertical: urlVertical } = useParams();
  const navigate = useNavigate();
  const [vertical, setVertical] = useState(urlVertical || "hentai");
  const [week] = useState(urlWeek || currentIsoWeek());
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    setLoading(true);
    api.get(`/top-weekly?vertical=${vertical}&week=${week}&limit=10`)
      .then((r) => setItems(r.data.items || []))
      .catch(() => setItems([]))
      .finally(() => setLoading(false));
  }, [vertical, week]);

  const changeTab = (id) => {
    setVertical(id);
    // Keep URL meaningful for SEO: /top/<vertical>/<week>
    navigate(`/top/${id}/${week}`, { replace: true });
  };

  const label = VERTICAL_TABS.find((t) => t.id === vertical)?.label || vertical;

  return (
    <Layout>
      <SiteHead
        title={`Top 10 Săptămânal — ${label} · ${week}`}
        description={`Cele mai vizionate ${label.toLowerCase()} din săptămâna ${week}. Clasament actualizat în timp real.`}
      />
      <div data-testid="top-weekly-page">
        <div className="flex items-center gap-3 mb-4">
          <div className="h-10 w-10 rounded-lg bg-gradient-to-br from-amber-400 to-rose-500 flex items-center justify-center">
            <Crown size={20} className="text-black" />
          </div>
          <div>
            <h1 className="text-2xl sm:text-3xl font-bold">Top 10 Săptămânal</h1>
            <p className="text-xs text-zinc-500">Săptămâna {week} · se resetează în fiecare luni</p>
          </div>
        </div>

        {/* Tabs */}
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
              data-testid={`top-tab-${tab.id}`}
            >
              {tab.label}
            </button>
          ))}
        </div>

        {/* Content */}
        {loading ? (
          <div className="text-zinc-500 py-10 text-center">Se încarcă topul…</div>
        ) : items.length === 0 ? (
          <div className="text-zinc-500 py-10 text-center" data-testid="top-empty">
            Nicio vizualizare înregistrată săptămâna aceasta în {label}. Fii primul!
          </div>
        ) : (
          <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-4" data-testid="top-grid">
            {items.map((v, i) => (
              <div key={v.id} className="relative">
                <div
                  className={`absolute top-2 left-2 z-10 w-8 h-8 rounded-full flex items-center justify-center font-black text-sm shadow-lg ${
                    i === 0 ? "bg-amber-400 text-black" :
                    i === 1 ? "bg-zinc-300 text-black" :
                    i === 2 ? "bg-amber-700 text-white" :
                    "bg-black/80 text-white border border-zinc-700"
                  }`}
                >
                  {i + 1}
                </div>
                <VideoCard v={v} />
                <div className="mt-1 text-xs text-rose-300 flex items-center gap-1">
                  <TrendingUp size={11} /> {v.weekly_views} vizualizări săptămâna aceasta
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </Layout>
  );
}
