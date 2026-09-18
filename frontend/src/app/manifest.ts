import type { MetadataRoute } from "next";

/**
 * Installable web app manifest. Added so the CRM can be kept on a phone's home
 * screen and open without browser chrome — with the bottom tab bar and the
 * hamburger drawer it then reads as an app rather than a site.
 */
export default function manifest(): MetadataRoute.Manifest {
  return {
    name: "EnergyFox CRM",
    short_name: "EnergyFox",
    description: "Leads, calls and tasks for the EnergyFox sales team.",
    start_url: "/",
    scope: "/",
    display: "standalone",
    orientation: "portrait-primary",
    background_color: "#f5f7fb",
    theme_color: "#0f1629",
    icons: [
      { src: "/energyfox-mark.png", sizes: "any", type: "image/png", purpose: "any" },
      { src: "/energyfox-mark.png", sizes: "any", type: "image/png", purpose: "maskable" },
    ],
  };
}
