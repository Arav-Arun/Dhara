import type { Metadata } from "next";
import Link from "next/link";
import { Host_Grotesk, Literata } from "next/font/google";
import { Suspense } from "react";
import CommandPalette, { FinderPlaceholder } from "@/components/CommandPalette";
import Waking from "@/components/Waking";
import Logo from "@/components/Logo";
import "./globals.css";

const serif = Literata({ variable: "--font-literata", subsets: ["latin"], weight: ["400", "500", "600"], style: ["normal", "italic"] });
const sans = Host_Grotesk({ variable: "--font-host", subsets: ["latin"] });

export const metadata: Metadata =
    {
        title: { default: "Dhara: Indian criminal law across the old and new codes", template: "%s · Dhara" },
        description: "Statutes, the official IPC to BNS mapping, and Supreme Court precedent found under either numbering.",
    };

const NAV = [
    ["/research", "Research"],
    ["/judgments", "Judgments"],
    ["/check", "Check a draft"],
    ["/method", "Method"],
];

export default function RootLayout({ children }: LayoutProps<"/">)
{
    return (
        <html lang="en" className={`${serif.variable} ${sans.variable} h-full antialiased`}>
            <body className="flex min-h-full flex-col font-sans text-[15px]">
                <header className="sticky top-0 z-40 border-b border-rule/70 bg-paper/80 backdrop-blur">
                    <div className="mx-auto flex max-w-6xl flex-wrap items-center gap-x-8 gap-y-3 px-5 py-4">
                        <Logo />
                        <nav className="order-last flex w-full gap-5 overflow-x-auto text-sm whitespace-nowrap text-graphite md:order-none md:w-auto md:gap-6">
                            {NAV.map(([to, name]) => <Link key={to} href={to} className="hover:text-ink">{name}</Link>)}
                        </nav>
                        <div className="ml-auto"><Suspense fallback={<FinderPlaceholder />}><CommandPalette /></Suspense></div>
                    </div>
                </header>
                <main className="flex-1">{children}</main>
                <Waking />
                <footer className="border-t border-rule">
                    <div className="mx-auto max-w-6xl px-5 py-8 text-center text-[13px] text-graphite">
                        <p>Built by <a href="https://aravarun.in" target="_blank" rel="noopener" className="text-ink underline decoration-rule underline-offset-4 hover:text-stamp hover:decoration-stamp">Arav Arun</a></p>
                    </div>
                </footer>
            </body>
        </html>
    );
}
