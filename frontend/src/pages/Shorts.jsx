import React, { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { Smartphone, Film, Search } from "lucide-react";
import api from "@/lib/api";
import { useT } from "@/contexts/LanguageContext";

/**
 * Shorts landing page — Netflix-style poster grid of shorts series.
 * Prop `category="xxx"|"drama"` picks which vertical to show. The same
 * component powers both /shorts (XXX Shorts) and /drama-shorts.
 */
export default function Shorts({ category = "xxx" }) {
  const { t } = useT();
  const [series, setSeries] = useState([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState("");
  const isDrama = category === "drama";
  const heading = isDrama ? "Drama Shorts" : "XXX Shorts";
  const listAllPath = isDrama ? "/drama-shorts/all" : "/shorts/all";
  const seriesPathBase = isDrama ? "/drama-shorts/series" : "/shorts/series";
  const filteredSeries = useFilteredSeries(series, search);

  useEffect(() => {
    setLoading(true);
    api.get(`/shorts-series?category=${category}`)
      .then((r) => setSeries(r.data))
      .catch(() => {})
      .finally(() => setLoading(false));
  }, [category]);

  return (
    <div data-testid={`page-shorts-${category}`}>
      <header className="flex items-center justify-between gap-3 mb-6 flex-wrap">
        <div className="flex items-center gap-3">
          <Smartphone size={26} className="text-rose-500" />
          <h1 className="text-3xl sm:text-4xl font-bold font-heading text-zinc-50">
            {heading}
          </h1>
        </div>
        <Link
          to={listAllPath}
          className="text-sm text-rose-400 hover:text-rose-300 flex items-center gap-1"
          data-testid={`shorts-${category}-view-all`}
        >
          <Film size={14} /> {t("shorts.viewAll") || "Toate shorts-urile"}
        </Link>
      </header>

      <div className="relative mb-6 max-w-xl" data-testid={`shorts-${category}-search-wrap`}>
        <Search className="absolute left-3 top-1/2 -translate-y-1/2 text-zinc-500" size={16} />
        <input
          type="text"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder={`Caută serie ${heading} după nume…`}
          className="w-full bg-zinc-900 border border-zinc-800 focus:border-rose-500/60 focus:outline-none text-zinc-100 pl-9 pr-3 py-2 rounded-md text-sm"
          data-testid={`shorts-${category}-search-input`}
        />
      </div>

      {loading && (
        <p className="text-zinc-500 text-center py-12">
          {t("common.loading") || "Se încarcă…"}
        </p>
      )}

      {!loading && filteredSeries.length === 0 && (
        <p className="text-zinc-500 text-center py-12" data-testid={`shorts-${category}-empty`}>
          {series.length === 0
            ? `Nu există încă serii ${heading}. Un admin le poate crea din Panou Admin.`
            : `Niciun rezultat pentru „${search}".`}
        </p>
      )}

      {!loading && filteredSeries.length > 0 && (
        <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 gap-3 sm:gap-4">
          {filteredSeries.map((s) => <SeriesPoster key={s.id} s={s} basePath={seriesPathBase} />)}
        </div>
      )}
    </div>
  );
}

function useFilteredSeries(series, search) {
  return useMemo(() => {
    const q = (search || "").trim().toLowerCase();
    if (!q) return series;
    return series.filter((s) =>
      (s.name || "").toLowerCase().includes(q) ||
      (s.tags || []).some((t) => (t || "").toLowerCase().includes(q))
    );
  }, [series, search]);
}

function SeriesPoster({ s, basePath }) {
  const cover = s.cover_thumbnail;
  return (
    <Link
      to={`${basePath}/${s.slug || s.id}`}
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
