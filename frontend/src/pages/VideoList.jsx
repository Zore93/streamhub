import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useParams, useNavigate, useLocation } from "react-router-dom";
import { Flame, Shuffle, Smartphone, ListVideo, Search, Filter, Crown, Sparkles, X } from "lucide-react";
import api from "@/lib/api";
import VideoCard from "@/components/VideoCard";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import Pagination from "@/components/Pagination";
import { useT } from "@/contexts/LanguageContext";
import { categoryLabel } from "@/i18n";

const PAGE_SIZE = 24;
const MAX_CATEGORIES = 2;

/**
 * Generic listing page used by /popular, /discover, /shorts, /all-episodes.
 * Discover variant additionally exposes a search bar + tier/category filters.
 * Pagination is numbered (1..N) and reflected in the URL path: `/popular/page/2`.
 */
export default function VideoList({ variant }) {
  const { t, lang } = useT();
  const params = useParams();
  const navigate = useNavigate();
  const location = useLocation();
  const currentPage = Math.max(1, parseInt(params.page, 10) || 1);

  const cfg = useMemo(() => {
    switch (variant) {
      case "popular":
        return { section: "popular", kind: null, titleKey: "page.popular", Icon: Flame, base: "/popular" };
      case "discover":
        return { section: "random", kind: null, titleKey: "page.discover", Icon: Shuffle, base: "/discover" };
      case "shorts":
        return { section: "latest", kind: "short", titleKey: "page.shorts", Icon: Smartphone, base: "/shorts" };
      case "all":
      default:
        return { section: "latest", kind: null, titleKey: "page.allEpisodes", Icon: ListVideo, base: "/all-episodes" };
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
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(false);
  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE));

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

  const buildParams = useCallback(() => {
    const p = new URLSearchParams();
    if (cfg.kind) p.set("kind", cfg.kind);
    if (isDiscover) {
      if (debouncedSearch) p.set("q", debouncedSearch);
      if (accessTier) p.set("access_tier", accessTier);
      if (selectedCats.length > 0) {
        p.set("category_ids", selectedCats.slice(0, MAX_CATEGORIES).join(","));
      }
    }
    return p;
  }, [cfg.kind, isDiscover, debouncedSearch, accessTier, selectedCats]);

  const fetchPage = useCallback(async (page) => {
    setLoading(true);
    try {
      const skip = (page - 1) * PAGE_SIZE;
      const params = buildParams();
      params.set("section", cfg.section);
      params.set("limit", String(PAGE_SIZE));
      params.set("skip", String(skip));
      // Fire list + count in parallel.
      const countParams = buildParams();
      const [{ data: list }, { data: counted }] = await Promise.all([
        api.get(`/videos?${params.toString()}`),
        api.get(`/videos/count?${countParams.toString()}`),
      ]);
      setItems(list);
      setTotal(counted.count || 0);
    } finally {
      setLoading(false);
    }
  }, [cfg.section, buildParams]);

  // Reload whenever the page in the URL changes
  useEffect(() => {
    fetchPage(currentPage);
    window.scrollTo({ top: 0, behavior: "smooth" });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [currentPage, variant]);

  // Discover: reload (and reset to page 1) whenever filters change
  const filterKey = `${debouncedSearch}|${accessTier}|${selectedCats.join(",")}`;
  const lastFilterKey = useRef("");
  useEffect(() => {
    if (!isDiscover) return;
    if (lastFilterKey.current === filterKey) return;
    if (lastFilterKey.current !== "") {
      // Filters changed → navigate back to page 1
      if (currentPage !== 1) {
        navigate(cfg.base, { replace: false });
      } else {
        fetchPage(1);
      }
    }
    lastFilterKey.current = filterKey;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [filterKey]);

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

  const buildHref = useCallback((p) => {
    if (p <= 1) return cfg.base + location.search;
    return `${cfg.base}/page/${p}${location.search}`;
  }, [cfg.base, location.search]);

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
                          {categoryLabel(c, lang)}
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
            ? "grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 gap-2 sm:gap-4"
            : "grid grid-cols-2 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-3 sm:gap-6"
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

      <Pagination
        currentPage={currentPage}
        totalPages={totalPages}
        buildHref={buildHref}
      />
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
