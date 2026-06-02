import React, { useCallback, useEffect, useMemo, useState } from "react";
import { Flame, Shuffle, Smartphone, ListVideo } from "lucide-react";
import api from "@/lib/api";
import VideoCard from "@/components/VideoCard";
import { Button } from "@/components/ui/button";
import { useT } from "@/contexts/LanguageContext";

const PAGE_SIZE = 24;

/**
 * Generic listing page used by /popular, /discover, /shorts, /all-episodes.
 * Pagination is "load more" style (skip/limit) to keep the implementation tiny.
 */
export default function VideoList({ variant }) {
  const { t } = useT();

  const cfg = useMemo(() => {
    switch (variant) {
      case "popular":
        return { section: "popular", kind: null, titleKey: "page.popular", Icon: Flame };
      case "discover":
        return { section: "random", kind: null, titleKey: "page.discover", Icon: Shuffle };
      case "shorts":
        return { section: "latest", kind: "short", titleKey: "page.shorts", Icon: Smartphone };
      case "all":
      default:
        return { section: "latest", kind: null, titleKey: "page.allEpisodes", Icon: ListVideo };
    }
  }, [variant]);

  const [items, setItems] = useState([]);
  const [skip, setSkip] = useState(0);
  const [done, setDone] = useState(false);
  const [loading, setLoading] = useState(false);

  // Reset whenever variant changes (route swap)
  useEffect(() => {
    setItems([]); setSkip(0); setDone(false);
  }, [variant]);

  const fetchPage = useCallback(async (currentSkip) => {
    setLoading(true);
    try {
      const params = new URLSearchParams({
        section: cfg.section,
        limit: String(PAGE_SIZE),
        skip: String(currentSkip),
      });
      if (cfg.kind) params.set("kind", cfg.kind);
      const { data } = await api.get(`/videos?${params.toString()}`);
      setItems((prev) => {
        // Random pages can repeat — dedupe by id.
        const seen = new Set(prev.map((v) => v.id));
        const merged = [...prev];
        for (const v of data) if (!seen.has(v.id)) merged.push(v);
        return merged;
      });
      if (data.length < PAGE_SIZE) setDone(true);
    } finally {
      setLoading(false);
    }
  }, [cfg.section, cfg.kind]);

  // Initial load (and after variant reset)
  useEffect(() => {
    if (items.length === 0 && !done) fetchPage(0);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [variant]);

  const loadMore = async () => {
    const next = skip + PAGE_SIZE;
    setSkip(next);
    await fetchPage(next);
  };

  const Icon = cfg.Icon;
  const isShorts = variant === "shorts";

  return (
    <div data-testid={`page-${variant}`}>
      <header className="flex items-center gap-3 mb-8">
        <Icon size={26} className="text-rose-500" />
        <h1 className="text-3xl sm:text-4xl font-bold font-heading text-zinc-50">{t(cfg.titleKey)}</h1>
      </header>

      <div
        className={
          isShorts
            ? "grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 gap-4"
            : "grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-6"
        }
      >
        {items.map((v) => <VideoCard key={v.id} v={v} vertical={isShorts} />)}
      </div>

      {items.length === 0 && !loading && (
        <p className="text-zinc-500 text-center py-12">{t("page.empty")}</p>
      )}

      <div className="flex justify-center mt-10">
        {!done && items.length > 0 && (
          <Button
            onClick={loadMore}
            variant="outline"
            disabled={loading}
            className="border-zinc-700 hover:bg-zinc-800"
            data-testid="load-more"
          >
            {loading ? t("page.loading") : t("page.loadMore")}
          </Button>
        )}
      </div>
    </div>
  );
}
