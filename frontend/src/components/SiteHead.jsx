import { useEffect } from "react";
import api from "@/lib/api";

/**
 * Loads site identity (title / description / favicon / SEO meta) from the
 * backend and applies it to the live <head>. Runs once on app boot.
 */
export default function SiteHead() {
  useEffect(() => {
    api.get("/site/config").then(({ data }) => {
      if (data.title) document.title = data.title;
      if (data.description) {
        let m = document.querySelector('meta[name="description"]');
        if (!m) { m = document.createElement("meta"); m.setAttribute("name", "description"); document.head.appendChild(m); }
        m.setAttribute("content", data.description);
      }
      if (data.keywords) {
        let m = document.querySelector('meta[name="keywords"]');
        if (!m) { m = document.createElement("meta"); m.setAttribute("name", "keywords"); document.head.appendChild(m); }
        m.setAttribute("content", data.keywords);
      }
      if (data.favicon_url) {
        let l = document.querySelector('link[rel="icon"]');
        if (!l) { l = document.createElement("link"); l.setAttribute("rel", "icon"); document.head.appendChild(l); }
        l.setAttribute("href", data.favicon_url);
      }
      if (data.meta) {
        // strip & re-inject custom <meta> blob
        document.querySelectorAll('meta[data-streamhub-custom]').forEach((n) => n.remove());
        const tmpl = document.createElement("template");
        tmpl.innerHTML = data.meta;
        tmpl.content.querySelectorAll("meta").forEach((m) => {
          m.setAttribute("data-streamhub-custom", "1");
          document.head.appendChild(m);
        });
      }
    }).catch(() => {});
  }, []);
  return null;
}
