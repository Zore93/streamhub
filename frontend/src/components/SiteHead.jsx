import { useEffect } from "react";
import { useLocation, useParams } from "react-router-dom";
import api, { mediaUrl } from "@/lib/api";

function setMeta(name, content, attr = "name") {
  if (!content) return;
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
 * Loads site identity + per-route Open Graph meta into <head>.
 *
 * Behaviour:
 *  - On boot, loads /site/config and applies defaults (title, og:image, og:url,
 *    favicon, canonical URL, raw meta HTML blob).
 *  - On /watch/:id, fetches the video and overrides og:title / og:image /
 *    og:description / og:url with the episode's own details so social embeds
 *    show the episode thumbnail + title instead of the generic site card.
 *
 * Note: this updates client-rendered <head>.  Discord/Slack/Telegram crawlers
 * (which do partial JS rendering) pick this up.  For Facebook (no JS at all)
 * you'd need server-side rendering — the admin can paste a static og:image
 * fallback via the Site/SEO "OG image" field.
 */
export default function SiteHead() {
  const { pathname } = useLocation();
  const params = useParams();

  // 1) Site defaults (loaded once)
  useEffect(() => {
    api.get("/site/config").then(({ data }) => {
      if (data.title) document.title = data.title;
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
      // Twitter Card defaults
      setMeta("twitter:card", "summary_large_image");
      setMeta("twitter:title", data.title);
      setMeta("twitter:description", data.description);
      if (data.og_image) setMeta("twitter:image", mediaUrl(data.og_image));
      // Favicon
      if (data.favicon_url) setLink("icon", data.favicon_url);
      // Custom raw meta HTML
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

  // 2) Per-route override for /watch/:id
  useEffect(() => {
    if (!pathname.startsWith("/watch/")) return;
    const id = params.id || pathname.split("/watch/")[1];
    if (!id) return;
    api.get(`/videos/${id}`).then(({ data }) => {
      const title = data.title + " — StreamHub";
      document.title = title;
      const desc = (data.description || "").slice(0, 200);
      setMeta("og:title", title, "property");
      setMeta("og:description", desc, "property");
      setMeta("og:type", "video.other", "property");
      if (data.thumbnail_url) setMeta("og:image", mediaUrl(data.thumbnail_url), "property");
      setMeta("og:url", window.location.href, "property");
      setMeta("twitter:title", title);
      setMeta("twitter:description", desc);
      if (data.thumbnail_url) setMeta("twitter:image", mediaUrl(data.thumbnail_url));
    }).catch(() => {});
  }, [pathname, params.id]);

  return null;
}
