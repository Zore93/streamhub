import React, { useEffect, useState } from "react";
import { useParams, Link } from "react-router-dom";
import { Smartphone, ArrowLeft, Film } from "lucide-react";
import api from "@/lib/api";
import VideoCard from "@/components/VideoCard";

/**
 * Detail page for one Shorts Series — /shorts/series/:slug.
 * Renders the cover + description header, then the episodes grid
 * in the order returned by the backend (position asc, then created_at).
 */
export default function ShortsSeriesDetail() {
  const { slug } = useParams();
  const [series, setSeries] = useState(null);
  const [loading, setLoading] = useState(true);
  const [notFound, setNotFound] = useState(false);

  useEffect(() => {
    setLoading(true);
    api.get(`/shorts-series/${slug}`)
      .then((r) => setSeries(r.data))
      .catch(() => setNotFound(true))
      .finally(() => setLoading(false));
  }, [slug]);

  if (loading) {
    return <p className="text-zinc-500 text-center py-12" data-testid="series-loading">Se încarcă…</p>;
  }

  if (notFound || !series) {
    return (
      <div className="text-center py-16" data-testid="series-not-found">
        <p className="text-zinc-500 mb-4">Această serie nu există sau a fost ștearsă.</p>
        <Link to="/shorts" className="text-rose-400 hover:text-rose-300">← Înapoi la Shorts</Link>
      </div>
    );
  }

  const episodes = series.episodes || [];

  return (
    <div data-testid="page-series-detail">
      <Link
        to="/shorts"
        className="inline-flex items-center gap-1 text-sm text-zinc-400 hover:text-zinc-200 mb-4"
        data-testid="series-back-link"
      >
        <ArrowLeft size={14} /> Înapoi la Shorts
      </Link>

      <header className="flex flex-col sm:flex-row gap-5 mb-8">
        {series.cover_thumbnail && (
          <img
            src={series.cover_thumbnail}
            alt={series.name}
            className="w-44 aspect-[2/3] object-cover rounded-lg border border-zinc-800 shrink-0"
          />
        )}
        <div className="flex-1 min-w-0">
          <div className="inline-flex items-center gap-2 text-xs uppercase tracking-widest text-rose-400 mb-2">
            <Smartphone size={12} /> Serial Shorts
          </div>
          <h1 className="text-3xl sm:text-4xl font-bold font-heading text-zinc-50 mb-2" data-testid="series-title">
            {series.name}
          </h1>
          {series.description && (
            <p className="text-zinc-400 mb-3 whitespace-pre-line">{series.description}</p>
          )}
          {series.tags?.length > 0 && (
            <div className="flex flex-wrap gap-1.5 mb-2">
              {series.tags.map((tag) => (
                <span key={tag} className="text-[11px] px-2 py-0.5 rounded-full bg-zinc-900 border border-zinc-800 text-zinc-400">
                  {tag}
                </span>
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
        <p className="text-zinc-500 text-center py-12" data-testid="series-no-episodes">
          Nu există încă episoade în acest serial.
        </p>
      ) : (
        <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 gap-2 sm:gap-4" data-testid="series-episodes-grid">
          {episodes.map((v, i) => (
            <div key={v.id} className="relative">
              <div className="absolute top-2 left-2 z-10 bg-black/70 backdrop-blur-sm text-white text-[11px] font-bold px-1.5 py-0.5 rounded">
                Ep {i + 1}
              </div>
              <VideoCard v={v} vertical />
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
