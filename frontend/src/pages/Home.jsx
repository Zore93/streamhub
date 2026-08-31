import React, { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { Flame, Clock, Smartphone, ChevronRight, Film } from "lucide-react";
import api from "@/lib/api";
import VideoCard from "@/components/VideoCard";
import { Button } from "@/components/ui/button";
import { useT } from "@/contexts/LanguageContext";

const HOME_LIMIT = 12;

function Section({ title, Icon, videos, seeMoreTo, testId, vertical = false, seeMoreLabel, children }) {
  if (children == null && (!videos || videos.length === 0)) return null;
  // Mobile: 2 columns of cards parallel (per user request) — matches the
  // typical tube-site layout.  Sizes scale up on tablet/desktop.
  const grid = vertical
    ? "grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-6 gap-2 sm:gap-4"
    : "grid grid-cols-2 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-3 sm:gap-6";
  return (
    <section className="mb-12" data-testid={testId}>
      <div className="flex items-center justify-between gap-3 mb-6 flex-wrap">
        <div className="flex items-center gap-3">
          <Icon size={24} className="text-rose-500" />
          <h2 className="text-2xl sm:text-3xl font-semibold tracking-tight text-zinc-50">{title}</h2>
        </div>
        {seeMoreTo && (
          <Link to={seeMoreTo} data-testid={`${testId}-see-more`}>
            <Button variant="ghost" size="sm" className="text-zinc-300 hover:text-rose-300 hover:bg-zinc-800/60 gap-1">
              {seeMoreLabel} <ChevronRight size={14} />
            </Button>
          </Link>
        )}
      </div>
      {children != null ? children : (
        <div className={grid}>
          {videos.map((v) => <VideoCard key={v.id} v={v} vertical={vertical} />)}
        </div>
      )}
    </section>
  );
}

/** Netflix-style horizontal poster row for a Shorts series. */
function SeriesPosterRow({ series, basePath = "/shorts/series" }) {
  return (
    <div className="grid grid-cols-3 sm:grid-cols-4 md:grid-cols-5 lg:grid-cols-6 xl:grid-cols-8 gap-2 sm:gap-3">
      {series.map((s) => (
        <Link
          key={s.id}
          to={`${basePath}/${s.slug || s.id}`}
          className="group block"
          data-testid={`home-series-${s.slug || s.id}`}
        >
          <div className="relative aspect-[2/3] rounded-lg overflow-hidden bg-zinc-900 border border-zinc-800 group-hover:border-zinc-600 transition-colors">
            {s.cover_thumbnail ? (
              <img src={s.cover_thumbnail} alt={s.name} loading="lazy" className="w-full h-full object-cover transition-transform group-hover:scale-105" />
            ) : (
              <div className="w-full h-full flex items-center justify-center text-zinc-700"><Film size={28} /></div>
            )}
            {s.episode_count > 0 && (
              <div className="absolute top-1.5 right-1.5 bg-black/70 backdrop-blur-sm text-zinc-100 text-[10px] font-semibold px-1.5 py-0.5 rounded">
                {s.episode_count} ep
              </div>
            )}
          </div>
          <div className="mt-1.5 text-xs font-semibold text-zinc-100 line-clamp-1">{s.name}</div>
        </Link>
      ))}
    </div>
  );
}

export default function Home() {
  const { t, siteCfg } = useT();
  const [latest, setLatest] = useState([]);
  const [popular, setPopular] = useState([]);
  const [shorts, setShorts] = useState([]);
  const [shortsSeries, setShortsSeries] = useState([]);
  const [dramaShorts, setDramaShorts] = useState([]);
  const [dramaSeries, setDramaSeries] = useState([]);

  useEffect(() => {
    const url = (section, extra = "") =>
      `/videos?section=${section}&limit=${HOME_LIMIT}&kind=video${extra}`;
    api.get(url("latest")).then((r) => setLatest(r.data)).catch(() => {});
    api.get(url("popular")).then((r) => setPopular(r.data)).catch(() => {});
    api
      .get(`/videos?section=latest&limit=${HOME_LIMIT}&kind=short&shorts_category=xxx`)
      .then((r) => setShorts(r.data))
      .catch(() => {});
    api
      .get("/shorts-series?category=xxx")
      .then((r) => setShortsSeries(r.data.slice(0, HOME_LIMIT)))
      .catch(() => {});
    api
      .get(`/videos?section=latest&limit=${HOME_LIMIT}&kind=short&shorts_category=drama`)
      .then((r) => setDramaShorts(r.data))
      .catch(() => {});
    api
      .get("/shorts-series?category=drama")
      .then((r) => setDramaSeries(r.data.slice(0, HOME_LIMIT)))
      .catch(() => {});
  }, []);

  const isEmpty =
    latest.length === 0 &&
    popular.length === 0 &&
    shorts.length === 0 &&
    shortsSeries.length === 0 &&
    dramaShorts.length === 0 &&
    dramaSeries.length === 0;

  const seeMore = t("home.seeMore");
  const heroText = (siteCfg?.home_hero_text || "").trim() || t("site.tagline");

  // Vertical selector — lets the visitor filter home to a single content
  // vertical without leaving the page (useful on mobile where the sidebar
  // is collapsed behind a hamburger).
  const [vertical, setVertical] = useState("all"); // all | videos | xxx | drama
  const tabs = [
    { id: "all",    label: t("home.tab.all")    || "Toate" },
    { id: "videos", label: t("home.tab.videos") || "Videoclipuri" },
    { id: "xxx",    label: t("home.tab.xxx")    || "XXX Shorts" },
    { id: "drama",  label: t("home.tab.drama")  || "Drama Shorts" },
  ];
  const showVideos      = vertical === "all" || vertical === "videos";
  const showXxxShorts   = vertical === "all" || vertical === "xxx";
  const showDramaShorts = vertical === "all" || vertical === "drama";

  return (
    <div data-testid="home-page">
      <header className="mb-6">
        <h1 className="text-sm sm:text-base lg:text-lg font-bold tracking-tight text-zinc-50 font-heading whitespace-pre-line" data-testid="home-hero-text">
          {heroText}
        </h1>
      </header>

      {/* Vertical selector */}
      <div
        role="tablist"
        aria-label="Vertical filter"
        className="flex flex-wrap gap-1 mb-8 bg-zinc-900/60 border border-zinc-800 rounded-full p-1 w-fit"
        data-testid="home-vertical-tabs"
      >
        {tabs.map((tab) => {
          const active = vertical === tab.id;
          return (
            <button
              key={tab.id}
              type="button"
              role="tab"
              aria-selected={active}
              onClick={() => setVertical(tab.id)}
              data-testid={`home-vertical-${tab.id}`}
              className={
                "px-4 py-1.5 rounded-full text-sm font-medium transition-colors " +
                (active
                  ? "bg-rose-600 text-white shadow"
                  : "text-zinc-400 hover:text-zinc-100 hover:bg-zinc-800/60")
              }
            >
              {tab.label}
            </button>
          );
        })}
      </div>

      {isEmpty && (
        <div className="bg-zinc-900/50 border border-zinc-800 rounded-xl p-12 text-center" data-testid="empty-state">
          <h3 className="text-xl font-semibold mb-2">{t("home.empty.title")}</h3>
          <p className="text-zinc-500">{t("home.empty.body")}</p>
        </div>
      )}
      {showVideos && (
        <Section
          title={t("home.latest")}
          Icon={Clock}
          videos={latest}
          seeMoreTo="/all-episodes"
          testId="section-latest"
          seeMoreLabel={seeMore}
        />
      )}
      {showVideos && (
        <Section
          title={t("home.popular")}
          Icon={Flame}
          videos={popular}
          seeMoreTo="/popular"
          testId="section-popular"
          seeMoreLabel={seeMore}
        />
      )}
      {showXxxShorts && (
        <Section
          title={t("home.lastShorts")}
          Icon={Smartphone}
          videos={shorts}
          seeMoreTo="/shorts/all"
          testId="section-shorts"
          vertical
          seeMoreLabel={seeMore}
        />
      )}
      {showXxxShorts && shortsSeries.length > 0 && (
        <Section
          title={t("home.lastShortsSeries")}
          Icon={Film}
          seeMoreTo="/shorts"
          testId="section-shorts-series"
          seeMoreLabel={seeMore}
        >
          <SeriesPosterRow series={shortsSeries} basePath="/shorts/series" />
        </Section>
      )}
      {showDramaShorts && (
        <Section
          title={t("home.lastDramaShorts")}
          Icon={Smartphone}
          videos={dramaShorts}
          seeMoreTo="/drama-shorts/all"
          testId="section-drama-shorts"
          vertical
          seeMoreLabel={seeMore}
        />
      )}
      {showDramaShorts && dramaSeries.length > 0 && (
        <Section
          title={t("home.lastDramaShortsSeries")}
          Icon={Film}
          seeMoreTo="/drama-shorts"
          testId="section-drama-shorts-series"
          seeMoreLabel={seeMore}
        >
          <SeriesPosterRow series={dramaSeries} basePath="/drama-shorts/series" />
        </Section>
      )}
    </div>
  );
}
