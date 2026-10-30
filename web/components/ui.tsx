import Link from "next/link";
import { href, label } from "@/lib/api";

const OLD = new Set(["IPC", "CRPC", "IEA"]);

// A section reference set like print: new-code numbers in stamp blue, old-code numbers in brown.
export function Ref({ id, link = true }: { id: string; link?: boolean })
{
    const old = OLD.has(id.split(":")[0]);
    const text = <span className={`figures font-medium ${old ? "text-old" : "text-stamp"}`}>{label(id)}</span>;
    return link ? <Link href={href(id)} className="underline-offset-4 hover:underline">{text}</Link> : text;
}

const STATUS: Record<string, [string, string]> =
    {
        in_force: ["bg-green", "In force"],
        not_commenced: ["bg-amber", "Not yet in force"],
        omitted: ["bg-redtape", "Omitted"],
        repealed: ["bg-redtape", "Repealed"],
    };

export function Status({ status, note }: { status: string; note?: string })
{
    const [dot, text] = STATUS[status] ?? ["bg-graphite", status];
    return (
        <span className="inline-flex items-center gap-2 text-sm text-graphite">
            <span className={`h-1.5 w-1.5 rounded-full ${dot}`} />
            {text}{note ? `, ${note}` : ""}
        </span>
    );
}

const RELATION: Record<string, string> =
    {
        equivalent: "Same provision, renumbered",
        merged: "Merged with other sections",
        split: "Split across several sections",
        partial: "Partly moved",
        new: "New, no earlier counterpart",
        omitted: "Dropped from the new code",
    };

export function relation(r: string): string
{
    return RELATION[r] ?? r;
}

export function Heading({ children, sub }: { children: React.ReactNode; sub?: React.ReactNode })
{
    return (
        <header className="mx-auto mb-10 max-w-3xl text-center">
            <h1 className="text-[38px] leading-tight tracking-[-0.04em] sm:text-[48px]">{children}</h1>
            {sub && <p className="mt-3 text-[17px] leading-relaxed text-graphite">{sub}</p>}
        </header>
    );
}

export function Button({ children, className = "", ...props }: React.ButtonHTMLAttributes<HTMLButtonElement>)
{
    return (
        <button {...props}
            className={`rounded-[4px] bg-[#1d1d3a] px-5 py-2 text-sm text-white hover:bg-stamp disabled:opacity-50 ${className}`}>
            {children}
        </button>
    );
}

export const field = "rounded-[4px] border border-rule bg-sheet px-3 py-2 outline-none focus:border-stamp";

const SMALL = new Set(["of", "the", "and", "or", "to", "in", "on", "by", "for", "at", "a", "an", "v.", "with", "under"]);

// Court titles and chapter names arrive in capitals or naive title case; print them the way a law report would.
export function titleCase(t: string): string
{
    // initials such as C.B.I., U.P. or B.S. stay in capitals
    return t.toLowerCase().split(/\s+/).map((w, i) =>
        /^\(?([a-z]\.){2,}[a-z]?[),]*$/.test(w) ? w.toUpperCase()
            : i > 0 && SMALL.has(w) ? w : w.charAt(0).toUpperCase() + w.slice(1)).join(" ").replace(/\bVersus\b/i, "v.");
}

// A link out to the official source, so any text on the site can be checked against the original.
export function Source({ href: to, children }: { href: string; children: React.ReactNode })
{
    return (
        <a href={to} target="_blank" rel="noopener" className="inline-flex items-center gap-1 text-[13px] text-stamp underline-offset-4 hover:underline">
            {children}
            <svg width="11" height="11" viewBox="0 0 12 12" fill="none" stroke="currentColor" strokeWidth="1.4" aria-hidden="true"><path d="M4.5 2.5h5v5M9.5 2.5l-7 7" /></svg>
        </a>
    );
}
