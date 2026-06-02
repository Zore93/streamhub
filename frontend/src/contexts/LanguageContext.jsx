import React, { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import api from "@/lib/api";
import { t as translate, SUPPORTED_LANGUAGES } from "@/i18n";

const LangCtx = createContext(null);

const STORAGE_KEY = "lang";
const VALID = SUPPORTED_LANGUAGES.map((l) => l.code);

function readStored() {
  try {
    const v = localStorage.getItem(STORAGE_KEY);
    if (v && VALID.includes(v)) return v;
  } catch {}
  return null;
}

export function LanguageProvider({ children }) {
  // Read stored override synchronously so the very first render is correct.
  const [lang, setLangState] = useState(() => readStored() || "ro");
  const [siteCfg, setSiteCfg] = useState(null);

  const refreshSiteCfg = useCallback(async () => {
    try {
      const { data } = await api.get("/site/config");
      setSiteCfg(data);
    } catch {}
  }, []);

  useEffect(() => {
    refreshSiteCfg().then(() => {
      // After first load, apply server default ONLY if user has never explicitly chosen.
      if (!readStored()) {
        // We need siteCfg right away — fetch again here is unnecessary, but the
        // initial refreshSiteCfg has already set state. The dependency on the
        // setLangState is intentional only for first load.
      }
    });
  }, [refreshSiteCfg]);

  // One-time: align UI language with server default the first time we get cfg.
  useEffect(() => {
    if (!siteCfg) return;
    if (readStored()) return;
    if (siteCfg.default_language && VALID.includes(siteCfg.default_language)) {
      setLangState(siteCfg.default_language);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [siteCfg]);

  useEffect(() => {
    document.documentElement.lang = lang;
  }, [lang]);

  const setLang = useCallback((next) => {
    if (!VALID.includes(next)) return;
    try { localStorage.setItem(STORAGE_KEY, next); } catch {}
    setLangState(next);
  }, []);

  const t = useCallback(
    (key, fallback, vars) => {
      let str = translate(lang, key, fallback);
      if (vars && typeof str === "string") {
        for (const [k, v] of Object.entries(vars)) {
          str = str.split(`{${k}}`).join(String(v));
        }
      }
      return str;
    },
    [lang],
  );

  const value = useMemo(
    () => ({ lang, setLang, t, siteCfg, supported: SUPPORTED_LANGUAGES, refreshSiteCfg }),
    [lang, setLang, t, siteCfg, refreshSiteCfg],
  );

  return <LangCtx.Provider value={value}>{children}</LangCtx.Provider>;
}

export function useT() {
  const ctx = useContext(LangCtx);
  if (!ctx) throw new Error("useT must be used inside <LanguageProvider>");
  return ctx;
}
