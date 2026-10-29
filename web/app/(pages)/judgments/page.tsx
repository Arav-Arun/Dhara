"use client";

import Link from "next/link";
import { Suspense, useCallback, useEffect, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { API, label } from "@/lib/api";
import { Button, Heading, field, titleCase } from "@/components/ui";

type Hit = { id: string; title: string; decided_on: string; citation: string; mentions: number; via: string[]; snippet: string };
type Page = { mode: "section" | "topic" | "all"; items: Hit[]; more: boolean };

const SORTS: [string, string][] = [["relevance", "Most relevant"], ["newest", "Newest first"], ["oldest", "Oldest first"]];
const NEW_CODES = "2024-07-01";
const FIRST = 1950;
const LAST = new Date().getFullYear();

function Judgments()
{
    const params = useSearchParams();
    const router = useRouter();
    const asked = params.get("q") ?? "";
    const [q, setQ] = useState(asked);
    const [from, setFrom] = useState("");
    const [to, setTo] = useState("");
    const [recent, setRecent] = useState(false);
    const [sort, setSort] = useState("relevance");
    const [page, setPage] = useState<Page | null>(null);
    const [loading, setLoading] = useState(false);

    // a year counts once all four digits are in, so typing doesn't refetch on every keystroke
    const year = (y: string) => (/^\d{4}$/.test(y) ? y : "");
    const after = recent ? NEW_CODES : year(from) ? `${from}-01-01` : "";
    const before = !recent && year(to) ? `${to}-12-31` : "";

    const load = useCallback(async (offset: number) =>
    {
        setLoading(true);
        const qs = new URLSearchParams({ q: asked, after, before, sort, offset: String(offset) });
        const r = await fetch(`${API}/v1/judgments?${qs}`).catch(() => null);
        const next: Page = r?.ok ? await r.json() : { mode: "all", items: [], more: false };
        setPage((prev) => (offset && prev ? { ...next, items: [...prev.items, ...next.items] } : next));
        setLoading(false);
    }, [asked, after, before, sort]);

    useEffect(() =>
    {
        const t = setTimeout(() => load(0), 0);
        return () => clearTimeout(t);
    }, [load]);

    const search = (e: React.FormEvent) =>
    {
        e.preventDefault();
        router.push(`/judgments?q=${encodeURIComponent(q.trim())}`);
    };

    return (
        <div className="mx-auto max-w-3xl">
            <Heading sub="Search by section (old or new number), case name, report citation or topic. A new-code section finds the judgments on the old one, and every reference inside a judgment shows today’s number.">
                Judgments in today’s numbers
            </Heading>
            <form onSubmit={search} className="flex gap-2">
                <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="BNS 316, Arnesh Kumar, [2014] 8 S.C.R. 128, or anticipatory bail"
                    className={`${field} flex-1`} />
                <Button type="submit">Search</Button>
            </form>

            <div className="mt-4 flex flex-wrap items-center gap-x-5 gap-y-3 text-sm text-graphite">
                <label className="flex items-center gap-2">
                    <input type="checkbox" checked={recent} onChange={(e) => setRecent(e.target.checked)} className="accent-[#23238f]" />
                    Decided since 1 July 2024
                </label>
                <span className={`flex items-center gap-2 ${recent ? "opacity-40" : ""}`}>
                    Years
                    <Year value={from} onChange={setFrom} disabled={recent} placeholder={String(FIRST)} />
                    to
                    <Year value={to} onChange={setTo} disabled={recent} placeholder={String(LAST)} />
                </span>
                <label className="ml-auto flex items-center gap-2">
                    Sort
                    <select value={sort} onChange={(e) => setSort(e.target.value)} className="rounded-[4px] border border-rule bg-sheet px-2 py-1 text-ink outline-none focus:border-stamp">
                        {SORTS.map(([v, name]) => <option key={v} value={v}>{name}</option>)}
                    </select>
                </label>
            </div>

            <p className="mt-8 text-sm text-graphite">{summary(page, asked, loading)}</p>
            <ol className="mt-3 divide-y divide-rule border-y border-rule">
                {page?.items.map((h) => (
                    <li key={h.id}>
                        <Link href={`/judgments/${encodeURIComponent(h.id)}`} className="block py-4 hover:bg-sheet/60">
                            <p className="font-serif text-[17px] leading-snug font-semibold">{titleCase(h.title)}</p>
                            <p className="figures mt-1 text-[13px] text-graphite">
                                {h.decided_on.slice(0, 4)} · {h.citation || h.id}
                                {h.via.length > 0 && <> · cites {h.via.slice(0, 3).map(label).join(", ")}{h.mentions > 1 ? `, ${h.mentions} times` : ""}</>}
                            </p>
                            {h.snippet && <p className="mt-2 line-clamp-2 font-serif text-[15px] leading-relaxed text-ink/75">{h.snippet}</p>}
                        </Link>
                    </li>
                ))}
                {page && page.items.length === 0 && !loading && <li className="py-4 text-graphite">Nothing found. Try a section number, old or new, part of the case name, or fewer filters.</li>}
            </ol>
            {page?.more && (
                <div className="mt-6 text-center">
                    <button onClick={() => load(page.items.length)} disabled={loading}
                        className="rounded-[4px] border border-rule bg-sheet px-5 py-2 text-sm hover:border-stamp hover:text-stamp disabled:opacity-50">
                        {loading ? "Loading" : "Show more"}
                    </button>
                </div>
            )}
        </div>
    );
}

function Year({ value, onChange, disabled, placeholder }: { value: string; onChange: (v: string) => void; disabled: boolean; placeholder: string })
{
    return (
        <input type="number" min={FIRST} max={LAST} value={value} disabled={disabled} placeholder={placeholder}
            onChange={(e) => onChange(e.target.value.slice(0, 4))}
            className="figures w-[76px] rounded-[4px] border border-rule bg-sheet px-2 py-1 text-ink outline-none focus:border-stamp" />
    );
}

function summary(page: Page | null, asked: string, loading: boolean): string
{
    if (!page)
    {
        return "Searching";
    }
    const n = `${page.items.length}${page.more ? "+" : ""} judgments`;
    if (page.mode === "section")
    {
        return `${n} citing ${asked} or its counterpart in the other code`;
    }
    if (page.mode === "topic")
    {
        return `${n} on “${asked}”, found by the same search as Research`;
    }
    return loading ? "Loading" : `${n}`;
}

export default function JudgmentsPage()
{
    return <Suspense><Judgments /></Suspense>;
}
