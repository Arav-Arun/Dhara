"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { API, failure, href, label } from "@/lib/api";

type Mention = { raw: string; id: string; other: string[] };
export type Passage = { n: string; id: string; role: string; text: string; refs: Mention[] };
type Point = { text: string; cites: string[] };
type Brief = { facts: Point | null; issue: Point | null; held: Point[]; cite_for: Point[] };
type Reply = { found: boolean; answer: string; points: Point[]; read: string[] };

const OLD = /^(IPC|CRPC|IEA):/;
// "P12", "[P12]", "(P11, P12)" written into the model's text
const MARK = /\s*[[(]?(?<![A-Za-z])(P\d+(?:\s*,\s*P\d+)*)[\])]?(?=[\s.,;:]|$)/g;

// The judgment as something to work with rather than scroll through: a cited brief, questions
// answered from its own passages, and the text itself folded away until a citation opens it.
export default function JudgmentReader({ jid, passages, citeAs }: { jid: string; passages: Passage[]; citeAs: string })
{
    const [brief, setBrief] = useState<Brief | null | string>(null);
    const [question, setQuestion] = useState("");
    const [reply, setReply] = useState<Reply | null>(null);
    const [asking, setAsking] = useState(false);
    const [lit, setLit] = useState<string | null>(null);
    const full = useRef<HTMLDetailsElement>(null);

    useEffect(() =>
    {
        let live = true;
        fetch(`${API}/v1/judgments/${encodeURIComponent(jid)}/brief`)
            .then(async (r) => (r.ok ? ((await r.json()) as Brief) : failure(r.status)))
            .then((b) => live && setBrief(typeof b === "string" || b.held ? b : failure(0)))
            .catch(() => live && setBrief(failure(0)));
        return () =>
        {
            live = false;
        };
    }, [jid]);

    const show = (n: string) =>
    {
        if (full.current)
        {
            full.current.open = true;
        }
        setLit(n);
        setTimeout(() => document.getElementById(`p-${n}`)?.scrollIntoView({ behavior: "smooth", block: "center" }), 50);
    };

    const ask = async () =>
    {
        if (!question.trim())
        {
            return;
        }
        setAsking(true);
        setReply(null);
        const r = await fetch(`${API}/v1/judgments/${encodeURIComponent(jid)}/ask`, {
            method: "POST",
            headers: { "content-type": "application/json" },
            body: JSON.stringify({ question }),
        }).catch(() => null);
        setReply(r?.ok ? await r.json() : { found: false, answer: failure(r?.status ?? 0), points: [], read: [] });
        setAsking(false);
    };

    const head = passages.filter((p) => p.role === "headnote");

    return (
        <div className="space-y-6">
            <section className="rounded-[16px] bg-sheet p-6 ring-1 ring-rule sm:p-8">
                <div className="flex items-baseline justify-between gap-4">
                    <h2 className="text-[20px] tracking-[-0.02em]">In brief</h2>
                    <span className="text-[12px] text-graphite">Written from the judgment’s own text; each point cites its paragraph</span>
                </div>
                {brief === null && <Skeleton />}
                {typeof brief === "string" && <p className="mt-4 text-graphite">{brief} The full text is below.</p>}
                {brief && typeof brief !== "string" && (
                    <div className="mt-5 space-y-5">
                        {brief.facts && <Block title="Facts"><p><Cited text={brief.facts.text} cites={brief.facts.cites} onShow={show} /></p></Block>}
                        {brief.issue && <Block title="Issue"><p><Cited text={brief.issue.text} cites={brief.issue.cites} onShow={show} /></p></Block>}
                        {brief.held.length > 0 && <Block title="Held"><Points points={brief.held} onShow={show} /></Block>}
                        {brief.cite_for.length > 0 && <Block title="Cite it for"><Points points={brief.cite_for} onShow={show} /></Block>}
                    </div>
                )}
                <CiteAs text={citeAs} />
            </section>

            <section className="rounded-[16px] bg-sheet p-6 ring-1 ring-rule sm:p-8">
                <h2 className="text-[20px] tracking-[-0.02em]">Ask this judgment</h2>
                <form
                    onSubmit={(e) =>
                    {
                        e.preventDefault();
                        ask();
                    }}
                    className="mt-4 flex gap-2"
                >
                    <input value={question} onChange={(e) => setQuestion(e.target.value)} maxLength={1000} placeholder="What did the Court say about the settlement?"
                        className="flex-1 rounded-[4px] border border-rule bg-sheet px-3 py-2 outline-none focus:border-stamp" />
                    <button type="submit" disabled={asking || !question.trim()} className="rounded-[4px] bg-[#1d1d3a] px-5 py-2 text-sm text-white hover:bg-stamp disabled:opacity-40">
                        {asking ? "Reading" : "Ask"}
                    </button>
                </form>
                {reply && (
                    <div className="mt-5 font-serif text-[17px] leading-[1.7]">
                        <p className={reply.found ? "" : "text-graphite"}><Cited text={reply.answer} cites={[]} onShow={show} /></p>
                        {reply.found && <div className="mt-3"><Points points={reply.points} onShow={show} /></div>}
                        {reply.read.length > 0 && <p className="mt-3 font-sans text-[12px] text-graphite">Read {reply.read.length} passages most relevant to the question: {reply.read.join(", ")}</p>}
                    </div>
                )}
            </section>

            <details ref={full} className="group rounded-[16px] bg-sheet ring-1 ring-rule">
                <summary className="flex cursor-pointer list-none items-center justify-between px-6 py-4 sm:px-8">
                    <span className="text-[17px]">The judgment <span className="text-graphite">· {passages.length} passages{head.length ? ", headnote first" : ""}</span></span>
                    <span className="text-sm text-stamp group-open:hidden">Read</span>
                    <span className="hidden text-sm text-stamp group-open:inline">Fold</span>
                </summary>
                <div className="space-y-5 border-t border-rule px-6 py-6 font-serif text-[17px] leading-[1.75] text-ink/90 sm:px-8">
                    {passages.map((p) => (
                        <p key={p.id} id={`p-${p.n}`} className={`relative scroll-mt-28 rounded-[4px] pl-12 transition-colors ${lit === p.n ? "bg-stamp/[.06]" : ""} ${p.role === "headnote" ? "text-ink" : ""}`}>
                            <span className="figures absolute top-1 left-0 font-sans text-[12px] text-graphite">{p.n}{p.role === "headnote" ? " H" : ""}</span>
                            <Annotated text={p.text} refs={p.refs} />
                        </p>
                    ))}
                    <p className="font-sans text-[13px] text-graphite">Text from the Indian Supreme Court Judgments dataset, Dattam Labs, CC-BY-4.0. H marks the reporter’s headnote.</p>
                </div>
            </details>
        </div>
    );
}

