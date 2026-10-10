"use client";

import { useEffect, useId, useRef, type ReactNode } from "react";
import { X } from "lucide-react";

export function Brand() {
  return (
    <div className="brand">
      <svg viewBox="0 0 40 46" fill="none" aria-hidden="true">
        <path d="M5 12 20 38 35 12M12 12l8 14 8-14" stroke="currentColor" strokeWidth="1.6" />
        <path d="M20 2v10M15 7h10" stroke="currentColor" strokeWidth="1.4" />
      </svg>
      <div>
        <span className="wordmark">
          VYOM<span>+</span>
        </span>
        <span className="brand-by">Value your own money</span>
      </div>
      <span className="brand-divider" />
      <span className="product-name">Viveka</span>
    </div>
  );
}

export function Dialog({
  title,
  children,
  onClose,
  wide = false,
}: {
  title: string;
  children: ReactNode;
  onClose: () => void;
  wide?: boolean;
}) {
  const ref = useRef<HTMLDialogElement>(null);
  const id = useId();
  useEffect(() => {
    const dialog = ref.current;
    dialog?.showModal();
    return () => dialog?.close();
  }, []);
  return (
    <dialog
      ref={ref}
      className={`dialog ${wide ? "dialog-wide" : ""}`}
      aria-labelledby={id}
      onCancel={(event) => {
        event.preventDefault();
        onClose();
      }}
      onClick={(event) => {
        if (event.target === event.currentTarget) onClose();
      }}
    >
      <div className="dialog-content">
        <div className="dialog-heading">
          <h2 id={id}>{title}</h2>
          <button className="icon-button" aria-label="Close dialog" onClick={onClose}>
            <X size={19} />
          </button>
        </div>
        {children}
      </div>
    </dialog>
  );
}

export function StatusBadge({ status }: { status: "review" | "ready" | "reviewed" | "corrected" }) {
  const label = {
    review: "Needs review",
    ready: "Ready",
    reviewed: "Reviewed",
    corrected: "Corrected",
  }[status];
  return (
    <span className={`status status-${status}`}>
      <span className="status-dot" />
      {label}
    </span>
  );
}
