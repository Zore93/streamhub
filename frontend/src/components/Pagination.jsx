import React from "react";
import { Link } from "react-router-dom";
import { ChevronLeft, ChevronRight } from "lucide-react";
import { useT } from "@/contexts/LanguageContext";

/**
 * Numbered pagination with previous / next + ellipsis when the range is long.
 *
 * Props:
 *   - currentPage: 1-indexed current page number
 *   - totalPages:  total number of pages
 *   - buildHref:   (page: number) => string  — generates the URL for a page
 *
 * Renders nothing when totalPages ≤ 1.
 */
export default function Pagination({ currentPage, totalPages, buildHref }) {
  const { t } = useT();
  if (!totalPages || totalPages <= 1) return null;

  const pages = computePageList(currentPage, totalPages);

  const linkCls = "min-w-[36px] h-9 px-2 inline-flex items-center justify-center rounded-md text-sm border transition-colors";
  const inactive = "bg-zinc-900 border-zinc-800 text-zinc-300 hover:bg-zinc-800 hover:text-zinc-50";
  const active = "bg-rose-600 border-rose-500 text-white font-semibold";
  const disabled = "bg-zinc-950 border-zinc-900 text-zinc-700 cursor-not-allowed pointer-events-none";

  return (
    <nav className="flex justify-center mt-10" aria-label="Pagination" data-testid="pagination">
      <div className="flex flex-wrap items-center gap-2">
        <Link
          to={buildHref(Math.max(1, currentPage - 1))}
          className={`${linkCls} ${currentPage === 1 ? disabled : inactive}`}
          data-testid="pagination-prev"
          aria-label={t("page.previous")}
        >
          <ChevronLeft size={16} />
        </Link>
        {pages.map((p, i) =>
          p === "..." ? (
            <span key={`gap-${i}`} className="px-2 text-zinc-500 select-none">…</span>
          ) : (
            <Link
              key={p}
              to={buildHref(p)}
              className={`${linkCls} ${p === currentPage ? active : inactive}`}
              data-testid={p === currentPage ? "pagination-current" : `pagination-page-${p}`}
              aria-current={p === currentPage ? "page" : undefined}
            >
              {p}
            </Link>
          )
        )}
        <Link
          to={buildHref(Math.min(totalPages, currentPage + 1))}
          className={`${linkCls} ${currentPage === totalPages ? disabled : inactive}`}
          data-testid="pagination-next"
          aria-label={t("page.next")}
        >
          <ChevronRight size={16} />
        </Link>
      </div>
    </nav>
  );
}

/**
 * Produces a compact list like [1, "...", 4, 5, 6, "...", 12].
 * Always shows first, last, current, neighbors of current.
 */
function computePageList(current, total) {
  const delta = 1; // neighbors on each side of current
  const out = new Set([1, total, current]);
  for (let i = current - delta; i <= current + delta; i++) {
    if (i >= 1 && i <= total) out.add(i);
  }
  const sorted = Array.from(out).sort((a, b) => a - b);
  const result = [];
  let prev = 0;
  for (const p of sorted) {
    if (prev && p - prev > 1) result.push("...");
    result.push(p);
    prev = p;
  }
  return result;
}
