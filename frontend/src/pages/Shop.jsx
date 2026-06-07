import React, { useEffect, useState } from "react";
import api from "@/lib/api";
import { useAuth } from "@/contexts/AuthContext";
import FramedAvatar from "@/components/FramedAvatar";
import { Button } from "@/components/ui/button";
import { Coins, Check, Lock } from "lucide-react";
import { toast } from "sonner";
import { Link } from "react-router-dom";

const RARITY_ORDER = { legendary: 0, epic: 1, rare: 2, common: 3 };

export default function Shop() {
  const { user, setUser, refresh } = useAuth();
  const [frames, setFrames] = useState([]);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(null); // frame id being purchased
  const [filter, setFilter] = useState("all");

  useEffect(() => {
    api.get("/shop/frames")
      .then(({ data }) => { setFrames(data); setLoading(false); })
      .catch(() => setLoading(false));
  }, []);

  const reload = () => {
    api.get("/shop/frames").then(({ data }) => setFrames(data)).catch(() => {});
  };

  const RARITY_ORDER_MAP = RARITY_ORDER;
  const byRarity = (a, b) => (RARITY_ORDER_MAP[a.rarity] - RARITY_ORDER_MAP[b.rarity]) || (a.price_coins - b.price_coins);
  const sortedFrames = [...frames].sort(byRarity);
  const filtered = filter === "all"
    ? sortedFrames
    : filter === "owned"
      ? sortedFrames.filter((f) => f.owned)
      : sortedFrames.filter((f) => f.rarity === filter);

  const buy = async (frame) => {
    if (!user) {
      toast.error("Conectează-te pentru a cumpăra");
      return;
    }
    setBusy(frame.id);
    try {
      const { data } = await api.post(`/shop/frames/${frame.id}/purchase`);
      setUser(data.user);
      toast.success(`Cadru "${frame.name}" cumpărat!`);
      reload();
    } catch (e) {
      const msg = e.response?.data?.detail || "Eroare la cumpărare";
      toast.error(msg);
    } finally {
      setBusy(null);
    }
  };

  return (
    <div className="max-w-7xl mx-auto" data-testid="shop-page">
      <div className="flex items-center justify-between mb-6 flex-wrap gap-3">
        <div>
          <h1 className="text-3xl font-bold font-heading">Magazin de Cadre</h1>
          <p className="text-zinc-400 text-sm mt-1">
            Câștigi monede dând <span className="text-rose-300">like</span> sau comentând la videoclipuri.
            Cumpără cadre animate pentru avatar.
          </p>
        </div>
        {user && (
          <div className="inline-flex items-center gap-2 bg-amber-500/15 border border-amber-500/40 px-4 py-2 rounded-md" data-testid="shop-balance">
            <Coins className="text-amber-300" size={18} />
            <span className="font-bold text-amber-200 text-lg">{user.coins || 0}</span>
            <span className="text-amber-300/80 text-sm">monede</span>
          </div>
        )}
        {!user && (
          <Link to="/login" className="text-rose-400 hover:underline">Conectează-te pentru a cumpăra</Link>
        )}
      </div>

      <div className="flex gap-2 mb-5 flex-wrap" role="tablist">
        {[
          ["all", "Toate"],
          ["legendary", "Legendare"],
          ["epic", "Epice"],
          ["rare", "Rare"],
          ["common", "Comune"],
          ["owned", "Deținute"],
        ].map(([k, label]) => (
          <button
            key={k}
            onClick={() => setFilter(k)}
            data-testid={`filter-${k}`}
            className={`px-3 py-1.5 rounded-md text-sm transition-colors ${filter === k ? "bg-rose-500 text-white" : "bg-zinc-900 text-zinc-300 hover:bg-zinc-800"}`}
          >
            {label}
          </button>
        ))}
      </div>

      {loading ? (
        <div className="text-zinc-500">Se încarcă...</div>
      ) : (
        <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 xl:grid-cols-6 gap-4">
          {filtered.map((f) => {
            const canAfford = (user?.coins || 0) >= f.price_coins;
            return (
              <div
                key={f.id}
                className={`bg-zinc-900 border rounded-lg p-3 flex flex-col items-center gap-2 transition-colors ${rarityBorder(f.rarity)}`}
                data-testid={`shop-frame-${f.id}`}
              >
                <FramedAvatar
                  src={user?.avatar_url}
                  username={user?.username || "?"}
                  size={84}
                  frame={f}
                />
                <div className="text-sm font-semibold text-zinc-100 text-center line-clamp-1">{f.name}</div>
                <RarityBadge rarity={f.rarity} />
                <div className="flex items-center gap-1 text-amber-300 font-bold text-sm">
                  <Coins size={14} /> {f.price_coins}
                </div>
                {f.owned ? (
                  <Button variant="secondary" size="sm" className="w-full" disabled>
                    <Check size={14} className="mr-1" /> Deținut
                  </Button>
                ) : (
                  <Button
                    size="sm"
                    className="w-full"
                    disabled={!canAfford || busy === f.id}
                    onClick={() => buy(f)}
                    data-testid={`buy-frame-${f.id}`}
                  >
                    {!canAfford ? <><Lock size={14} className="mr-1" /> Insuficient</> : busy === f.id ? "..." : "Cumpără"}
                  </Button>
                )}
              </div>
            );
          })}
          {filtered.length === 0 && <p className="text-zinc-500 col-span-full text-center py-8">Niciun cadru în această categorie.</p>}
        </div>
      )}
    </div>
  );
}

function rarityBorder(r) {
  if (r === "legendary") return "border-amber-500/50 hover:border-amber-500";
  if (r === "epic") return "border-purple-500/40 hover:border-purple-500";
  if (r === "rare") return "border-blue-500/40 hover:border-blue-500";
  return "border-zinc-800 hover:border-zinc-700";
}

function RarityBadge({ rarity }) {
  const colors = {
    common: "bg-zinc-800 text-zinc-300 border-zinc-700",
    rare: "bg-blue-500/15 text-blue-300 border-blue-500/40",
    epic: "bg-purple-500/15 text-purple-300 border-purple-500/40",
    legendary: "bg-amber-500/15 text-amber-300 border-amber-500/40",
  };
  return (
    <span className={`text-[10px] font-semibold uppercase tracking-wide px-1.5 py-0.5 rounded border ${colors[rarity] || colors.common}`}>
      {rarity}
    </span>
  );
}
