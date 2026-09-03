import React, { useEffect, useState } from "react";
import { useParams, Link } from "react-router-dom";
import { ArrowLeft, Tv, Film } from "lucide-react";
import api from "@/lib/api";
import VideoCard from "@/components/VideoCard";

/** /anime/series/:slug — series detail with landscape episodes list. */
export default function AnimeSeriesDetail() {
  const { slug } = useParams();
  const [series, setSeries] = useState(null);
  const [loading, setLoading] = useState(true);
  const [notFound, setNotFound] = useState(false);

  useEffect(() => {
    setLoading(true);
    api.get(`/anime-series/${slug}`).then((r) => setSeries(r.data)).catch(() => setNotFound(true)).finally(() => setLoading(false));
  }, [slug]);

  if (loading) return <p className="text-zinc-500 text-center py-12">Se încarcă…</p>;
  if (notFound || !series) {
    return (
      <div className="text-center py-16" data-testid="anime-series-not-found">
        <p className="text-zinc-500 mb-4">Această serie nu există sau a fost ștearsă.</p>
        <Link to="/anime" className="text-rose-400 hover:text-rose-300">← Înapoi la Anime</Link>
      </div>
    );
  }
  const episodes = series.episodes || [];

  return (
    <div data-testid="page-anime-series-detail">
      <Link to="/anime" className="inline-flex items-center gap-1 text-sm text-zinc-400 hover:text-zinc-200 mb-4" data-testid="anime-series-back-link">
        <ArrowLeft size={14} /> Înapoi la Anime
      </Link>
      <header className="flex flex-col sm:flex-row gap-5 mb-8">
        {series.cover_thumbnail && (
          <img src={series.cover_thumbnail} alt={series.name} className="w-44 aspect-[2/3] object-cover rounded-lg border border-zinc-800 shrink-0" />
        )}
        <div className="flex-1 min-w-0">
          <div className="inline-flex items-center gap-2 text-xs uppercase tracking-widest text-rose-400 mb-2">
            <Tv size={12} /> Serial Anime
          </div>
          <h1 className="text-3xl sm:text-4xl font-bold font-heading text-zinc-50 mb-2" data-testid="anime-series-title">{series.name}</h1>
          {series.description && <p className="text-zinc-400 mb-3 whitespace-pre-line">{series.description}</p>}
          {series.tags?.length > 0 && (
            <div className="flex flex-wrap gap-1.5 mb-2">
              {series.tags.map((tag) => (
                <span key={tag} className="text-[11px] px-2 py-0.5 rounded-full bg-zinc-900 border border-zinc-800 text-zinc-400">{tag}</span>
              ))}
            </div>
          )}
          <div className="text-sm text-zinc-500">
            <Film size={12} className="inline mr-1" />
            {series.episode_count} {series.episode_count === 1 ? "episod" : "episoade"}
          </div>
        </div>
      </header>

      {episodes.length === 0 ? (
        <p className="text-zinc-500 text-center py-12" data-testid="anime-series-no-episodes">Nu există încă episoade în acest serial.</p>
      ) : (
        <div className="grid grid-cols-2 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-3 sm:gap-6" data-testid="anime-series-episodes-grid">
          {episodes.map((v, i) => (
            <div key={v.id} className="relative">
              <div className="absolute top-2 left-2 z-10 bg-black/70 backdrop-blur-sm text-white text-[11px] font-bold px-1.5 py-0.5 rounded">Ep {i + 1}</div>
              <VideoCard v={v} />
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
