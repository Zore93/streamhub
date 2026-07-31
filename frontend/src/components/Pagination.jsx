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
 *   - buildHref:   (page: number) => string  — generates the URL for a page (Link mode)
 *   - onPageChange: (page: number) => void   — click handler (button mode; used when buildHref is omitted)
 *
 * Renders nothing when totalPages ≤ 1.
 */
export default function Pagination({ currentPage, totalPages, buildHref, onPageChange }) {
  const { t } = useT();
  if (!totalPages || totalPages <= 1) return null;

  const pages = computePageList(currentPage, totalPages);

  const linkCls = "min-w-[36px] h-9 px-2 inline-flex items-center justify-center rounded-md text-sm border transition-colors";
  const inactive = "bg-zinc-900 border-zinc-800 text-zinc-300 hover:bg-zinc-800 hover:text-zinc-50";
  const active = "bg-rose-600 border-rose-500 text-white font-semibold";
  const disabled = "bg-zinc-950 border-zinc-900 text-zinc-700 cursor-not-allowed pointer-events-none";

  // Reusable renderer — falls back to <button> when no buildHref is supplied.
  const renderCell = (page, opts = {}) => {
    const { key, testid, ariaLabel, ariaCurrent, className, children, isDisabled } = opts;
    if (buildHref) {
      return (
        <Link
          key={key}
          to={buildHref(page)}
          className={`${linkCls} ${className}`}
          data-testid={testid}
          aria-label={ariaLabel}
          aria-current={ariaCurrent}
        >
          {children}
        </Link>
      );
    }
    return (
      <button
        key={key}
        type="button"
        disabled={isDisabled}
        onClick={() => !isDisabled && onPageChange?.(page)}
        className={`${linkCls} ${className}`}
        data-testid={testid}
        aria-label={ariaLabel}
        aria-current={ariaCurrent}
      >
        {children}
      </button>
    );
  };

  return (
    <nav className="flex justify-center mt-10" aria-label="Pagination" data-testid="pagination">
      <div className="flex flex-wrap items-center gap-2">
        {renderCell(Math.max(1, currentPage - 1), {
          key: "prev",
          testid: "pagination-prev",
          ariaLabel: t("page.previous"),
          className: currentPage === 1 ? disabled : inactive,
          isDisabled: currentPage === 1,
          children: <ChevronLeft size={16} />,
        })}
        {pages.map((p, i) =>
          p === "..." ? (
            <span key={`gap-${i}`} className="px-2 text-zinc-500 select-none">…</span>
          ) : (
            renderCell(p, {
              key: p,
              testid: p === currentPage ? "pagination-current" : `pagination-page-${p}`,
              ariaCurrent: p === currentPage ? "page" : undefined,
              className: p === currentPage ? active : inactive,
              children: p,
            })
          )
        )}
        {renderCell(Math.min(totalPages, currentPage + 1), {
          key: "next",
          testid: "pagination-next",
          ariaLabel: t("page.next"),
          className: currentPage === totalPages ? disabled : inactive,
          isDisabled: currentPage === totalPages,
          children: <ChevronRight size={16} />,
        })}
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
