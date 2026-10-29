import React, { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import api, { mediaUrl } from "@/lib/api";
import { Layout } from "@/layout/Layout";
import { Button } from "@/components/ui/button";
import { Users, Film, Play, Loader2, RefreshCw } from "lucide-react";
import SiteHead from "@/components/SiteHead";

/**
 * Party Rooms — public listing of all active watch-party rooms created with
 * visibility=public. Ordered by member count DESC. Auto-refreshes every 10s
 * so empty rooms (where everyone left) drop off the list quickly, and new
 * rooms show up as people create them.
 */
export default function PartyRooms() {
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);

  const load = async () => {
    try {
      const { data } = await api.get("/parties");
      setItems(data.items || []);
    } catch {
      /* keep stale list */
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    load();
    const id = setInterval(load, 10000); // 10s refresh
    return () => clearInterval(id);
  }, []);

  return (
    <Layout>
      <SiteHead
        title="Party Rooms — Vizionează cu prietenii"
        description="Lista camerelor publice de Watch Party active acum. Alătură-te și urmărește împreună cu alții în timp real."
      />
      <div className="max-w-5xl" data-testid="party-rooms-page">
        <div className="flex items-center justify-between mb-6 flex-wrap gap-3">
          <div>
            <h1 className="text-3xl sm:text-4xl font-bold mb-1 flex items-center gap-2">
              <Users className="text-fuchsia-400" size={28} />
              Party Rooms
            </h1>
            <p className="text-zinc-400 text-sm">
              Camere publice active chiar acum. Intră și vezi împreună cu alții.
            </p>
          </div>
          <Button
            variant="outline"
            size="sm"
            onClick={load}
            className="border-zinc-700"
            data-testid="party-rooms-refresh"
          >
            <RefreshCw size={14} className="mr-1.5" /> Reîmprospătează
          </Button>
        </div>

        {loading ? (
          <div className="flex items-center justify-center py-20 text-zinc-500">
            <Loader2 size={24} className="animate-spin mr-2" /> Se încarcă camerele…
          </div>
        ) : items.length === 0 ? (
          <div className="text-center py-20 bg-zinc-900/40 border border-zinc-800 rounded-xl">
            <Film size={44} className="text-zinc-700 mx-auto mb-3" />
            <h2 className="text-xl font-semibold mb-1">Nicio cameră publică activă</h2>
            <p className="text-zinc-400 text-sm max-w-md mx-auto">
              Fii primul! Deschide orice videoclip și apasă <span className="text-fuchsia-400 font-semibold">„Vizionare în grup"</span> pentru a crea o cameră publică.
            </p>
          </div>
        ) : (
          <div className="grid gap-3" data-testid="party-rooms-list">
            {items.map((p) => (
              <div
                key={p.code}
                className="bg-zinc-900 border border-zinc-800 rounded-xl p-3 flex items-center gap-4 hover:border-fuchsia-500/40 transition-colors"
                data-testid={`party-row-${p.code}`}
              >
                {/* Thumbnail */}
                <div className="relative shrink-0 w-32 sm:w-40 aspect-video bg-black rounded-lg overflow-hidden border border-zinc-800">
                  {p.video?.thumbnail_url ? (
                    <img
                      src={mediaUrl(p.video.thumbnail_url)}
                      alt={p.video?.title || "Video"}
                      className="w-full h-full object-cover"
                      loading="lazy"
                    />
                  ) : (
                    <div className="w-full h-full flex items-center justify-center text-zinc-700">
                      <Film size={22} />
                    </div>
                  )}
                  <div className="absolute inset-0 flex items-center justify-center opacity-0 hover:opacity-100 bg-black/50 transition-opacity">
                    <Play size={22} className="text-white" />
                  </div>
                </div>

                {/* Meta */}
                <div className="flex-1 min-w-0">
                  <div className="text-[11px] uppercase tracking-wider text-fuchsia-400 flex items-center gap-1 mb-0.5">
                    <code className="font-mono tracking-wider text-zinc-300 bg-zinc-800 px-1.5 py-0.5 rounded text-[10px]">
                      {p.code}
                    </code>
                    <span className="text-zinc-600">·</span>
                    <span>Gazdă: {p.host_name || "Guest"}</span>
                  </div>
                  <div className="text-base sm:text-lg font-semibold text-zinc-100 line-clamp-1" data-testid={`party-row-title-${p.code}`}>
                    {p.video?.title || "Videoclip indisponibil"}
                  </div>
                  <div className="flex items-center gap-2 text-xs text-zinc-500 mt-1">
                    <span className="inline-flex items-center gap-1 text-emerald-300 bg-emerald-500/10 border border-emerald-500/30 rounded-full px-2 py-0.5">
                      <Users size={11} /> {p.member_count} {p.member_count === 1 ? "membru" : "membri"}
                    </span>
                    {p.video?.access_tier && p.video.access_tier !== "free" && (
                      <span className="uppercase text-amber-300">{p.video.access_tier}</span>
                    )}
                  </div>
                </div>

                {/* Join */}
                <Link to={`/party/${p.code}`} data-testid={`party-join-${p.code}`}>
                  <Button className="pro-gradient text-white border-0">
                    <Users size={14} className="mr-1.5" /> Intră
                  </Button>
                </Link>
              </div>
            ))}
          </div>
        )}
      </div>
    </Layout>
  );
}
