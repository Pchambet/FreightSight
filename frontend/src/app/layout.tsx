import { ClerkProvider } from "@clerk/nextjs";
import type { Metadata } from "next";
import { Geist, Geist_Mono } from "next/font/google";
import { Toaster } from "sonner";
import "./globals.css";

const geistSans = Geist({ variable: "--font-geist-sans", subsets: ["latin"] });
const geistMono = Geist_Mono({ variable: "--font-geist-mono", subsets: ["latin"] });

// Every page reads live, per-user data: never prerender at build time.
export const dynamic = "force-dynamic";

export const metadata: Metadata = {
  title: { default: "FreightSight", template: "%s · FreightSight" },
  description: "Landed cost allocation and container tracking for SMB importers. Pre-alpha.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className={`${geistSans.variable} ${geistMono.variable} h-full antialiased`}>
      <body className="min-h-full flex flex-col bg-slate-50 text-slate-900">
        <ClerkProvider taskUrls={{ "choose-organization": "/choose-organization" }} afterSignOutUrl="/sign-in">
          {children}
          <Toaster position="top-right" richColors />
        </ClerkProvider>
      </body>
    </html>
  );
}
