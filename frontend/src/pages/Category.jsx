import React, { useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import api from "@/lib/api";
import VideoCard from "@/components/VideoCard";

export default function Category() {
  const { id } = useParams();
  const [vids, setVids] = useState([]);
  const [cats, setCats] = useState([]);
  useEffect(() => {
    api.get(`/videos?category_id=${id}&limit=60`).then((r) => setVids(r.data));
    api.get("/categories").then((r) => setCats(r.data));
  }, [id]);
  const cat = cats.find((c) => c.id === id);
  return (
    <div data-testid="category-page">
      <h1 className="text-3xl font-bold font-heading mb-6">{cat?.name || "Category"}</h1>
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-6">
        {vids.map((v) => <VideoCard key={v.id} v={v} />)}
      </div>
      {vids.length === 0 && <p className="text-zinc-500">No videos in this category.</p>}
    </div>
  );
}
