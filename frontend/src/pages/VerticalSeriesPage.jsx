import React, { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { Film, Tv, Search } from "lucide-react";
import api from "@/lib/api";

/**
 * Generic grid of "series posters" for a vertical (hentai, tv, …).
 * One component powers /hentai and /seriale-tv so the UI stays consistent
 * even as we add more verticals. Pass the API base path, URL base path,
 * title and testid prefix via props.
 */
export default function VerticalSeriesPage({
  apiBase,
  basePath,
  title,
  testIdPrefix,
  // seasonFieldKey — kept for future "aggregate episodes" page, not used here
  seasonFieldKey,
}) {
  const [series, setSeries] = useState([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState("");

  useEffect(() => {
    setLoading(true);
    api.get(apiBase)
      .then((r) => setSeries(r.data))
      .catch(() => setSeries([]))
      .finally(() => setLoading(false));
  }, [apiBase]);

  const filtered = useMemo(() => {
    const q = search.trim().toLowerCase();
    if (!q) return series;
    return series.filter((s) =>
      (s.name || "").toLowerCase().includes(q) ||
      (s.tags || []).some((t) => (t || "").toLowerCase().includes(q))
    );
  }, [search, series]);

  return (
    <div data-testid={`page-${testIdPrefix}`}>
      <header className="flex items-center justify-between gap-3 mb-6 flex-wrap">
        <div className="flex items-center gap-3">
          <Tv size={26} className="text-rose-500" />
          <h1 className="text-3xl sm:text-4xl font-bold font-heading text-zinc-50">{title}</h1>
        </div>
      </header>

      <div className="relative mb-6 max-w-xl" data-testid={`${testIdPrefix}-search-wrap`}>
        <Search className="absolute left-3 top-1/2 -translate-y-1/2 text-zinc-500" size={16} />
        <input
          type="text"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder={`Caută serie ${title} după nume…`}
          className="w-full bg-zinc-900 border border-zinc-800 focus:border-rose-500/60 focus:outline-none text-zinc-100 pl-9 pr-3 py-2 rounded-md text-sm"
          data-testid={`${testIdPrefix}-search-input`}
        />
      </div>

      {loading && <p className="text-zinc-500 text-center py-12">Se încarcă…</p>}
      {!loading && filtered.length === 0 && (
        <p className="text-zinc-500 text-center py-12" data-testid={`${testIdPrefix}-empty`}>
          {series.length === 0
            ? `Nu există încă serii ${title}. Un admin le poate crea din Panou Admin.`
            : `Niciun rezultat pentru „${search}".`}
        </p>
      )}
      {!loading && filtered.length > 0 && (
        <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 gap-3 sm:gap-4" data-testid={`${testIdPrefix}-grid`}>
          {filtered.map((s) => (
            <Link key={s.id} to={`${basePath}/series/${s.slug || s.id}`} className="group block" data-testid={`${testIdPrefix}-poster-${s.slug || s.id}`}>
              <div className="relative aspect-[2/3] rounded-lg overflow-hidden bg-zinc-900 border border-zinc-800 group-hover:border-zinc-600 transition-colors">
                {s.cover_thumbnail ? (
                  <img src={s.cover_thumbnail} alt={s.name} loading="lazy" className="w-full h-full object-cover transition-transform group-hover:scale-105" />
                ) : (
                  <div className="w-full h-full flex items-center justify-center text-zinc-700"><Film size={40} /></div>
                )}
                {s.episode_count > 0 && (
                  <div className="absolute top-1.5 right-1.5 bg-black/70 backdrop-blur-sm text-zinc-100 text-[11px] font-semibold px-1.5 py-0.5 rounded">
                    {s.episode_count} ep
                  </div>
                )}
              </div>
              <div className="mt-2">
                <div className="text-sm font-semibold text-zinc-100 line-clamp-1">{s.name}</div>
                {s.tags?.length > 0 && <div className="text-[11px] text-zinc-500 line-clamp-1 mt-0.5">{s.tags.slice(0, 3).join(" · ")}</div>}
              </div>
            </Link>
          ))}
        </div>
      )}
    </div>
  );
}
