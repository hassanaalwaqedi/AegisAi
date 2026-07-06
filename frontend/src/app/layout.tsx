import type { Metadata } from "next";
import { Providers } from "@/app/providers";
import "./globals.css";

export const metadata: Metadata = {
  title: "AegisAI | Risk Intelligence Dashboard",
  description: "A real-time AI security risk detection dashboard for smart city operations."
};

export default function RootLayout({
  children
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <body>
        <Providers>{children}</Providers>
      </body>
    </html>
  );
}
