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

/** /anime/:slug — series detail: grid of seasons (falls back to flat episode
 *  list for legacy series that don't have seasons yet). */
export default function AnimeSeriesDetail() {
  const { slug } = useParams();
  const [series, setSeries] = useState(null);
  const [loading, setLoading] = useState(true);
  const [notFound, setNotFound] = useState(false);

  useEffect(() => {
    setLoading(true);
    api.get(`/anime-series/${slug}`).then((r) => setSeries(r.data))
      .catch(() => setNotFound(true))
      .finally(() => setLoading(false));
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
  const seasons = series.seasons || [];
  const episodes = series.episodes || [];
  const orphanEpisodes = episodes.filter((e) => !e.anime_season_id);

  return (
    <div data-testid="page-anime-series-detail">
      <Link
        to="/anime"
        className="inline-flex items-center gap-1 text-sm text-zinc-400 hover:text-zinc-200 mb-4"
        data-testid="anime-series-back-link"
      >
        <ArrowLeft size={14} /> Înapoi la Anime
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
            <Tv size={12} /> Serial Anime
          </div>
          <h1 className="text-3xl sm:text-4xl font-bold font-heading text-zinc-50 mb-2" data-testid="anime-series-title">{series.name}</h1>
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
            {seasons.length > 0 && (
              <span className="mr-4">
                <Tv size={12} className="inline mr-1" />
                {seasons.length} {seasons.length === 1 ? "sezon" : "sezoane"}
              </span>
            )}
            <Film size={12} className="inline mr-1" />
            {series.episode_count} {series.episode_count === 1 ? "episod" : "episoade"}
          </div>
        </div>
      </header>

      {seasons.length > 0 ? (
        <>
          <h2 className="text-lg font-semibold text-zinc-200 mb-4">Sezoane</h2>
          <div
            className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 gap-3 sm:gap-4 mb-10"
            data-testid="anime-series-seasons-grid"
          >
            {seasons.map((se) => {
              const typeLabel = SEASON_TYPE_LABEL[se.season_type] || "Sezon";
              return (
                <Link
                  key={se.id}
                  to={`/anime/series/${series.slug}/${se.slug || se.id}`}
                  className="group block"
                  data-testid={`anime-season-card-${se.slug || se.id}`}
                >
                  <div className="relative aspect-[2/3] rounded-lg overflow-hidden bg-zinc-900 border border-zinc-800 group-hover:border-zinc-600 transition-colors">
                    {se.cover_thumbnail ? (
                      <img
                        src={se.cover_thumbnail}
                        alt={se.title}
                        loading="lazy"
                        className="w-full h-full object-cover transition-transform group-hover:scale-105"
                      />
                    ) : series.cover_thumbnail ? (
                      <img
                        src={series.cover_thumbnail}
                        alt={se.title}
                        loading="lazy"
                        className="w-full h-full object-cover opacity-70"
                      />
                    ) : (
                      <div className="w-full h-full flex items-center justify-center text-zinc-700">
                        <Film size={40} />
                      </div>
                    )}
                    <div className="absolute top-1.5 left-1.5 bg-rose-600/90 text-white text-[10px] font-bold uppercase tracking-wider px-1.5 py-0.5 rounded">
                      {typeLabel}
                    </div>
                    {se.episode_count > 0 && (
                      <div className="absolute top-1.5 right-1.5 bg-black/70 backdrop-blur-sm text-zinc-100 text-[11px] font-semibold px-1.5 py-0.5 rounded">
                        {se.episode_count} ep
                      </div>
                    )}
                    {se.year && (
                      <div className="absolute bottom-1.5 right-1.5 bg-black/70 backdrop-blur-sm text-zinc-100 text-[10px] font-medium px-1.5 py-0.5 rounded flex items-center gap-1">
                        <Calendar size={10} /> {se.year}
                      </div>
                    )}
                  </div>
                  <div className="mt-2">
                    <div className="text-sm font-semibold text-zinc-100 line-clamp-1">{se.title}</div>
                    {se.description && (
                      <div className="text-[11px] text-zinc-500 line-clamp-1 mt-0.5">{se.description}</div>
                    )}
                  </div>
                </Link>
              );
            })}
          </div>
        </>
      ) : null}

      {orphanEpisodes.length > 0 && (
        <>
          {seasons.length > 0 && (
            <h2 className="text-lg font-semibold text-zinc-200 mb-4">Episoade fără sezon</h2>
          )}
          {episodes.length === 0 ? null : (
            <div
              className="grid grid-cols-2 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-3 sm:gap-6"
              data-testid="anime-series-episodes-grid"
            >
              {orphanEpisodes.map((v, i) => (
                <div key={v.id} className="relative">
                  <div className="absolute top-2 left-2 z-10 bg-black/70 backdrop-blur-sm text-white text-[11px] font-bold px-1.5 py-0.5 rounded">
                    Ep {i + 1}
                  </div>
                  <VideoCard v={v} />
                </div>
              ))}
            </div>
          )}
        </>
      )}

      {seasons.length === 0 && orphanEpisodes.length === 0 && (
        <p
          className="text-zinc-500 text-center py-12"
          data-testid="anime-series-empty"
        >
          Nu există încă sezoane sau episoade. Un admin poate adăuga sezoane
          din Panou Admin → Serii Anime.
        </p>
      )}
    </div>
  );
}
