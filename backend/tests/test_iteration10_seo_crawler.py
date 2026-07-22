"""SEO crawler middleware + category SSR tests (iteration 10).

Covers:
- Static index.html correctness (no Emergent branding, lang=ro, Loading title)
- /api/og/category/{slug} valid + invalid slug fallback
- Crawler middleware for /category/:slug, /videos/category/:slug (Googlebot only)
- Crawler middleware regression for /watch/:slug and / and listing pages
- Regular browser UA doesn't trigger SSR
"""
import os
import re
import pytest
import requests

BACKEND_URL = "http://127.0.0.1:8001"  # Direct hit — crawler middleware only works on non-/api paths on backend
PUBLIC_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")

GOOGLEBOT_UA = (
    "Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)"
)
BROWSER_UA = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/121.0.0.0 Safari/537.36"
)

INDEX_HTML_PATH = "/app/frontend/public/index.html"


# ---------- Static index.html (build-time SEO) ----------
class TestStaticIndexHtml:
    def test_index_html_lang_is_ro(self):
        with open(INDEX_HTML_PATH, "r", encoding="utf-8") as f:
            content = f.read()
        assert re.search(r'<html\s+lang="ro"', content), "index.html must have lang='ro'"

    def test_index_html_title_is_loading(self):
        with open(INDEX_HTML_PATH, "r", encoding="utf-8") as f:
            content = f.read()
        m = re.search(r"<title>(.*?)</title>", content, re.IGNORECASE | re.DOTALL)
        assert m, "index.html must have a <title>"
        title = m.group(1).strip()
        assert "Emergent" not in title, f"Title should not contain 'Emergent', got: {title!r}"
        assert title in ("Loading…", "Loading..."), f"Title must be 'Loading…', got: {title!r}"

    def test_index_html_description_not_emergent(self):
        with open(INDEX_HTML_PATH, "r", encoding="utf-8") as f:
            content = f.read()
        m = re.search(
            r'<meta\s+name="description"\s+content="([^"]*)"', content, re.IGNORECASE
        )
        assert m, "index.html must have a meta description"
        desc = m.group(1)
        assert "emergent.sh" not in desc.lower(), f"description must not reference emergent.sh: {desc!r}"
        assert "product of emergent" not in desc.lower()


# ---------- /api/og/category/{slug} endpoint ----------
class TestOgCategoryEndpoint:
    @classmethod
    def setup_class(cls):
        r = requests.get(f"{BACKEND_URL}/api/categories", timeout=10)
        cls.categories = r.json() if r.status_code == 200 else []

    def _first_slug(self):
        for c in self.categories:
            if c.get("slug"):
                return c["slug"], c["name"]
        pytest.skip("No categories available with a slug")

    def test_og_category_valid_slug(self):
        slug, name = self._first_slug()
        r = requests.get(f"{BACKEND_URL}/api/og/category/{slug}", timeout=10)
        assert r.status_code == 200, f"expected 200, got {r.status_code}"
        assert "text/html" in r.headers.get("content-type", ""), (
            f"expected html, got {r.headers.get('content-type')}"
        )
        html = r.text
        # Title must include category name
        m = re.search(r"<title>(.*?)</title>", html, re.IGNORECASE | re.DOTALL)
        assert m, "no <title> tag"
        title = m.group(1)
        assert name in title, f"title must include category name {name!r}, got {title!r}"
        assert "—" in title or "-" in title, f"expected 'Name — SiteTitle', got {title!r}"
        # Canonical link
        canonical_m = re.search(
            r'<link\s+rel="canonical"\s+href="([^"]+)"', html, re.IGNORECASE
        )
        assert canonical_m, "missing canonical link"
        assert f"/category/{slug}" in canonical_m.group(1)
        # Meta description
        assert re.search(r'<meta\s+name="description"', html, re.IGNORECASE), \
            "missing meta description"
        # lang=ro
        assert re.search(r'<html\s+lang="ro"', html), "SSR should be lang='ro'"
        # <ul> present (episodes list)
        assert "<ul>" in html, "expected <ul> listing element"

    def test_og_category_invalid_slug_falls_back_to_home(self):
        r = requests.get(
            f"{BACKEND_URL}/api/og/category/this-does-not-exist-xyz-12345",
            timeout=10,
        )
        assert r.status_code == 200, "invalid slug should fall back to home SSR, not 404"
        assert "text/html" in r.headers.get("content-type", "")
        html = r.text
        # Should NOT contain 404
        assert "404" not in html
        # Should have a <title>
        assert re.search(r"<title>.+?</title>", html, re.IGNORECASE | re.DOTALL)


