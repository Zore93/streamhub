import React, { useEffect, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import api from "@/lib/api";
import { useAuth } from "@/contexts/AuthContext";
import { useT } from "@/contexts/LanguageContext";
import { Button } from "@/components/ui/button";
import { Crown, Check } from "lucide-react";
import { toast } from "sonner";

export default function Pro() {
  const [pkgs, setPkgs] = useState([]);
  const { user, refresh } = useAuth();
  const { t } = useT();
  const nav = useNavigate();
  const [busy, setBusy] = useState(null);
  const [search] = useSearchParams();

  useEffect(() => {
    api.get("/packages?tier=pro").then((r) => setPkgs(r.data)).catch(() => {});
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
          toast.success("Payment successful! You're now PRO.");
          await refresh();
          nav("/pro", { replace: true });
          return;
        }
        if (data.status === "expired") {
          toast.error("Payment expired");
          return;
        }
      } catch {}
      if (attempts < 6) setTimeout(poll, 2000);
    };
    poll();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [search]);

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
    <div data-testid="pro-page">
      <div className="text-center mb-12">
        <Crown size={48} className="pro-gradient-text mx-auto mb-4" />
        <h1 className="text-4xl sm:text-5xl font-bold font-heading mb-2">{t("pro.title")} <span className="pro-gradient-text">PRO</span></h1>
        <p className="text-zinc-400 max-w-xl mx-auto">{t("pro.subtitle")}</p>
      </div>
      {user?.is_pro && (
        <div className="bg-green-900/30 border border-green-700 rounded-lg p-4 text-center mb-8" data-testid="pro-active">
          {t("pro.active")} {user.pro_expires_at?.slice(0, 10) || "—"}
        </div>
      )}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6 max-w-5xl mx-auto">
        {pkgs.map((p) => (
          <div key={p.id} className="bg-zinc-900 border border-zinc-800 rounded-xl p-6 flex flex-col" data-testid={`package-${p.id}`}>
            <div className="font-heading text-2xl font-bold mb-1" style={{ color: p.color }}>{p.name}</div>
            <p className="text-zinc-500 text-sm mb-4 flex-1 whitespace-pre-line">{p.description}</p>
            <div className="text-3xl font-bold mb-1">${p.price}</div>
            <div className="text-xs text-zinc-500 mb-4">{p.duration_days} days access</div>
            <ul className="text-sm text-zinc-400 space-y-2 mb-6">
              <li className="flex gap-2"><Check size={14} className="text-rose-500" /> {t("pro.feature.watchAll")}</li>
              <li className="flex gap-2"><Check size={14} className="text-rose-500" /> {t("pro.feature.adFree")}</li>
              <li className="flex gap-2"><Check size={14} className="text-rose-500" /> {t("pro.feature.support")}</li>
            </ul>
            <Button disabled={busy === p.id} onClick={() => buy(p)} className="pro-gradient text-white border-0 w-full" data-testid={`buy-${p.id}`}>
              {busy === p.id ? t("pro.subscribing") : t("pro.subscribe")}
            </Button>
          </div>
        ))}
        {pkgs.length === 0 && <p className="text-zinc-500 col-span-3 text-center">{t("pro.empty")}</p>}
      </div>
    </div>
  );
}
