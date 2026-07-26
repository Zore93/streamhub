import React, { useEffect, useState } from "react";
import { useNavigate, useSearchParams, Link } from "react-router-dom";
import api from "@/lib/api";
import { useAuth } from "@/contexts/AuthContext";
import { Button } from "@/components/ui/button";
import { Crown, Check, Sparkles } from "lucide-react";
import { toast } from "sonner";

export default function Vip() {
  const [pkgs, setPkgs] = useState([]);
  const { user, refresh } = useAuth();
  const nav = useNavigate();
  const [busy, setBusy] = useState(null);
  const [search] = useSearchParams();

  useEffect(() => {
    api.get("/packages?tier=vip").then((r) => setPkgs(r.data)).catch(() => {});
  }, []);

  // Handle return-from-stripe
  useEffect(() => {
    const sid = search.get("session_id");
    if (!sid) return;
    let attempts = 0;
    const poll = async () => {
      attempts++;
      try {
        const { data } = await api.get(`/payments/status/${sid}`);
        if (data.payment_status === "paid") {
          toast.success("Plată reușită! Ești acum VIP.");
          await refresh();
          nav("/vip", { replace: true });
          return;
        }
        if (data.status === "expired") {
          toast.error("Plată expirată");
          return;
        }
      } catch { /* ignore transient errors while polling */ }
      if (attempts < 6) setTimeout(poll, 2000);
    };
    poll();
  }, [search, nav, refresh]);

  const buy = async (pkg) => {
    if (!user) return nav("/login");
    setBusy(pkg.id);
    try {
      const { data } = await api.post("/payments/checkout", {
        package_id: pkg.id,
        origin_url: window.location.origin,
      });
      window.location.href = data.url;
    } catch (err) {
      toast.error(err.response?.data?.detail || "Checkout failed");
      setBusy(null);
    }
  };

  return (
    <div data-testid="vip-page">
      <div className="text-center mb-12">
        <Crown size={48} className="vip-gradient-text mx-auto mb-4" />
        <h1 className="text-4xl sm:text-5xl font-bold font-heading mb-2">
          Devino <span className="vip-gradient-text">VIP</span>
        </h1>
        <p className="text-zinc-400 max-w-xl mx-auto">
          Acces la conținut exclusiv VIP + tot conținutul PRO și Free.
        </p>
        <Link to="/pro" className="inline-block mt-3 text-sm text-rose-400 hover:underline" data-testid="vip-goto-pro">
          Vezi pachetele PRO →
        </Link>
      </div>

      {user?.is_vip && (
        <div className="bg-amber-900/30 border border-amber-700 rounded-lg p-4 text-center mb-8" data-testid="vip-active">
          <Sparkles size={16} className="inline mr-2 text-amber-300" />
          Abonament VIP activ până la {user.vip_expires_at?.slice(0, 10) || "—"}
        </div>
      )}

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6 max-w-5xl mx-auto">
        {pkgs.map((p) => (
          <div key={p.id} className="vip-border-gradient rounded-xl p-6 flex flex-col" data-testid={`vip-package-${p.id}`}>
            <div className="font-heading text-2xl font-bold mb-1 vip-gradient-text flex items-center gap-2">
              <Crown size={20} /> {p.name}
            </div>
            <p className="text-zinc-400 text-sm mb-4 flex-1 whitespace-pre-line">{p.description}</p>
            <div className="text-3xl font-bold mb-1">${p.price}</div>
            <div className="text-xs text-zinc-500 mb-4">{p.duration_days} zile acces</div>
            <ul className="text-sm text-zinc-300 space-y-2 mb-6">
              <li className="flex gap-2"><Check size={14} className="text-amber-400" /> Acces la conținut VIP exclusiv</li>
              <li className="flex gap-2"><Check size={14} className="text-amber-400" /> Include și tot conținutul PRO</li>
              <li className="flex gap-2"><Check size={14} className="text-amber-400" /> Fără reclame · Suport prioritar</li>
            </ul>
            <Button
              disabled={busy === p.id}
              onClick={() => buy(p)}
              className="vip-gradient text-black font-bold border-0 w-full hover:opacity-90"
              data-testid={`vip-buy-${p.id}`}
            >
              {busy === p.id ? "Se procesează…" : "Abonează-te VIP"}
            </Button>
          </div>
        ))}
        {pkgs.length === 0 && (
          <p className="text-zinc-500 col-span-3 text-center" data-testid="vip-empty">
            Nu sunt pachete VIP disponibile momentan. Adaugă-le din Admin Panel → Packages VIP.
          </p>
        )}
      </div>
    </div>
  );
}