function Block({ title, children }: { title: string; children: React.ReactNode })
{
    return (
        <div className="grid gap-1 sm:grid-cols-[110px_1fr] sm:gap-6">
            <h3 className="pt-0.5 text-sm text-graphite">{title}</h3>
            <div className="font-serif text-[17px] leading-[1.7]">{children}</div>
        </div>
    );
}

function Points({ points, onShow }: { points: Point[]; onShow: (n: string) => void })
{
    return (
        <ul className="space-y-2.5">
            {points.map((p, i) => (
                <li key={i} className="flex gap-3">
                    <span className="mt-[11px] h-1.5 w-1.5 shrink-0 rounded-full bg-stamp/40" />
                    <span><Cited text={p.text} cites={p.cites} onShow={onShow} /></span>
                </li>
            ))}
        </ul>
    );
}

// Paragraph markers become chips that open the full text at that passage.
function Cited({ text, cites, onShow }: { text: string; cites: string[]; onShow: (n: string) => void })
{
    const parts: React.ReactNode[] = [];
    const seen = new Set<string>();
    let at = 0;
    for (const m of text.matchAll(MARK))
    {
        parts.push(text.slice(at, m.index));
        for (const n of m[1].split(/\s*,\s*/))
        {
            seen.add(n);
            parts.push(<Chip key={`${m.index}-${n}`} n={n} onShow={onShow} />);
        }
        at = m.index + m[0].length;
    }
    parts.push(text.slice(at));
    cites.filter((c) => !seen.has(c)).forEach((c) => parts.push(<Chip key={c} n={c} onShow={onShow} />));
    return <>{parts}</>;
}

