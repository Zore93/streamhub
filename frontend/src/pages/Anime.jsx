import React, { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { Film, Tv, Search } from "lucide-react";
import api from "@/lib/api";
import Pagination from "@/components/Pagination";

const PAGE_SIZE = 25;

/** /anime — poster grid of anime series (long-form). Now with inline
 *  search over series names so users can quickly jump to a title in a
 *  large library without scrolling the whole poster wall. */
export default function Anime() {
  const [series, setSeries] = useState([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState("");
  const [page, setPage] = useState(1);

  useEffect(() => {
    api.get("/anime-series").then((r) => setSeries(r.data)).catch(() => {}).finally(() => setLoading(false));
  }, []);

  const filtered = useMemo(() => {
    const q = search.trim().toLowerCase();
    if (!q) return series;
    return series.filter((s) =>
      (s.name || "").toLowerCase().includes(q) ||
      (s.tags || []).some((t) => (t || "").toLowerCase().includes(q))
    );
  }, [search, series]);

  const totalPages = Math.max(1, Math.ceil(filtered.length / PAGE_SIZE));
  const pageItems = filtered.slice((page - 1) * PAGE_SIZE, page * PAGE_SIZE);
  useEffect(() => { if (page > totalPages) setPage(1); }, [totalPages, page]);
  useEffect(() => { setPage(1); }, [search]);
  const handlePageChange = (p) => {
    setPage(p);
    window.scrollTo({ top: 0, behavior: "smooth" });
  };

  return (
    <div data-testid="page-anime">
      <header className="flex items-center justify-between gap-3 mb-6 flex-wrap">
        <div className="flex items-center gap-3">
          <Tv size={26} className="text-rose-500" />
          <h1 className="text-3xl sm:text-4xl font-bold font-heading text-zinc-50">Anime</h1>
        </div>
        <Link to="/anime/all" className="text-sm text-rose-400 hover:text-rose-300 flex items-center gap-1" data-testid="anime-view-all">
          <Film size={14} /> Toate episoadele Anime
        </Link>
      </header>

      <div className="relative mb-6 max-w-xl" data-testid="anime-search-wrap">
        <Search className="absolute left-3 top-1/2 -translate-y-1/2 text-zinc-500" size={16} />
        <input
          type="text"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder="Caută serie Anime după nume…"
          className="w-full bg-zinc-900 border border-zinc-800 focus:border-rose-500/60 focus:outline-none text-zinc-100 pl-9 pr-3 py-2 rounded-md text-sm"
          data-testid="anime-search-input"
        />
      </div>

      {loading && <p className="text-zinc-500 text-center py-12">Se încarcă…</p>}
      {!loading && filtered.length === 0 && (
        <p className="text-zinc-500 text-center py-12" data-testid="anime-empty">
          {series.length === 0
            ? "Nu există încă serii Anime. Un admin le poate crea din Panou Admin → Serii Anime."
            : `Niciun rezultat pentru „${search}".`}
        </p>
      )}
      {!loading && filtered.length > 0 && (
        <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 gap-3 sm:gap-4" data-testid="anime-grid">
          {pageItems.map((s) => (
            <Link key={s.id} to={`/anime/series/${s.slug || s.id}`} className="group block" data-testid={`anime-poster-${s.slug || s.id}`}>
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
      {!loading && totalPages > 1 && (
        <div className="mt-8" data-testid="anime-pagination">
          <Pagination currentPage={page} totalPages={totalPages} onPageChange={handlePageChange} />
        </div>
      )}
    </div>
  );
}
