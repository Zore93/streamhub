import React, { useEffect, useState } from "react";
import { useParams, Link } from "react-router-dom";
import { ArrowLeft, Tv, Film, Calendar } from "lucide-react";
import api from "@/lib/api";
import VideoCard from "@/components/VideoCard";

const SEASON_TYPE_LABEL = {
  season: "Sezon",
  ova: "OVA",
  movie: "Film",
  special: "Special",
};

/** /anime/:seriesSlug/:seasonSlug — season detail with episodes list. */
export default function AnimeSeasonDetail() {
  const { seriesSlug, seasonSlug } = useParams();
  const [season, setSeason] = useState(null);
  const [loading, setLoading] = useState(true);
  const [notFound, setNotFound] = useState(false);

  useEffect(() => {
    setLoading(true);
    api.get(`/anime-series/${seriesSlug}/seasons/${seasonSlug}`)
      .then((r) => setSeason(r.data))
      .catch(() => setNotFound(true))
      .finally(() => setLoading(false));
  }, [seriesSlug, seasonSlug]);

  if (loading) return <p className="text-zinc-500 text-center py-12">Se încarcă…</p>;
  if (notFound || !season) {
    return (
      <div className="text-center py-16" data-testid="anime-season-not-found">
        <p className="text-zinc-500 mb-4">Acest sezon nu există sau a fost șters.</p>
        <Link to={`/anime/${seriesSlug}`} className="text-rose-400 hover:text-rose-300">← Înapoi la serie</Link>
      </div>
    );
  }
  const episodes = season.episodes || [];
  const typeLabel = SEASON_TYPE_LABEL[season.season_type] || "Sezon";

  return (
    <div data-testid="page-anime-season-detail">
      <Link
        to={`/anime/series/${season.series?.slug || seriesSlug}`}
        className="inline-flex items-center gap-1 text-sm text-zinc-400 hover:text-zinc-200 mb-4"
        data-testid="anime-season-back-link"
      >
        <ArrowLeft size={14} /> Înapoi la {season.series?.name || "serie"}
      </Link>
      <header className="flex flex-col sm:flex-row gap-5 mb-8">
        {(season.cover_thumbnail || season.series?.cover_thumbnail) && (
          <img
            src={season.cover_thumbnail || season.series?.cover_thumbnail}
            alt={season.title}
            className="w-44 aspect-[2/3] object-cover rounded-lg border border-zinc-800 shrink-0"
          />
        )}
        <div className="flex-1 min-w-0">
          <div className="inline-flex items-center gap-2 text-xs uppercase tracking-widest text-rose-400 mb-2">
            <Tv size={12} /> {typeLabel}
          </div>
          <h1
            className="text-3xl sm:text-4xl font-bold font-heading text-zinc-50 mb-2"
            data-testid="anime-season-title"
          >
            {season.series?.name} — {season.title}
          </h1>
          {season.description && (
            <p className="text-zinc-400 mb-3 whitespace-pre-line">{season.description}</p>
          )}
          <div className="flex items-center gap-4 text-sm text-zinc-500 flex-wrap">
            <span>
              <Film size={12} className="inline mr-1" />
              {season.episode_count} {season.episode_count === 1 ? "episod" : "episoade"}
            </span>
            {season.year && (
              <span>
                <Calendar size={12} className="inline mr-1" />
                {season.year}
              </span>
            )}
          </div>
        </div>
      </header>

      {episodes.length === 0 ? (
        <p
          className="text-zinc-500 text-center py-12"
          data-testid="anime-season-no-episodes"
        >
          Nu există încă episoade în acest sezon.
        </p>
      ) : (
        <div
          className="grid grid-cols-2 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-3 sm:gap-6"
          data-testid="anime-season-episodes-grid"
        >
          {episodes.map((v, i) => (
            <div key={v.id} className="relative">
              <div className="absolute top-2 left-2 z-10 bg-black/70 backdrop-blur-sm text-white text-[11px] font-bold px-1.5 py-0.5 rounded">
                Ep {v.anime_series_position || i + 1}
              </div>
              <VideoCard v={v} />
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
