import { useEffect, useRef } from "react";
import { useLocation, useParams } from "react-router-dom";
import api, { mediaUrl } from "@/lib/api";

function setMeta(name, content, attr = "name") {
  if (content == null) return;
  let m = document.querySelector(`meta[${attr}="${name}"]`);
  if (!m) {
    m = document.createElement("meta");
    m.setAttribute(attr, name);
    document.head.appendChild(m);
  }
  m.setAttribute("content", content);
}

function setLink(rel, href) {
  if (!href) return;
  let l = document.querySelector(`link[rel="${rel}"]`);
  if (!l) {
    l = document.createElement("link");
    l.setAttribute("rel", rel);
    document.head.appendChild(l);
  }
  l.setAttribute("href", href);
}

/**
 * Sync per-route document.title + Open Graph tags.
 *
 * Behaviour:
 *  - Loads /site/config once; the default site title is cached as `defaultTitle`.
 *  - On `/watch/:id` we fetch the video and overwrite title + OG tags.
 *  - On EVERY other route we restore the site default title (fixes the bug
 *    where the tab title kept the previous episode title after navigation).
 *
 * Crawlers (Discord/Facebook/Telegram/etc) do NOT execute JavaScript — they
 * hit `/api/og/video/:id` directly via the FastAPI middleware in server.py.
 */
export default function SiteHead() {
  const { pathname } = useLocation();
  const params = useParams();
  const defaultsRef = useRef({ title: "StreamHub", description: "", og_image: "", canonical_url: "" });

  // 1) Site defaults — loaded once, applied to <head>.
  useEffect(() => {
    api.get("/site/config").then(({ data }) => {
      defaultsRef.current = {
        title: data.title || "StreamHub",
        description: data.description || "",
        og_image: data.og_image || "",
        canonical_url: data.canonical_url || "",
      };
      // Apply site defaults immediately
      document.title = defaultsRef.current.title;
      setMeta("description", data.description);
      setMeta("keywords", data.keywords);
      setMeta("og:title", data.title, "property");
      setMeta("og:description", data.description, "property");
      setMeta("og:type", "website", "property");
      setMeta("og:site_name", data.title, "property");
      if (data.og_image) setMeta("og:image", mediaUrl(data.og_image), "property");
      if (data.canonical_url) {
        setMeta("og:url", data.canonical_url, "property");
        setLink("canonical", data.canonical_url);
      }
      setMeta("twitter:card", "summary_large_image");
      setMeta("twitter:title", data.title);
      setMeta("twitter:description", data.description);
      if (data.og_image) setMeta("twitter:image", mediaUrl(data.og_image));
      if (data.favicon_url) setLink("icon", data.favicon_url);
      if (data.meta) {
        document.querySelectorAll("meta[data-streamhub-custom]").forEach((n) => n.remove());
        const tmpl = document.createElement("template");
        tmpl.innerHTML = data.meta;
        tmpl.content.querySelectorAll("meta").forEach((m) => {
          m.setAttribute("data-streamhub-custom", "1");
          document.head.appendChild(m);
        });
      }
    }).catch(() => {});
  }, []);

  // 2) Per-route title + OG sync.
  useEffect(() => {
    const onWatch = pathname.startsWith("/watch/");
    if (!onWatch) {
      // Restore the site default title so users don't keep seeing the previous
      // episode name in the browser tab after navigating away.
      const d = defaultsRef.current;
      if (d.title) document.title = d.title;
      setMeta("og:title", d.title, "property");
      setMeta("og:description", d.description, "property");
      setMeta("og:type", "website", "property");
      if (d.og_image) setMeta("og:image", mediaUrl(d.og_image), "property");
      setMeta("twitter:title", d.title);
      setMeta("twitter:description", d.description);
      return;
    }
    const id = params.id || pathname.split("/watch/")[1];
    if (!id) return;
    api.get(`/videos/${id}`).then(({ data }) => {
      const title = `${data.title} — ${defaultsRef.current.title || "StreamHub"}`;
      document.title = title;
      const desc = (data.description || "").slice(0, 200);
      // Compute the CANONICAL slug URL — critical for SEO so Google doesn't
      // treat /watch/<uuid> and /watch/<slug> as duplicate content.
      const siteBase = (defaultsRef.current.canonical_url || window.location.origin).replace(/\/$/, "");
      const canonicalPath = `/watch/${data.slug || data.id}`;
      const canonicalUrl = `${siteBase}${canonicalPath}`;
      setMeta("og:title", title, "property");
      setMeta("og:description", desc, "property");
      setMeta("og:type", "video.other", "property");
      if (data.thumbnail_url) setMeta("og:image", mediaUrl(data.thumbnail_url), "property");
      setMeta("og:url", canonicalUrl, "property");
      setLink("canonical", canonicalUrl);
      setMeta("twitter:title", title);
      setMeta("twitter:description", desc);
      if (data.thumbnail_url) setMeta("twitter:image", mediaUrl(data.thumbnail_url));
    }).catch(() => {});
  }, [pathname, params.id]);

  return null;
}
