import React, { useEffect, useMemo, useState } from "react";
import { useParams, Link, useSearchParams } from "react-router-dom";
import { Film, Search } from "lucide-react";
import api from "@/lib/api";
import VideoCard from "@/components/VideoCard";

/**
 * /filme-rosub — full-length RoSub films.
 * Layout: a horizontal row of category text-links at the top, then a
 * grid of film cards underneath. Also handles /filme-rosub/{cat_slug}
 * (routed here so the category text is the ONLY thing that changes on
 * click, keeping the perceived nav in-place).
 */
export default function FilmeRoSub() {
  const params = useParams();
  const [searchParams] = useSearchParams();
  const catRef = params.catSlug || null;

  const [categories, setCategories] = useState([]);
  const [films, setFilms] = useState([]);
  const [activeCat, setActiveCat] = useState(null);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState("");

  const visibleFilms = useMemo(() => {
    const q = search.trim().toLowerCase();
    if (!q) return films;
    return films.filter((v) =>
      (v.title || "").toLowerCase().includes(q) ||
      (v.tags || []).some((t) => (t || "").toLowerCase().includes(q))
    );
  }, [films, search]);

  useEffect(() => {
    api.get("/film-categories").then((r) => setCategories(r.data)).catch(() => {});
  }, []);

  useEffect(() => {
    if (!catRef) { setActiveCat(null); return; }
    api.get(`/film-categories/${catRef}`).then((r) => setActiveCat(r.data)).catch(() => setActiveCat(null));
  }, [catRef]);

  useEffect(() => {
    setLoading(true);
    const url = catRef ? `/videos/filme?category_id=${encodeURIComponent(catRef)}` : "/videos/filme";
    api.get(url).then((r) => setFilms(r.data?.items || []))
      .catch(() => setFilms([]))
      .finally(() => setLoading(false));
  }, [catRef, searchParams]);

  return (
    <div data-testid="page-filme-rosub">
      <header className="flex items-center gap-3 mb-4">
        <Film size={26} className="text-rose-500" />
        <h1 className="text-3xl sm:text-4xl font-bold font-heading text-zinc-50">
          {activeCat ? `Filme RoSub — ${activeCat.name}` : "Filme RoSub"}
        </h1>
      </header>

      {/* Categories row — text-only chips, no images */}
      {categories.length > 0 && (
        <nav
          className="mb-6 pb-2 border-b border-zinc-800 flex flex-wrap gap-x-4 gap-y-2 items-center text-sm"
          data-testid="filme-categories-row"
        >
          <Link
            to="/filme-rosub"
            className={`hover:text-rose-400 transition-colors ${!activeCat ? "text-rose-400 font-semibold" : "text-zinc-400"}`}
            data-testid="filme-cat-all"
          >
            Toate
          </Link>
          {categories.map((c) => (
            <Link
              key={c.id}
              to={`/filme-rosub/${c.slug}`}
              className={`hover:text-rose-400 transition-colors ${activeCat?.id === c.id ? "text-rose-400 font-semibold" : "text-zinc-400"}`}
              data-testid={`filme-cat-${c.slug}`}
              title={c.description || undefined}
            >
              {c.name}
              {c.film_count ? <span className="ml-1 text-[11px] text-zinc-600">({c.film_count})</span> : null}
            </Link>
          ))}
        </nav>
      )}
      {categories.length === 0 && (
        <p className="text-xs text-zinc-500 mb-4" data-testid="filme-no-categories">
          Un admin poate crea categorii din Panou Admin → Categorii Filme.
        </p>
      )}

      <div className="relative mb-6 max-w-xl" data-testid="filme-search-wrap">
        <Search className="absolute left-3 top-1/2 -translate-y-1/2 text-zinc-500" size={16} />
        <input
          type="text"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder="Caută film după titlu…"
          className="w-full bg-zinc-900 border border-zinc-800 focus:border-rose-500/60 focus:outline-none text-zinc-100 pl-9 pr-3 py-2 rounded-md text-sm"
          data-testid="filme-search-input"
        />
      </div>

      {/* Films grid */}
      {loading && <p className="text-zinc-500 text-center py-12">Se încarcă…</p>}
      {!loading && visibleFilms.length === 0 && (
        <p className="text-zinc-500 text-center py-12" data-testid="filme-empty">
          {search
            ? `Niciun rezultat pentru „${search}".`
            : activeCat
              ? `Nu există filme în categoria "${activeCat.name}" încă.`
              : "Nu există filme RoSub încă. Adaugă unul din /upload → Este film RoSub."}
        </p>
      )}
      {!loading && visibleFilms.length > 0 && (
        <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-4" data-testid="filme-grid">
          {visibleFilms.map((v) => <VideoCard key={v.id} v={v} />)}
        </div>
      )}
    </div>
  );
}
