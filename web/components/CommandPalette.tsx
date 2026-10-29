"use client";

import { useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { usePathname, useRouter } from "next/navigation";
import { API, href, label } from "@/lib/api";
import { titleCase } from "@/components/ui";

type Section = { id: string; heading: string; other: string[] };
type Judgment = { id: string; title: string; year: string; citation: string };
type Entry = { key: string; group: string; to: string; main: React.ReactNode; side?: React.ReactNode };

const OLD = /^(IPC|CRPC|IEA):/;

// other parts of the page open the palette by dispatching this event
const FIND = "dhara:find";

export function openFinder()
{
    window.dispatchEvent(new Event(FIND));
}

const TRY: [string, string][] = [["IPC 302", "murder, under the old code"], ["BNSS 528", "the High Court’s inherent powers"], ["438 CrPC", "anticipatory bail"], ["Evidence Act 65B", "electronic records"]];
const PAGES: [string, string, string][] = [["/research", "Research", "Ask a question in your own words"], ["/judgments", "Judgments", "Search Supreme Court judgments"], ["/check", "Check a draft", "Find outdated citations in a draft"]];

const BUTTON = "flex items-center gap-4 rounded-[4px] border border-rule bg-sheet px-3 py-1.5 text-sm text-graphite hover:border-ink hover:text-ink";

// shown while the palette loads: it reads the URL, so it renders in the browser only
export function FinderPlaceholder()
{
    return (
        <span className={BUTTON}>
            <span>Find a section</span>
            <kbd className="rounded border border-rule px-1.5 font-[system-ui] text-[12px] leading-5 text-graphite">Ctrl K</kbd>
        </span>
    );
}

// ⌘K / Ctrl+K from anywhere: a section by number in either code or by heading, a judgment by
// name or citation, or the question itself sent to Research or to judgment search.
export default function CommandPalette()
{
    const [open, setOpen] = useState(false);
    const [q, setQ] = useState("");
    const [found, setFound] = useState<{ sections: Section[]; judgments: Judgment[] } | null>(null);
    const [loading, setLoading] = useState(false);
    const [active, setActive] = useState(0);
    const input = useRef<HTMLInputElement>(null);
    const list = useRef<HTMLDivElement>(null);
    const router = useRouter();
    const path = usePathname();
    // ⌘ on a Mac, Ctrl elsewhere; decided in the browser, so the server renders the neutral form
    const [shortcut, setShortcut] = useState("Ctrl K");

    useEffect(() =>
    {
        const t = setTimeout(() => setShortcut(/Mac|iPhone|iPad/.test(navigator.platform) ? "⌘ K" : "Ctrl K"), 0);
        return () => clearTimeout(t);
    }, []);

    useEffect(() =>
    {
        const onKey = (e: KeyboardEvent) =>
        {
            if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k")
            {
                e.preventDefault();
                setOpen((o) => !o);
            }
            if (e.key === "Escape")
            {
                setOpen(false);
            }
        };
        const onFind = () => setOpen(true);
        window.addEventListener("keydown", onKey);
        window.addEventListener(FIND, onFind);
        return () =>
        {
            window.removeEventListener("keydown", onKey);
            window.removeEventListener(FIND, onFind);
        };
    }, []);

    // close on navigation; while open, the page behind doesn't scroll
    useEffect(() =>
    {
        const t = setTimeout(() => setOpen(false), 0);
        return () => clearTimeout(t);
    }, [path]);

    useEffect(() =>
    {
        if (!open)
        {
            return;
        }
        input.current?.select();
        const before = document.body.style.overflow;
        document.body.style.overflow = "hidden";
        return () =>
        {
            document.body.style.overflow = before;
        };
    }, [open]);

    useEffect(() =>
    {
        const text = q.trim();
        const t = setTimeout(async () =>
        {
            if (!text)
            {
                setFound(null);
                setActive(0);
                return;
            }
            setLoading(true);
            const res = await fetch(`${API}/v1/search?q=${encodeURIComponent(text)}`).catch(() => null);
            setFound(res?.ok ? await res.json() : { sections: [], judgments: [] });
            setActive(0);
            setLoading(false);
        }, text ? 120 : 0);
        return () => clearTimeout(t);
    }, [q]);

    const text = q.trim();
    const entries: Entry[] = text
        ? [
            ...(found?.sections ?? []).map((s) => ({
                key: s.id,
                group: "Sections",
                to: href(s.id),
                main: <><span className={`figures shrink-0 font-medium whitespace-nowrap ${OLD.test(s.id) ? "text-old" : "text-stamp"}`}>{label(s.id)}</span><span className="ml-3 truncate text-ink/80">{s.heading}</span></>,
                side: s.other.length > 0 && <span className="figures text-[12px] whitespace-nowrap text-graphite">{OLD.test(s.id) ? "now" : "was"} {s.other.map(label).join(", ")}</span>,
            })),
            ...(found?.judgments ?? []).map((j) => ({
                key: j.id,
                group: "Judgments",
                to: `/judgments/${encodeURIComponent(j.id)}`,
                main: <span className="truncate font-serif">{titleCase(j.title)}</span>,
                side: <span className="figures text-[12px] text-graphite">{j.year}</span>,
            })),
            { key: "ask", group: "Ask", to: `/research?q=${encodeURIComponent(text)}`, main: <span>Ask in Research: <span className="text-stamp">“{text}”</span></span> },
            { key: "judge", group: "Ask", to: `/judgments?q=${encodeURIComponent(text)}`, main: <span>Search judgments for <span className="text-stamp">“{text}”</span></span> },
        ]
        : [
            ...TRY.map(([t, what]) => ({ key: t, group: "Try", to: "", main: <span className="figures font-medium text-ink">{t}</span>, side: <span className="text-[12px] text-graphite">{what}</span> })),
            ...PAGES.map(([to, name, what]) => ({ key: to, group: "Go to", to, main: <span>{name}</span>, side: <span className="text-[12px] text-graphite">{what}</span> })),
        ];

    const go = (e: Entry) =>
    {
        if (!e.to)
        {
            setQ(e.key); // a suggestion fills the box rather than leaving the palette
            input.current?.focus();
            return;
        }
        setOpen(false);
        router.push(e.to);
    };

    const move = (step: number) =>
    {
        const next = (active + step + entries.length) % entries.length;
        setActive(next);
        list.current?.querySelector(`[data-i="${next}"]`)?.scrollIntoView({ block: "nearest" });
    };

    return (
        <>
            <button
                onClick={() => setOpen(true)}
                className={BUTTON}
            >
                <span>Find a section</span>
                <kbd className="rounded border border-rule px-1.5 font-[system-ui] text-[12px] leading-5 text-graphite">{shortcut}</kbd>
            </button>
            {/* portalled to <body>: the header's backdrop blur would otherwise clip a fixed overlay to the header */}
            {open && createPortal(
                <div className="fixed inset-0 z-50 bg-ink/30 px-4 pt-[12vh] backdrop-blur-[3px]" onClick={() => setOpen(false)}>
                    <div role="dialog" aria-label="Find a section or judgment"
                        className="mx-auto max-w-[620px] overflow-hidden rounded-[12px] border border-rule bg-sheet shadow-[0_30px_80px_-20px_rgba(20,20,60,.45)]"
                        onClick={(e) => e.stopPropagation()}>
                        <div className="flex items-center gap-3 border-b border-rule px-4">
                            <svg width="18" height="18" viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth="1.6" className="shrink-0 text-graphite" aria-hidden="true"><circle cx="9" cy="9" r="6" /><path d="m14 14 4 4" /></svg>
                            <input
                                ref={input}
                                value={q}
                                onChange={(e) => setQ(e.target.value)}
                                onKeyDown={(e) =>
                                {
                                    if (e.key === "ArrowDown" || e.key === "ArrowUp")
                                    {
                                        e.preventDefault();
                                        move(e.key === "ArrowDown" ? 1 : -1);
                                    }
                                    if (e.key === "Enter" && entries[active])
                                    {
                                        go(entries[active]);
                                    }
                                }}
                                placeholder="A section, old or new: 302, BNS 103, cheating, or a case name"
                                aria-label="Search"
                                style={{ outline: "none" }} // the dialog itself shows where focus is
                                className="h-14 w-full bg-transparent text-[16px] placeholder:text-graphite/70"
                            />
                            {loading
                                ? <span className="h-4 w-4 shrink-0 animate-spin rounded-full border-2 border-rule border-t-stamp" aria-hidden="true" />
                                : <kbd className="shrink-0 rounded border border-rule px-1.5 font-[system-ui] text-[11px] leading-5 text-graphite">esc</kbd>}
                        </div>

                        <div ref={list} className="max-h-[min(420px,60vh)] overflow-y-auto py-2">
                            {entries.map((e, i) => (
                                <div key={e.group + e.key}>
                                    {(i === 0 || entries[i - 1].group !== e.group) && (
                                        <p className="px-4 pt-3 pb-1 text-[12px] text-graphite">{e.group}</p>
                                    )}
                                    <button
                                        data-i={i}
                                        onClick={() => go(e)}
                                        onMouseMove={() => setActive(i)}
                                        className={`mx-2 flex w-[calc(100%-16px)] items-center justify-between gap-4 rounded-[6px] px-3 py-2 text-left text-[14px] ${i === active ? "bg-stamp-wash" : ""}`}
                                    >
                                        <span className="flex min-w-0 items-baseline">{e.main}</span>
                                        {e.side && <span className="shrink-0">{e.side}</span>}
                                    </button>
                                </div>
                            ))}
                            {text && found && found.sections.length === 0 && found.judgments.length === 0 && !loading && (
                                <p className="px-4 pt-1 pb-2 text-[13px] text-graphite">No section or case name matches; ask it as a question instead.</p>
                            )}
                        </div>

                        <div className="flex items-center gap-4 border-t border-rule bg-paper px-4 py-2 text-[12px] text-graphite">
                            <span><Key>↑</Key><Key>↓</Key> move</span>
                            <span><Key>↵</Key> open</span>
                            <span><Key>esc</Key> close</span>
                            <span className="ml-auto hidden sm:inline">Sections show their counterpart in the other code</span>
                        </div>
                    </div>
                </div>,
                document.body,
            )}
        </>
    );
}

function Key({ children }: { children: React.ReactNode })
{
    return <kbd className="mr-1 rounded border border-rule bg-sheet px-1 font-[system-ui] text-[11px]">{children}</kbd>;
}
