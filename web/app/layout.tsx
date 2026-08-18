import type { Metadata } from "next";
import "./globals.css";
import { Sidebar } from "@/components/nav/Sidebar";
import { CommandPaletteProvider } from "@/components/nav/CommandPaletteProvider";

export const metadata: Metadata = {
  title: "ro",
  description: "your personal agent.",
  manifest: "/manifest.json",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en" suppressHydrationWarning>
      <body>
        <script
          dangerouslySetInnerHTML={{
            __html: "try{var t=localStorage.getItem('ro-theme');if(t)document.documentElement.dataset.theme=t}catch(e){}",
          }}
        />
        <CommandPaletteProvider>
          <div className="flex h-screen overflow-hidden">
            <Sidebar />
            <main className="min-w-0 flex-1">{children}</main>
          </div>
        </CommandPaletteProvider>
      </body>
    </html>
  );
}
