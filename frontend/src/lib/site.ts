// Public site configuration. Safe for the client bundle: no secrets here.
export const site = {
  name: "FreightSight",
  tagline: "Le coût de revient rendu de vos importations, par commande et par SKU.",
  // Where the "Réserver 20 minutes" buttons go. Set NEXT_PUBLIC_BOOKING_URL (Cal.com, Calendly…)
  // on Vercel to replace the e-mail fallback.
  bookingUrl:
    process.env.NEXT_PUBLIC_BOOKING_URL ||
    "mailto:pierrechambet@gmail.com?subject=FreightSight%20%E2%80%93%2020%20minutes",
  appHome: "/containers",
  hostingRegion: "Amsterdam (UE)",
};
