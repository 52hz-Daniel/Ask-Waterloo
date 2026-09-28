import type { Metadata } from "next";
import "./styles.css";

export const metadata: Metadata = {
  title: "Academic Navigator — Synthetic Demo",
  description: "Fixture-only architecture proof",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}

