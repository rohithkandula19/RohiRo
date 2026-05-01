import type { Metadata } from "next";
import "./globals.css";
import { TopNav } from "@/components/nav/TopNav";
import { CommandPaletteProvider } from "@/components/nav/CommandPaletteProvider";

export const metadata: Metadata = {
  title: "ro",
  description: "one agent. your whole life.",
  manifest: "/manifest.json",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body>
        <CommandPaletteProvider>
          <TopNav />
          <main className="mx-auto max-w-[1200px] px-6 py-10">{children}</main>
        </CommandPaletteProvider>
      </body>
    </html>
  );
}
