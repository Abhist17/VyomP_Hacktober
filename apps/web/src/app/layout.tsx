import type { Metadata, Viewport } from "next";
import "@fontsource-variable/manrope";
import "./globals.css";

export const metadata: Metadata = {
  title: "Viveka — Voucher intelligence for VYOM+",
  description:
    "Classify your transaction ledger, review the evidence and export clear voucher decisions with Viveka.",
  robots: { index: false, follow: false },
};
export const viewport: Viewport = { themeColor: "#080808", colorScheme: "dark" };

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