# ---------- Crawler middleware ----------
class TestCrawlerMiddleware:
    @classmethod
    def setup_class(cls):
        r = requests.get(f"{BACKEND_URL}/api/categories", timeout=10)
        cls.categories = r.json() if r.status_code == 200 else []
        # get a video slug too
        rv = requests.get(f"{BACKEND_URL}/api/videos", timeout=10)
        cls.video_slug = None
        if rv.status_code == 200:
            data = rv.json()
            items = data if isinstance(data, list) else data.get("videos") or data.get("items") or []
            for v in items:
                if v.get("slug"):
                    cls.video_slug = v["slug"]
                    break

    def _first_cat(self):
        for c in self.categories:
            if c.get("slug"):
                return c
        pytest.skip("No categories with slug")

    def test_googlebot_on_category_returns_ssr(self):
        cat = self._first_cat()
        slug = cat["slug"]
        name = cat["name"]
        r = requests.get(
            f"{BACKEND_URL}/category/{slug}",
            headers={"User-Agent": GOOGLEBOT_UA},
            timeout=10,
            allow_redirects=False,
        )
        assert r.status_code == 200, f"expected 200, got {r.status_code}"
        assert "text/html" in r.headers.get("content-type", "")
        html = r.text
        # Should be SSR HTML with category title, not the SPA index
        assert name in html, f"expected SSR content containing {name!r}"
        # Distinguishing marker: SSR page has no <div id=\"root\">, but has a canonical
        assert "rel=\"canonical\"" in html or "rel='canonical'" in html
        assert "/category/" in html

    def test_googlebot_on_legacy_videos_category_returns_ssr(self):
        cat = self._first_cat()
        slug = cat["slug"]
        r = requests.get(
            f"{BACKEND_URL}/videos/category/{slug}",
            headers={"User-Agent": GOOGLEBOT_UA},
            timeout=10,
            allow_redirects=False,
        )
        assert r.status_code == 200
        assert "text/html" in r.headers.get("content-type", "")
        html = r.text
        assert cat["name"] in html
        assert "rel=\"canonical\"" in html or "rel='canonical'" in html

    def test_regular_browser_on_category_does_not_trigger_ssr(self):
        cat = self._first_cat()
        slug = cat["slug"]
        r = requests.get(
            f"{BACKEND_URL}/category/{slug}",
            headers={"User-Agent": BROWSER_UA},
            timeout=10,
            allow_redirects=False,
        )
        # Should NOT return the crawler SSR — should fall through to SPA or 404.
        # The SSR marker is the specific <title>Name — Site</title> pattern.
        # Regular browsers should NOT see that SSR title.
        # 404 is acceptable (no SPA behind on port 8001), but if 200 must not be SSR.
        html = r.text
        # SSR would have <h1>Comedy</h1> and Episoade section — assert absent
        ssr_signature = f"<h1>{cat['name']}</h1>"
        assert ssr_signature not in html, (
            "Regular browser should NOT receive crawler SSR HTML"
        )

    def test_googlebot_on_watch_still_works(self):
        if not self.video_slug:
            pytest.skip("No video slug available for regression check")
        r = requests.get(
            f"{BACKEND_URL}/watch/{self.video_slug}",
            headers={"User-Agent": GOOGLEBOT_UA},
            timeout=10,
            allow_redirects=False,
        )
        assert r.status_code == 200
        assert "text/html" in r.headers.get("content-type", "")
        html = r.text
        # Video SSR contains og:video or og:type=video.other or a <title>
        assert re.search(r"<title>.+?</title>", html, re.IGNORECASE | re.DOTALL)
        assert "og:type" in html or "og:title" in html

    def test_googlebot_on_popular_returns_home_ssr(self):
        r = requests.get(
            f"{BACKEND_URL}/popular",
            headers={"User-Agent": GOOGLEBOT_UA},
            timeout=10,
            allow_redirects=False,
        )
        assert r.status_code == 200
        assert "text/html" in r.headers.get("content-type", "")
        html = r.text
        assert re.search(r"<title>.+?</title>", html, re.IGNORECASE | re.DOTALL)

    def test_googlebot_on_all_episodes_returns_home_ssr(self):
        r = requests.get(
            f"{BACKEND_URL}/all-episodes",
            headers={"User-Agent": GOOGLEBOT_UA},
            timeout=10,
            allow_redirects=False,
        )
        assert r.status_code == 200
        assert "text/html" in r.headers.get("content-type", "")
        html = r.text
        assert re.search(r"<title>.+?</title>", html, re.IGNORECASE | re.DOTALL)


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
