import type { Metadata, Viewport } from "next";
import "@fontsource-variable/manrope";
import "./globals.css";

export const metadata: Metadata = {
  title: { default: "PayYard", template: "%s | PayYard" },
  description: "Attendance-to-payroll control for site-based workforces.",
  manifest: "/manifest.webmanifest",
};

export const viewport: Viewport = {
  themeColor: "#10281f",
  width: "device-width",
  initialScale: 1,
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
