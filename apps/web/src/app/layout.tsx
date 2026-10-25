import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "SecondLook",
  description: "Review football evidence against the source clip.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
