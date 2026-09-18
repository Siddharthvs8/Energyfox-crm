import type { Metadata, Viewport } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "EnergyFox CRM",
  description: "EnergyFox sales CRM — manage leads, calls, and the solar sales pipeline.",
  manifest: "/manifest.webmanifest",
  applicationName: "EnergyFox",
  // On a phone the CRM is meant to be used from the home screen, full screen,
  // with no browser chrome — the same four tabs the bottom bar shows.
  appleWebApp: {
    capable: true,
    title: "EnergyFox",
    statusBarStyle: "default",
  },
  // Safari turns anything that looks like a phone number into a blue link,
  // which mangles IDs, amounts and dates all over the tables.
  formatDetection: { telephone: false },
};

export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
  // Pinch-zoom stays available (accessibility); it is only the automatic zoom
  // on focusing an input that the 16px font rule in globals.css prevents.
  maximumScale: 5,
  userScalable: true,
  // Lets the layout paint under the notch / home indicator; every fixed bar
  // then pads itself back out with env(safe-area-inset-*).
  viewportFit: "cover",
  themeColor: [
    { media: "(prefers-color-scheme: light)", color: "#f5f7fb" },
    { media: "(prefers-color-scheme: dark)", color: "#0b1220" },
  ],
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" className="h-full antialiased">
      <head>
        <link rel="preconnect" href="https://fonts.googleapis.com" />
        <link
          rel="preconnect"
          href="https://fonts.gstatic.com"
          crossOrigin="anonymous"
        />
        <link
          href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800;900&family=Space+Grotesk:wght@400;500;600;700&display=swap"
          rel="stylesheet"
        />
        <link rel="apple-touch-icon" href="/energyfox-mark.png" />
      </head>
      <body className="min-h-full flex flex-col">{children}</body>
    </html>
  );
}
