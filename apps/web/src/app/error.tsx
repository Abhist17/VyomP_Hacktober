"use client";

export default function ErrorPage({ reset }: { reset: () => void }) {
  return (
    <main className="fatal-error">
      <h1>The workspace couldn&apos;t load.</h1>
      <p>Try again to restore the interface. Unsaved reviews may need to be repeated.</p>
      <button className="button primary" onClick={reset}>
        Try again
      </button>
    </main>
  );
}
