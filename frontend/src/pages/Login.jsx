import React, { useState } from "react";
import { useNavigate, Link } from "react-router-dom";
import { useAuth } from "@/contexts/AuthContext";
import { useT } from "@/contexts/LanguageContext";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { toast } from "sonner";

export default function Login() {
  const { login } = useAuth();
  const { t, siteCfg } = useT();
  const nav = useNavigate();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);

  const submit = async (e) => {
    e.preventDefault();
    setBusy(true);
    try {
      await login(email, password);
      toast.success(t("auth.welcomeBack"));
      nav("/");
    } catch (err) {
      toast.error(err.response?.data?.detail || "Login failed");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="max-w-md mx-auto mt-12" data-testid="login-page">
      <h1 className="text-3xl font-bold font-heading mb-2">{t("auth.signIn")}</h1>
      <p className="text-zinc-500 mb-8">{t("auth.signIn.subtitle")} {siteCfg?.title || "StreamHub"}</p>
      <form onSubmit={submit} className="space-y-4">
        <div>
          <Label>{t("auth.email")}</Label>
          <Input
            type="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            className="bg-zinc-900 border-zinc-800"
            data-testid="login-email"
            required
          />
        </div>
        <div>
          <Label>{t("auth.password")}</Label>
          <Input
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            className="bg-zinc-900 border-zinc-800"
            data-testid="login-password"
            required
          />
        </div>
        <Button type="submit" disabled={busy} className="w-full pro-gradient text-white border-0" data-testid="login-submit">
          {busy ? t("auth.signIn.busy") : t("auth.signIn.btn")}
        </Button>
      </form>
      <p className="mt-6 text-zinc-500 text-sm">
        {t("auth.noAccount")}{" "}
        <Link to="/register" className="text-rose-400 hover:text-rose-300">{t("auth.createOne")}</Link>
      </p>
    </div>
  );
}
