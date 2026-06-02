import React, { useCallback, useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import api from "@/lib/api";
import VideoCard from "@/components/VideoCard";
import { Button } from "@/components/ui/button";
import { useT } from "@/contexts/LanguageContext";

const PAGE_SIZE = 24;

export default function Category() {
  const { id } = useParams();
  const { t } = useT();
  const [vids, setVids] = useState([]);
  const [cats, setCats] = useState([]);
  const [skip, setSkip] = useState(0);
  const [done, setDone] = useState(false);
  const [loading, setLoading] = useState(false);

  // Reset on route change
  useEffect(() => {
    setVids([]); setSkip(0); setDone(false);
    api.get("/categories").then((r) => setCats(r.data));
  }, [id]);

  const fetchPage = useCallback(async (currentSkip) => {
    setLoading(true);
    try {
      const { data } = await api.get(`/videos?category_id=${id}&limit=${PAGE_SIZE}&skip=${currentSkip}`);
      setVids((prev) => {
        const seen = new Set(prev.map((v) => v.id));
        const merged = [...prev];
        for (const v of data) if (!seen.has(v.id)) merged.push(v);
        return merged;
      });
      if (data.length < PAGE_SIZE) setDone(true);
    } finally {
      setLoading(false);
    }
  }, [id]);

  useEffect(() => {
    if (vids.length === 0 && !done) fetchPage(0);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id]);

  const loadMore = async () => {
    const next = skip + PAGE_SIZE;
    setSkip(next);
    await fetchPage(next);
  };

  const cat = cats.find((c) => c.id === id);
  return (
    <div data-testid="category-page">
      <h1 className="text-3xl font-bold font-heading mb-6">{cat?.name || "Category"}</h1>
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-6">
        {vids.map((v) => <VideoCard key={v.id} v={v} />)}
      </div>
      {vids.length === 0 && !loading && <p className="text-zinc-500 text-center py-10">{t("page.empty")}</p>}
      <div className="flex justify-center mt-10">
        {!done && vids.length > 0 && (
          <Button onClick={loadMore} disabled={loading} variant="outline" className="border-zinc-700 hover:bg-zinc-800" data-testid="category-load-more">
            {loading ? t("page.loading") : t("page.loadMore")}
          </Button>
        )}
      </div>
    </div>
  );
}