function Chip({ n, onShow }: { n: string; onShow: (n: string) => void })
{
    return (
        <button onClick={() => onShow(n)} className="ml-1 inline-flex -translate-y-px items-center rounded-[4px] bg-stamp/10 px-1.5 align-middle font-sans text-[11px] leading-[18px] font-medium text-stamp hover:ring-1 hover:ring-stamp">
            {n}
        </button>
    );
}

function CiteAs({ text }: { text: string })
{
    const [done, setDone] = useState(false);
    return (
        <div className="mt-6 flex flex-wrap items-center justify-between gap-3 rounded-[8px] bg-paper px-4 py-3">
            <p className="text-sm"><span className="text-graphite">Cite it today as </span>{text}</p>
            <button onClick={async () =>
            {
                await navigator.clipboard.writeText(text);
                setDone(true);
                setTimeout(() => setDone(false), 1500);
            }} className="rounded-[4px] border border-rule bg-sheet px-3 py-1 text-[13px] hover:border-stamp hover:text-stamp">
                {done ? "Copied" : "Copy"}
            </button>
        </div>
    );
}

function Skeleton()
{
    return (
        <div className="mt-5 space-y-3" aria-label="Writing the brief">
            {[88, 72, 94, 65, 80].map((w) => <div key={w} className="h-3 animate-pulse rounded-[4px] bg-paper" style={{ width: `${w}%` }} />)}
        </div>
    );
}

// The judgment's own words with each section reference marked in place, followed by its
// counterpart. One phrase can name several sections ("ss. 376, 363, 323 IPC"), so the chip lists
// every counterpart the phrase covers, not just the last one.
function Annotated({ text, refs }: { text: string; refs: Mention[] })
{
    if (refs.length === 0)
    {
        return <>{text}</>;
    }
    const byRaw = new Map<string, Mention[]>();
    refs.forEach((r) => byRaw.set(r.raw, [...(byRaw.get(r.raw) ?? []), r]));
    const pattern = new RegExp([...byRaw.keys()].sort((a, b) => b.length - a.length).map((r) => r.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")).join("|"), "g");
    const out: React.ReactNode[] = [];
    let at = 0;
    for (const m of text.matchAll(pattern))
    {
        const group = byRaw.get(m[0])!;
        const old = OLD.test(group[0].id);
        const others = [...new Set(group.flatMap((r) => r.other))];
        out.push(text.slice(at, m.index));
        out.push(
            <span key={m.index}>
                <Link href={href(group[0].id)} className="decoration-old/40 underline underline-offset-4 hover:decoration-old">{m[0]}</Link>
                {others.length > 0 && (
                    <span className={`ml-1 rounded-[4px] px-1 align-[1px] font-sans text-[11px] font-medium ${old ? "bg-stamp/10 text-stamp" : "bg-old/10 text-old"}`}>
                        {old ? "now " : "was "}
                        {others.slice(0, 4).map((o, i) => <span key={o}>{i > 0 && ", "}<Link href={href(o)} className="hover:underline">{label(o)}</Link></span>)}
                        {others.length > 4 && ` +${others.length - 4}`}
                    </span>
                )}
            </span>,
        );
        at = m.index + m[0].length;
    }
    out.push(text.slice(at));
    return <>{out}</>;
}
