"use client";

import { useEffect, useRef, useState, type CSSProperties, type ReactNode } from "react";

export function prefersReducedMotion() {
  return (
    typeof window !== "undefined" && window.matchMedia("(prefers-reduced-motion: reduce)").matches
  );
}

/** Calls `onEnter` once, the first time the element scrolls into view. */
function useFirstView(onEnter: () => void, rootMargin = "0px 0px -12% 0px") {
  const ref = useRef<HTMLElement>(null);
  const callback = useRef(onEnter);
  useEffect(() => {
    callback.current = onEnter;
  });
  useEffect(() => {
    const node = ref.current;
    if (!node) return;
    const observer = new IntersectionObserver(
      ([entry]) => {
        if (!entry.isIntersecting) return;
        observer.disconnect();
        callback.current();
      },
      { rootMargin },
    );
    observer.observe(node);
    return () => observer.disconnect();
  }, [rootMargin]);
  return ref;
}

/**
 * Fades and lifts its content in the first time it scrolls into view. Reduced-motion users
 * see the content in place (handled in CSS), so nothing depends on the animation running.
 */
export function Reveal({
  children,
  className = "",
  delay = 0,
  as: Tag = "div",
}: {
  children: ReactNode;
  className?: string;
  delay?: number;
  as?: "div" | "section" | "li" | "span";
}) {
  const [visible, setVisible] = useState(false);
  const ref = useFirstView(() => setVisible(true));
  return (
    <Tag
      ref={ref as never}
      className={`reveal ${visible ? "is-visible" : ""} ${className}`}
      style={{ "--reveal-delay": `${delay}ms` } as CSSProperties}
    >
      {children}
    </Tag>
  );
}

/** Counts from zero to `value` the first time it is shown; later changes update in place. */
export function CountUp({
  value,
  format = (n: number) => Math.round(n).toLocaleString("en-IN"),
  duration = 1200,
}: {
  value: number;
  format?: (n: number) => string;
  duration?: number;
}) {
  const [frameValue, setFrameValue] = useState<number | null>(null);
  const latest = useRef(value);
  useEffect(() => {
    latest.current = value;
  });
  const ref = useFirstView(() => {
    if (prefersReducedMotion()) return;
    const start = performance.now();
    const tick = (now: number) => {
      const t = Math.min(1, (now - start) / duration);
      setFrameValue(t < 1 ? latest.current * (1 - Math.pow(1 - t, 3)) : null);
      if (t < 1) requestAnimationFrame(tick);
    };
    setFrameValue(0);
    requestAnimationFrame(tick);
  }, "0px");
  return (
    <span ref={ref as never}>
      <span className="sr-only">{format(value)}</span>
      <span aria-hidden="true">{format(frameValue ?? value)}</span>
    </span>
  );
}

/** A thin gold bar along the bottom of the window that tracks scroll position. */
export function ScrollProgress() {
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    let frame = 0;
    const update = () => {
      frame = 0;
      const max = document.documentElement.scrollHeight - window.innerHeight;
      const progress = max > 0 ? window.scrollY / max : 0;
      ref.current?.style.setProperty("--progress", String(Math.min(1, Math.max(0, progress))));
    };
    const schedule = () => {
      if (!frame) frame = requestAnimationFrame(update);
    };
    update();
    window.addEventListener("scroll", schedule, { passive: true });
    window.addEventListener("resize", schedule);
    return () => {
      window.removeEventListener("scroll", schedule);
      window.removeEventListener("resize", schedule);
      cancelAnimationFrame(frame);
    };
  }, []);
  return <div ref={ref} className="scroll-progress" aria-hidden="true" />;
}
