import Link from "next/link";

export default function NotFound() {
  return (
    <main className="fatal-error">
      <h1>This page isn&apos;t in the books.</h1>
      <p>Return to your voucher workspace to continue.</p>
      <Link className="button primary" href="/">
        Open workspace
      </Link>
    </main>
  );
}
