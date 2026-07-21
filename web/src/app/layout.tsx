import type { Metadata } from "next";
import { Geist } from "next/font/google";
import Nav from "@/components/Nav";
import "./globals.css";

const geist = Geist({ variable: "--font-geist", subsets: ["latin"] });

export const metadata: Metadata = {
  title: "CivicLens Cook County",
  description:
    "See every layer of local government for any Cook County address — who represents you, where the money goes, and what's on the next agenda.",
};

export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en" className={`${geist.variable} antialiased`}>
      <body className="min-h-screen flex flex-col bg-background text-foreground">
        <Nav />
        <main className="flex-1">{children}</main>
        <footer className="border-t border-border px-6 py-6 text-xs text-muted">
          <div className="max-w-5xl mx-auto flex flex-col sm:flex-row justify-between gap-2">
            <span>
              Data from Census TIGER/Line, IL Comptroller AFR, Cook County
              Clerk. Self-reported; may contain errors.
            </span>
            <a
              href="https://github.com/eshaambhattad-tech/civiclens"
              className="underline hover:text-accent"
              target="_blank"
            >
              Source on GitHub
            </a>
          </div>
        </footer>
      </body>
    </html>
  );
}
