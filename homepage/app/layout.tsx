import type { Metadata } from "next";
import { JetBrains_Mono, Manrope } from "next/font/google";
import "./globals.css";

const manrope = Manrope({
  subsets: ["latin"],
  weight: ["400", "500", "600", "700", "800"],
  variable: "--font-body",
  display: "swap",
});

const jetbrains = JetBrains_Mono({
  subsets: ["latin"],
  weight: ["400", "500"],
  variable: "--font-mono",
  display: "swap",
});

export const metadata: Metadata = {
  metadataBase: new URL("https://kuchup.com"),
  title: {
    template: "%s | Relocation Jobs",
    default: "Relocation Jobs | Visa-Sponsored Software Roles in Europe",
  },
  description:
    "Find visa-sponsored software engineering roles in Europe. Search relocation-friendly openings in Germany, Netherlands, UK, Portugal, and Ireland. Track applications and tailor your CV with Claude or Cursor via MCP.",
  icons: {
    icon: [{ url: "/static/icons/kuchup-bird.svg", type: "image/svg+xml" }],
    apple: [{ url: "/static/icons/apple-touch-icon.png" }],
  },
  openGraph: {
    title: "Relocation Jobs",
    description:
      "Find visa-sponsored engineering roles in Europe — before they're gone.",
    url: "https://kuchup.com/",
    siteName: "Relocation Jobs",
    type: "website",
    locale: "en_GB",
  },
  twitter: {
    card: "summary",
    title: "Relocation Jobs",
    description:
      "Find visa-sponsored engineering roles in Europe — before they're gone.",
  },
  robots: {
    index: true,
    follow: true,
  },
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  const jsonLd = {
    "@context": "https://schema.org",
    "@graph": [
      {
        "@type": "Organization",
        name: "Relocation Jobs",
        alternateName: "KUCHUP",
        url: "https://kuchup.com/",
        description:
          "Curated visa-sponsored software engineering roles across Europe.",
        sameAs: ["https://github.com/AminMortezaie/relocation-jobs"],
      },
      {
        "@type": "WebSite",
        name: "Relocation Jobs",
        url: "https://kuchup.com/",
        description:
          "Find visa-sponsored software engineering roles in Germany, Netherlands, UK, Portugal, and Ireland.",
      },
    ],
  };

  return (
    <html lang="en" className={`${manrope.variable} ${jetbrains.variable}`}>
      <head>
        <link rel="preconnect" href="https://fonts.googleapis.com" />
        <link
          rel="preconnect"
          href="https://fonts.gstatic.com"
          crossOrigin="anonymous"
        />
        <link
          href="https://fonts.googleapis.com/css2?family=Lexend:wght@500;600;700&display=swap"
          rel="stylesheet"
        />
      </head>
      <body className={manrope.className}>
        <script
          type="application/ld+json"
          dangerouslySetInnerHTML={{ __html: JSON.stringify(jsonLd) }}
        />
        {children}
      </body>
    </html>
  );
}
