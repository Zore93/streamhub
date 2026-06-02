import React, { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { Flame, Clock, Shuffle, Smartphone, ChevronRight } from "lucide-react";
import api from "@/lib/api";
import VideoCard from "@/components/VideoCard";
import { Button } from "@/components/ui/button";
import { useT } from "@/contexts/LanguageContext";

const HOME_LIMIT = 12;

function Section({ title, Icon, videos, seeMoreTo, testId, vertical = false, seeMoreLabel }) {
  if (!videos || videos.length === 0) return null;
  const grid = vertical
    ? "grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-6 gap-4"
    : "grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-6";
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
      <div className={grid}>
        {videos.map((v) => <VideoCard key={v.id} v={v} vertical={vertical} />)}
      </div>
    </section>
  );
}

export default function Home() {
  const { t } = useT();
  const [latest, setLatest] = useState([]);
  const [popular, setPopular] = useState([]);
  const [random, setRandom] = useState([]);
  const [shorts, setShorts] = useState([]);

  useEffect(() => {
    const url = (section, extra = "") =>
      `/videos?section=${section}&limit=${HOME_LIMIT}&kind=video${extra}`;
    api.get(url("latest")).then((r) => setLatest(r.data)).catch(() => {});
    api.get(url("popular")).then((r) => setPopular(r.data)).catch(() => {});
    api.get(url("random")).then((r) => setRandom(r.data)).catch(() => {});
    api
      .get(`/videos?section=latest&limit=${HOME_LIMIT}&kind=short`)
      .then((r) => setShorts(r.data))
      .catch(() => {});
  }, []);

  const isEmpty =
    latest.length === 0 &&
    popular.length === 0 &&
    random.length === 0 &&
    shorts.length === 0;

  const seeMore = t("home.seeMore");

  return (
    <div data-testid="home-page">
      <header className="mb-10">
        <h1 className="text-3xl sm:text-5xl lg:text-6xl font-bold tracking-tight text-zinc-50 font-heading">
          {t("site.tagline")}
        </h1>
      </header>
      {isEmpty && (
        <div className="bg-zinc-900/50 border border-zinc-800 rounded-xl p-12 text-center" data-testid="empty-state">
          <h3 className="text-xl font-semibold mb-2">{t("home.empty.title")}</h3>
          <p className="text-zinc-500">{t("home.empty.body")}</p>
        </div>
      )}
      <Section
        title={t("home.latest")}
        Icon={Clock}
        videos={latest}
        seeMoreTo="/all-episodes"
        testId="section-latest"
        seeMoreLabel={seeMore}
      />
      <Section
        title={t("home.popular")}
        Icon={Flame}
        videos={popular}
        seeMoreTo="/popular"
        testId="section-popular"
        seeMoreLabel={seeMore}
      />
      <Section
        title={t("home.discover")}
        Icon={Shuffle}
        videos={random}
        seeMoreTo="/discover"
        testId="section-discover"
        seeMoreLabel={seeMore}
      />
      <Section
        title={t("home.lastShorts")}
        Icon={Smartphone}
        videos={shorts}
        seeMoreTo="/shorts"
        testId="section-shorts"
        vertical
        seeMoreLabel={seeMore}
      />
    </div>
  );
}
