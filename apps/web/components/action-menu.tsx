"use client";

import { useEffect, useLayoutEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";

export interface MenuAction {
  label: string;
  icon?: string;
  danger?: boolean;
  onSelect: () => void;
}

interface Pos {
  top?: number;
  bottom?: number;
  left: number;
}

const MENU_WIDTH = 200;
const ITEM_H = 40;
const PADDING = 8;

/**
 * A "⋯" action menu whose popup is rendered in a portal on <body> with fixed
 * positioning. This escapes any `overflow:hidden`/clipping ancestor (e.g. the
 * dashboard cards) and viewport/page boundaries, and it auto-flips above the
 * trigger when there isn't room below (e.g. the last item on the page).
 */
export function ActionMenu({ items, ariaLabel = "Actions", busy = false }: {
  items: MenuAction[];
  ariaLabel?: string;
  busy?: boolean;
}) {
  const [open, setOpen] = useState(false);
  const [pos, setPos] = useState<Pos | null>(null);
  const btnRef = useRef<HTMLButtonElement>(null);

  const place = () => {
    const btn = btnRef.current;
    if (!btn) return;
    const rect = btn.getBoundingClientRect();
    const menuH = items.length * ITEM_H + PADDING;
    const spaceBelow = window.innerHeight - rect.bottom;
    const left = Math.max(
      PADDING,
      Math.min(rect.right - MENU_WIDTH, window.innerWidth - MENU_WIDTH - PADDING),
    );
    // Flip up if not enough room below but there is room above.
    if (spaceBelow < menuH + PADDING && rect.top > menuH + PADDING) {
      setPos({ bottom: window.innerHeight - rect.top + 4, left });
    } else {
      setPos({ top: rect.bottom + 4, left });
    }
  };

  useLayoutEffect(() => {
    if (open) place();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open]);

  useEffect(() => {
    if (!open) return;
    const close = () => setOpen(false);
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && close();
    // Recompute is complex on scroll; closing is the simplest correct behaviour.
    window.addEventListener("scroll", close, true);
    window.addEventListener("resize", close);
    window.addEventListener("keydown", onKey);
    return () => {
      window.removeEventListener("scroll", close, true);
      window.removeEventListener("resize", close);
      window.removeEventListener("keydown", onKey);
    };
  }, [open]);

  return (
    <>
      <button
        ref={btnRef}
        aria-label={ariaLabel}
        aria-haspopup="menu"
        aria-expanded={open}
        disabled={busy}
        onClick={() => setOpen((o) => !o)}
        className="flex h-8 w-8 items-center justify-center rounded-lg border border-border text-muted hover:text-fg disabled:opacity-50"
      >
        {busy ? (
          <span className="h-3 w-3 animate-spin rounded-full border-2 border-muted border-t-transparent" />
        ) : (
          <span className="text-lg leading-none">⋯</span>
        )}
      </button>

      {open &&
        pos &&
        typeof document !== "undefined" &&
        createPortal(
          <>
            <div className="fixed inset-0 z-[100]" onClick={() => setOpen(false)} />
            <div
              role="menu"
              style={{
                position: "fixed",
                top: pos.top,
                bottom: pos.bottom,
                left: pos.left,
                width: MENU_WIDTH,
              }}
              className="z-[101] overflow-hidden rounded-lg border border-border bg-surface shadow-card animate-in"
            >
              {items.map((item, i) => (
                <button
                  key={i}
                  role="menuitem"
                  onClick={() => {
                    setOpen(false);
                    item.onSelect();
                  }}
                  className={`flex w-full items-center gap-2 px-3 py-2 text-left text-sm hover:bg-elevated ${
                    item.danger ? "text-danger hover:bg-danger/10" : ""
                  }`}
                >
                  {item.icon && <span className="w-4 text-center">{item.icon}</span>}
                  {item.label}
                </button>
              ))}
            </div>
          </>,
          document.body,
        )}
    </>
  );
}
