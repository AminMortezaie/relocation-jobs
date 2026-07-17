import type { Metadata } from "next";
import { Inter, Manrope } from "next/font/google";
import "./globals.css";

const inter = Inter({
  subsets: ["latin"],
  weight: ["400", "500", "600", "700"],
  variable: "--font-inter",
  display: "swap",
});

const manrope = Manrope({
  subsets: ["latin"],
  weight: ["600", "700", "800"],
  variable: "--font-display",
  display: "swap",
});

export const metadata: Metadata = {
  metadataBase: new URL("https://kuchup.com"),
  title: {
    template: "%s | Relocation Jobs",
    default: "Relocation Jobs | Visa-Sponsored Software Roles in Europe",
  },
  description:
    "Find visa-sponsored software engineering roles in Europe. Search relocation-friendly openings in Germany, Netherlands, UK, Portugal, and Ireland. Track applications and tailor your CV.",
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
    <html lang="en" className={`${inter.variable} ${manrope.variable}`}>
      <head>
        <script
          type="application/ld+json"
          id="schema-org"
          dangerouslySetInnerHTML={{ __html: JSON.stringify(jsonLd) }}
        />
      </head>
      <body className="min-h-screen font-sans">{children}</body>
    </html>
  );
}
