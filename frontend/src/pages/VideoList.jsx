import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Flame, Shuffle, Smartphone, ListVideo, Search, Filter, Crown, Sparkles, X } from "lucide-react";
import api from "@/lib/api";
import VideoCard from "@/components/VideoCard";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { useT } from "@/contexts/LanguageContext";

const PAGE_SIZE = 24;
const MAX_CATEGORIES = 2;

/**
 * Generic listing page used by /popular, /discover, /shorts, /all-episodes.
 * Discover variant additionally exposes a search bar + tier/category filters.
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

  const isDiscover = variant === "discover";

  // Filter state (only used by Discover)
  const [search, setSearch] = useState("");
  const [debouncedSearch, setDebouncedSearch] = useState("");
  const [accessTier, setAccessTier] = useState("");  // "" | "free" | "pro"
  const [selectedCats, setSelectedCats] = useState([]); // category ids
  const [cats, setCats] = useState([]);
  const [showFilters, setShowFilters] = useState(false);

  // Listing state
  const [items, setItems] = useState([]);
  const [skip, setSkip] = useState(0);
  const [done, setDone] = useState(false);
  const [loading, setLoading] = useState(false);

  // Reset whenever variant changes (route swap)
  useEffect(() => {
    setItems([]); setSkip(0); setDone(false);
  }, [variant]);

  // Load categories for the Discover filter pills
  useEffect(() => {
    if (!isDiscover) return;
    api.get("/categories").then((r) => setCats(r.data)).catch(() => {});
  }, [isDiscover]);

  // Debounce search input → debouncedSearch (350 ms)
  useEffect(() => {
    if (!isDiscover) return;
    const id = setTimeout(() => setDebouncedSearch(search.trim()), 350);
    return () => clearTimeout(id);
  }, [search, isDiscover]);

  const fetchPage = useCallback(async (currentSkip) => {
    setLoading(true);
    try {
      const params = new URLSearchParams({
        section: cfg.section,
        limit: String(PAGE_SIZE),
        skip: String(currentSkip),
      });
      if (cfg.kind) params.set("kind", cfg.kind);
      if (isDiscover) {
        if (debouncedSearch) params.set("q", debouncedSearch);
        if (accessTier) params.set("access_tier", accessTier);
        if (selectedCats.length > 0) {
          params.set("category_ids", selectedCats.slice(0, MAX_CATEGORIES).join(","));
        }
      }
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
  }, [cfg.section, cfg.kind, isDiscover, debouncedSearch, accessTier, selectedCats]);

  // Initial load (and after variant reset) for non-discover routes
  useEffect(() => {
    if (isDiscover) return;
    if (items.length === 0 && !done) fetchPage(0);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [variant]);

  // Discover: reload whenever filters change.  Reset pagination first.
  const filterKey = `${debouncedSearch}|${accessTier}|${selectedCats.join(",")}`;
  const lastFilterKey = useRef("");
  useEffect(() => {
    if (!isDiscover) return;
    if (lastFilterKey.current === filterKey) return;
    lastFilterKey.current = filterKey;
    setItems([]); setSkip(0); setDone(false);
    fetchPage(0);
  }, [isDiscover, filterKey, fetchPage]);

  const loadMore = async () => {
    const next = skip + PAGE_SIZE;
    setSkip(next);
    await fetchPage(next);
  };

  const toggleCat = (id) => {
    setSelectedCats((prev) => {
      if (prev.includes(id)) return prev.filter((x) => x !== id);
      if (prev.length >= MAX_CATEGORIES) return prev;  // hard cap
      return [...prev, id];
    });
  };

  const clearAll = () => {
    setSearch(""); setDebouncedSearch(""); setAccessTier(""); setSelectedCats([]);
  };

  const Icon = cfg.Icon;
  const isShorts = variant === "shorts";
  const activeFilterCount =
    (accessTier ? 1 : 0) + selectedCats.length + (debouncedSearch ? 1 : 0);

  return (
    <div data-testid={`page-${variant}`}>
      <header className="flex items-center gap-3 mb-6">
        <Icon size={26} className="text-rose-500" />
        <h1 className="text-3xl sm:text-4xl font-bold font-heading text-zinc-50">{t(cfg.titleKey)}</h1>
      </header>

      {isDiscover && (
        <div className="mb-8 space-y-4" data-testid="discover-filters">
          {/* Search bar */}
          <div className="relative">
            <Search size={16} className="absolute left-3 top-1/2 -translate-y-1/2 text-zinc-500 pointer-events-none" />
            <Input
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder={t("discover.searchPlaceholder")}
              className="bg-zinc-900 border-zinc-800 pl-10 pr-10 h-11 text-base"
              data-testid="discover-search"
            />
            {search && (
              <button
                type="button"
                onClick={() => setSearch("")}
                className="absolute right-3 top-1/2 -translate-y-1/2 text-zinc-500 hover:text-zinc-200"
                aria-label="Clear search"
                data-testid="discover-search-clear"
              >
                <X size={14} />
              </button>
            )}
          </div>

          {/* Filter toggle + active count */}
          <div className="flex items-center justify-between flex-wrap gap-2">
            <button
              type="button"
              onClick={() => setShowFilters((s) => !s)}
              className="inline-flex items-center gap-2 text-sm text-zinc-300 hover:text-zinc-50 transition-colors"
              data-testid="discover-toggle-filters"
            >
              <Filter size={14} />
              <span>{t("discover.filters")}</span>
              {activeFilterCount > 0 && (
                <span className="bg-rose-500 text-white text-[10px] font-bold rounded-full px-2 py-0.5">
                  {activeFilterCount}
                </span>
              )}
            </button>
            {activeFilterCount > 0 && (
              <button
                type="button"
                onClick={clearAll}
                className="text-xs text-zinc-500 hover:text-rose-400"
                data-testid="discover-clear-all"
              >
                {t("discover.clearAll")}
              </button>
            )}
          </div>

          {/* Filter panel */}
          {showFilters && (
            <div className="bg-zinc-900/70 border border-zinc-800 rounded-lg p-4 space-y-4" data-testid="discover-filter-panel">
              {/* Tier */}
              <div>
                <div className="text-xs uppercase tracking-widest text-zinc-500 mb-2">{t("discover.tier")}</div>
                <div className="flex flex-wrap gap-2">
                  <FilterPill
                    active={accessTier === ""}
                    onClick={() => setAccessTier("")}
                    icon={Sparkles}
                    testId="tier-all"
                  >
                    {t("discover.tierAll")}
                  </FilterPill>
                  <FilterPill
                    active={accessTier === "free"}
                    onClick={() => setAccessTier(accessTier === "free" ? "" : "free")}
                    testId="tier-free"
                  >
                    {t("discover.tierFree")}
                  </FilterPill>
                  <FilterPill
                    active={accessTier === "pro"}
                    onClick={() => setAccessTier(accessTier === "pro" ? "" : "pro")}
                    icon={Crown}
                    testId="tier-pro"
                  >
                    {t("discover.tierPro")}
                  </FilterPill>
                </div>
              </div>

              {/* Categories */}
              {cats.length > 0 && (
                <div>
                  <div className="flex items-center justify-between mb-2">
                    <div className="text-xs uppercase tracking-widest text-zinc-500">
                      {t("discover.categories")}
                    </div>
                    <div className="text-xs text-zinc-500">
                      {selectedCats.length}/{MAX_CATEGORIES}
                    </div>
                  </div>
                  <div className="flex flex-wrap gap-2">
                    {cats.map((c) => {
                      const active = selectedCats.includes(c.id);
                      const disabled = !active && selectedCats.length >= MAX_CATEGORIES;
                      return (
                        <FilterPill
                          key={c.id}
                          active={active}
                          disabled={disabled}
                          onClick={() => toggleCat(c.id)}
                          testId={`cat-${c.slug || c.id}`}
                        >
                          {c.name}
                        </FilterPill>
                      );
                    })}
                  </div>
                </div>
              )}
            </div>
          )}
        </div>
      )}

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
        <p className="text-zinc-500 text-center py-12">
          {isDiscover && activeFilterCount > 0
            ? t("discover.noResults")
            : t("page.empty")}
        </p>
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

function FilterPill({ active, disabled, onClick, icon: Icon, children, testId }) {
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      data-testid={`discover-pill-${testId}`}
      className={`inline-flex items-center gap-1.5 px-3 py-1.5 text-sm rounded-full border transition-colors ${
        active
          ? "bg-rose-500 border-rose-500 text-white"
          : disabled
            ? "bg-zinc-950 border-zinc-800 text-zinc-600 cursor-not-allowed opacity-60"
            : "bg-zinc-950 border-zinc-800 text-zinc-300 hover:border-zinc-600 hover:text-zinc-100"
      }`}
    >
      {Icon && <Icon size={12} />}
      <span>{children}</span>
    </button>
  );
}
