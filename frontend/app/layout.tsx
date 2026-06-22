import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "ShirtPost — Admin",
  description: "Internal trend radar + factory queue.",
  robots: { index: false, follow: false },
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
