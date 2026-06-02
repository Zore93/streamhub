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

  useEffect(() => {
    api.get("/site/config").then(({ data }) => {
      setSiteCfg(data);
      // Apply server default ONLY if user has never explicitly chosen.
      if (!readStored() && data.default_language && VALID.includes(data.default_language)) {
        setLangState(data.default_language);
      }
    }).catch(() => {});
  }, []);

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
    () => ({ lang, setLang, t, siteCfg, supported: SUPPORTED_LANGUAGES }),
    [lang, setLang, t, siteCfg],
  );

  return <LangCtx.Provider value={value}>{children}</LangCtx.Provider>;
}

export function useT() {
  const ctx = useContext(LangCtx);
  if (!ctx) throw new Error("useT must be used inside <LanguageProvider>");
  return ctx;
}
