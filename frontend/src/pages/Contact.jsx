import React, { useState } from "react";
import api from "@/lib/api";
import { useT } from "@/contexts/LanguageContext";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { Mail } from "lucide-react";
import { toast } from "sonner";

export default function Contact() {
  const { t } = useT();
  const [title, setTitle] = useState("");
  const [email, setEmail] = useState("");
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState(false);

  const submit = async (e) => {
    e.preventDefault();
    setBusy(true);
    try {
      await api.post("/contact", { title, email, message });
      toast.success(t("contact.sent"));
      setTitle(""); setEmail(""); setMessage("");
    } catch (err) {
      toast.error(err.response?.data?.detail || "Send failed");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="max-w-xl mx-auto" data-testid="contact-page">
      <div className="flex items-center gap-3 mb-2">
        <Mail size={28} className="text-rose-500" />
        <h1 className="text-3xl sm:text-4xl font-bold font-heading">{t("contact.title")}</h1>
      </div>
      <p className="text-zinc-400 mb-8">{t("contact.subtitle")}</p>
      <form onSubmit={submit} className="bg-zinc-900 border border-zinc-800 rounded-xl p-6 space-y-4">
        <div>
          <Label>{t("contact.titleField")}</Label>
          <Input value={title} onChange={(e) => setTitle(e.target.value)} required className="bg-zinc-950 border-zinc-800" data-testid="contact-title" />
        </div>
        <div>
          <Label>{t("contact.message")}</Label>
          <Textarea rows={6} value={message} onChange={(e) => setMessage(e.target.value)} required className="bg-zinc-950 border-zinc-800" data-testid="contact-message" />
        </div>
        <div>
          <Label>{t("contact.email")}</Label>
          <Input type="email" value={email} onChange={(e) => setEmail(e.target.value)} required className="bg-zinc-950 border-zinc-800" data-testid="contact-email" />
        </div>
        <Button type="submit" disabled={busy} className="w-full pro-gradient text-white border-0" data-testid="contact-send">
          {busy ? t("contact.sending") : t("contact.send")}
        </Button>
      </form>
    </div>
  );
}
