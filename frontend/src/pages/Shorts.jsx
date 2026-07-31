import React, { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { Smartphone, Film } from "lucide-react";
import api from "@/lib/api";
import { useT } from "@/contexts/LanguageContext";

/**
 * Shorts landing page — Netflix-style poster grid of shorts series.
 * Each series links to /shorts/series/:slug (the SeriesDetail page).
 * A "Toate shorts-urile" link at the top jumps to /shorts/all (VideoList variant).
 */
export default function Shorts() {
  const { t } = useT();
  const [series, setSeries] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    api.get("/shorts-series")
      .then((r) => setSeries(r.data))
      .catch(() => {})
      .finally(() => setLoading(false));
  }, []);

  return (
    <div data-testid="page-shorts">
      <header className="flex items-center justify-between gap-3 mb-6 flex-wrap">
        <div className="flex items-center gap-3">
          <Smartphone size={26} className="text-rose-500" />
          <h1 className="text-3xl sm:text-4xl font-bold font-heading text-zinc-50">
            {t("page.shorts")}
          </h1>
        </div>
        <Link
          to="/shorts/all"
          className="text-sm text-rose-400 hover:text-rose-300 flex items-center gap-1"
          data-testid="shorts-view-all"
        >
          <Film size={14} /> {t("shorts.viewAll") || "Toate shorts-urile"}
        </Link>
      </header>

      {loading && (
        <p className="text-zinc-500 text-center py-12" data-testid="shorts-loading">
          {t("common.loading") || "Se încarcă…"}
        </p>
      )}

      {!loading && series.length === 0 && (
        <p className="text-zinc-500 text-center py-12" data-testid="shorts-empty">
          Nu există încă serii Shorts. Un admin le poate crea din Panou Admin → Serii Shorts.
        </p>
      )}

      {!loading && series.length > 0 && (
        <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 gap-3 sm:gap-4">
          {series.map((s) => <SeriesPoster key={s.id} s={s} />)}
        </div>
      )}
    </div>
  );
}

function SeriesPoster({ s }) {
  const cover = s.cover_thumbnail;
  return (
    <Link
      to={`/shorts/series/${s.slug || s.id}`}
      className="group block"
      data-testid={`series-poster-${s.slug || s.id}`}
    >
      <div className="relative aspect-[2/3] rounded-lg overflow-hidden bg-zinc-900 border border-zinc-800 group-hover:border-zinc-600 transition-colors">
        {cover ? (
          <img
            src={cover}
            alt={s.name}
            loading="lazy"
            className="w-full h-full object-cover transition-transform group-hover:scale-105"
          />
        ) : (
          <div className="w-full h-full flex items-center justify-center text-zinc-700">
            <Film size={40} />
          </div>
        )}
        {/* Episode-count badge — top-right, subtle rose accent */}
        {s.episode_count > 0 && (
          <div className="absolute top-1.5 right-1.5 bg-black/70 backdrop-blur-sm text-zinc-100 text-[11px] font-semibold px-1.5 py-0.5 rounded">
            {s.episode_count} ep
          </div>
        )}
      </div>
      <div className="mt-2">
        <div className="text-sm font-semibold text-zinc-100 line-clamp-1">{s.name}</div>
        {s.tags?.length > 0 && (
          <div className="text-[11px] text-zinc-500 line-clamp-1 mt-0.5">
            {s.tags.slice(0, 3).join(" · ")}
          </div>
        )}
      </div>
    </Link>
  );
}
