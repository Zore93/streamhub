import React, { useEffect, useState } from "react";
import api from "@/lib/api";
import VideoCard from "@/components/VideoCard";
import { Flame, Clock, Shuffle } from "lucide-react";

function Section({ title, Icon, videos }) {
  if (!videos || videos.length === 0) return null;
  return (
    <section className="mb-12" data-testid={`section-${title.toLowerCase().replace(/\s/g, "-")}`}>
      <div className="flex items-center gap-3 mb-6">
        <Icon size={24} className="text-rose-500" />
        <h2 className="text-2xl sm:text-3xl font-semibold tracking-tight text-zinc-50">{title}</h2>
      </div>
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-6">
        {videos.map((v) => <VideoCard key={v.id} v={v} />)}
      </div>
    </section>
  );
}

export default function Home() {
  const [latest, setLatest] = useState([]);
  const [popular, setPopular] = useState([]);
  const [random, setRandom] = useState([]);

  useEffect(() => {
    api.get("/videos?section=latest&limit=10").then((r) => setLatest(r.data)).catch(() => {});
    api.get("/videos?section=popular&limit=10").then((r) => setPopular(r.data)).catch(() => {});
    api.get("/videos?section=random&limit=10").then((r) => setRandom(r.data)).catch(() => {});
  }, []);

  const isEmpty = latest.length === 0 && popular.length === 0 && random.length === 0;

  return (
    <div data-testid="home-page">
      <header className="mb-10">
        <h1 className="text-4xl sm:text-5xl font-bold tracking-tight text-zinc-50 font-heading">Welcome to StreamHub</h1>
        <p className="text-zinc-400 mt-2 max-w-2xl">A premium video-sharing community. Discover, upload and stream in stunning quality.</p>
      </header>
      {isEmpty && (
        <div className="bg-zinc-900/50 border border-zinc-800 rounded-xl p-12 text-center" data-testid="empty-state">
          <h3 className="text-xl font-semibold mb-2">No videos yet</h3>
          <p className="text-zinc-500">Be the first to upload one!</p>
        </div>
      )}
      <Section title="Latest Uploads" Icon={Clock} videos={latest} />
      <Section title="Most Viewed" Icon={Flame} videos={popular} />
      <Section title="Discover" Icon={Shuffle} videos={random} />
    </div>
  );
}
