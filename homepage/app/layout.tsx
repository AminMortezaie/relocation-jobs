import type { Metadata } from "next";
import { Inter } from "next/font/google";
import "./globals.css";

const inter = Inter({
  subsets: ["latin"],
  weight: ["400", "500", "600", "700"],
  variable: "--font-inter",
  display: "swap",
});

export const metadata: Metadata = {
  title: "Relocation Jobs",
  description:
    "Find visa-sponsored engineering roles in Europe. Search relocation-friendly openings, track applications, and tailor your CV per job.",
  icons: {
    icon: [{ url: "/icon.svg", type: "image/svg+xml" }],
  },
  openGraph: {
    title: "Relocation Jobs",
    description:
      "Find visa-sponsored engineering roles in Europe — before they're gone.",
    url: "https://kuchup.com/",
    siteName: "Relocation Jobs",
    type: "website",
  },
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" className={inter.variable}>
      <body className="min-h-screen">{children}</body>
    </html>
  );
}
