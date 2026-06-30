import React, { useCallback, useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import api from "@/lib/api";
import VideoCard from "@/components/VideoCard";
import Pagination from "@/components/Pagination";
import { useT } from "@/contexts/LanguageContext";
import { categoryLabel } from "@/i18n";

const PAGE_SIZE = 24;

export default function Category() {
  const { id, page: pageParam } = useParams();
  const { t, lang } = useT();
  const currentPage = Math.max(1, parseInt(pageParam, 10) || 1);
  const [vids, setVids] = useState([]);
  const [total, setTotal] = useState(0);
  const [cats, setCats] = useState([]);
  const [loading, setLoading] = useState(false);
  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE));

  useEffect(() => {
    api.get("/categories").then((r) => setCats(r.data));
  }, []);

  const fetchPage = useCallback(async (p) => {
    setLoading(true);
    try {
      const skip = (p - 1) * PAGE_SIZE;
      const [{ data: list }, { data: counted }] = await Promise.all([
        api.get(`/videos?category_id=${id}&limit=${PAGE_SIZE}&skip=${skip}`),
        api.get(`/videos/count?category_id=${id}`),
      ]);
      setVids(list);
      setTotal(counted.count || 0);
    } finally {
      setLoading(false);
    }
  }, [id]);

  useEffect(() => {
    fetchPage(currentPage);
    window.scrollTo({ top: 0, behavior: "smooth" });
  }, [id, currentPage, fetchPage]);

  const cat = cats.find((c) => c.id === id);
  const buildHref = (p) => (p <= 1 ? `/category/${id}` : `/category/${id}/page/${p}`);

  return (
    <div data-testid="category-page">
      <h1 className="text-3xl font-bold font-heading mb-6">{categoryLabel(cat, lang) || "Category"}</h1>
      <div className="grid grid-cols-2 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-3 sm:gap-6">
        {vids.map((v) => <VideoCard key={v.id} v={v} />)}
      </div>
      {vids.length === 0 && !loading && <p className="text-zinc-500 text-center py-10">{t("page.empty")}</p>}
      <Pagination currentPage={currentPage} totalPages={totalPages} buildHref={buildHref} />
    </div>
  );
}
