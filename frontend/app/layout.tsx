import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Prescription Intelligence",
  description:
    "AI-powered prescription analysis and medication intelligence platform.",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}