"use client";

import Link from "next/link";
import { useState } from "react";
import { href, label } from "@/lib/api";
import { Ref, Source, Status, relation, titleCase } from "@/components/ui";

export type Point = { kind?: "law" | "holding" | "practice"; text: string; cites: string[] };
type Row = { offence: string; punishment: string; cognizable: string; bailable: string; triable_by: string };
type Authority = { id: string; proposition: string };
export type Source =
    {
        id: string;
        unit: string;
        ref: string;
        title: string;
        text: string;
        kind: "statute" | "judgment";
        heading?: string;
        status?: string;
        official?: string;
        original?: string;
        counterparts?: { id: string; relation: string }[];
        case?: string;
        decided_on?: string;
        citation?: string;
        role?: string;
        cites?: { id: string; mentions: number; counterparts: string[] }[];
        bench?: string[];
        classified?: Row[];
    };
export type Answer =
    {
        route: "research" | "lookup";
        question: string;
        abstain?: boolean;
        short_answer?: string;
        points?: Point[];
        authorities?: Authority[];
        caveats?: string[];
        context?: Source[];
        follow_ups?: string[];
        statutes?: string[];
    };

// One answer: the reply with its citations, what to do next, and every source it rests on.
export default function AnswerView({ turn, answer, onAsk }: { turn: number; answer: Answer; onAsk: (q: string) => void })
{
    const [open, setOpen] = useState<string | null>(null);
    const sources = answer.context ?? [];
    const byId = Object.fromEntries(sources.map((s) => [s.id, s]));
    const anchor = (id: string) => `t${turn}-${id}`;
    const show = (id: string) =>
    {
        setOpen(id);
        document.getElementById(anchor(id))?.scrollIntoView({ behavior: "smooth", block: "center" });
    };

    if (answer.route === "lookup")
    {
        return (
            <div className="grid gap-3 sm:grid-cols-3">
                {(answer.statutes ?? []).map((id) => (
                    <Link key={id} href={href(id)} className="rounded-[14px] bg-sheet p-4 ring-1 ring-rule hover:ring-stamp">
                        <Ref id={id} link={false} />
                        <p className="mt-1 text-sm text-graphite">Open the section, its counterpart and the judgments on it</p>
                    </Link>
                ))}
            </div>
        );
    }

    if (answer.abstain)
    {
        return (
            <div className="rounded-[16px] border-l-2 border-amber bg-sheet p-5 ring-1 ring-rule">
                <h3 className="text-[18px]">Not enough support for an answer</h3>
                <p className="mt-2 leading-relaxed text-graphite">
                    The sections and judgments found don’t support a reliable answer. Try naming the section, or asking about a narrower point.
                </p>
                {(answer.caveats ?? []).map((c) => <p key={c} className="mt-2 text-sm text-graphite">{c}</p>)}
            </div>
        );
    }

    const statutes = sources.filter((s) => s.kind === "statute");
    const judgments = sources.filter((s) => s.kind === "judgment");
    // a long section reaches the answer as several passages; show it once
    const sections = [...new Set(statutes.map((s) => s.ref))].map((ref) => statutes.filter((s) => s.ref === ref));
    const paired = statutes.find((s) => (s.counterparts ?? []).length > 0);

    return (
        <div>
            <article className="rounded-[18px] bg-sheet p-6 ring-1 ring-rule sm:p-8">
                <p className="font-serif text-[21px] leading-[1.6]"><Cited text={answer.short_answer ?? ""} cites={[]} byId={byId} onShow={show} /></p>
                {GROUPS.map(([kind, title]) =>
                {
                    const points = (answer.points ?? []).filter((p) => (p.kind ?? "law") === kind);
                    return points.length > 0 && (
                        <div key={kind} className="mt-6">
                            <h4 className="text-[13px] text-graphite">{title}</h4>
                            <ul className="mt-2 space-y-3 font-serif text-[17px] leading-[1.7] text-ink/90">
                                {points.map((p, i) => (
                                    <li key={i} className="flex gap-3">
                                        <span className="mt-[11px] h-1.5 w-1.5 shrink-0 rounded-full bg-stamp/40" />
                                        <span><Cited text={p.text} cites={p.cites} byId={byId} onShow={show} /></span>
                                    </li>
                                ))}
                            </ul>
                        </div>
                    );
                })}

                {(answer.authorities ?? []).length > 0 && (
                    <div className="mt-7 rounded-[12px] bg-paper p-4 sm:p-5">
                        <h4 className="text-[13px] text-graphite">Cases to cite</h4>
                        <ol className="mt-3 space-y-3">
                            {answer.authorities!.filter((a) => byId[a.id]).map((a) => (
                                <li key={a.id} className="text-[15px] leading-snug">
                                    <Link href={`/judgments/${encodeURIComponent(byId[a.id].ref)}`} className="font-serif font-semibold underline-offset-4 hover:underline">
                                        {titleCase(byId[a.id].case ?? byId[a.id].title)}
                                    </Link>
                                    <span className="figures text-[13px] text-graphite"> · {cite(byId[a.id])}</span>
                                    <p className="mt-0.5 text-ink/80">{a.proposition.replace(MARK, "")}<Chip id={a.id} title={byId[a.id].title} onShow={show} /></p>
                                </li>
                            ))}
                        </ol>
                    </div>
                )}
                {(answer.caveats ?? []).length > 0 && (
                    <div className="mt-6 rounded-[12px] bg-paper px-4 py-3 text-sm leading-relaxed text-graphite">
                        {answer.caveats!.map((c) => <p key={c}><Cited text={c} cites={[]} byId={byId} onShow={show} /></p>)}
                    </div>
                )}

                <div className="mt-6 flex flex-wrap gap-2 border-t border-rule pt-5">
                    <Copy answer={answer} />
                    <Action href={`/research?q=${encodeURIComponent(answer.question)}`}>Link to this question</Action>
                    {paired && <Action href={`${href(paired.ref)}#changes`}>How {label(paired.ref)} changed from the old code</Action>}
                </div>
            </article>

            {(answer.follow_ups ?? []).length > 0 && (
                <div className="mt-5">
                    <p className="text-sm text-graphite">Ask next</p>
                    <div className="mt-2 grid gap-2 sm:grid-cols-3">
                        {answer.follow_ups!.map((f) => (
                            <button key={f} onClick={() => onAsk(f)}
                                className="group flex items-start gap-2 rounded-[4px] border border-rule bg-sheet px-3 py-2.5 text-left text-[13px] leading-snug text-graphite hover:border-stamp hover:text-stamp">
                                <svg width="14" height="14" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" className="mt-0.5 shrink-0" aria-hidden="true"><path d="M4 3v5a3 3 0 0 0 3 3h6M10 8l3 3-3 3" /></svg>
                                <span>{f}</span>
                            </button>
                        ))}
                    </div>
                </div>
            )}

            <section className="mt-10">
                <h3 className="text-[20px] tracking-[-0.02em]">Sources</h3>
                <p className="mt-1 text-sm text-graphite">
                    {sections.length} {sections.length === 1 ? "section" : "sections"} and {new Set(judgments.map((j) => j.ref)).size} judgments were given to the answer. Each was checked against what was retrieved.
                </p>
                {statutes.length > 0 && (
                    <div className="mt-5 grid gap-3 md:grid-cols-2">
                        {sections.map((parts) => (
                            <StatuteCard key={parts[0].ref} parts={parts} anchor={anchor} open={parts.some((x) => x.id === open)}
                                onToggle={() => setOpen(parts.some((x) => x.id === open) ? null : parts[0].id)} />
                        ))}
                    </div>
                )}
                {judgments.length > 0 && (
                    <div className="mt-3 space-y-3">
                        {judgments.map((s) => <JudgmentCard key={s.id} s={s} anchor={anchor(s.id)} open={open === s.id} onToggle={() => setOpen(open === s.id ? null : s.id)} />)}
                    </div>
                )}
            </section>
        </div>
    );
}

const OLD = /^(IPC|CRPC|IEA):/;
const GROUPS: [NonNullable<Point["kind"]>, string][] = [["law", "The law"], ["holding", "What the courts have held"], ["practice", "In practice"]];

// "Title (2013) [2013] 2 S.C.R. 921, bench of 3" as a lawyer would note it
function cite(s: Source): string
{
    const bench = (s.bench ?? []).length;
    return [s.decided_on?.slice(0, 4), s.citation, bench >= 5 ? `bench of ${bench}, Constitution Bench` : bench >= 2 ? `bench of ${bench}` : ""].filter(Boolean).join(" · ");
}

// "[S7] [J5]" or "[S7, J5]" written into the text by the model
const MARK = /\s*\[([SJ]\d+(?:\s*,\s*[SJ]\d+)*)\]/g;

// The answer's text with its citation markers turned into chips that open the source. Markers the
// model wrote inline stay where it put them; cited ids it left out of the text go at the end.
function Cited({ text, cites, byId, onShow }: { text: string; cites: string[]; byId: Record<string, Source>; onShow: (id: string) => void })
{
    const parts: React.ReactNode[] = [];
    const seen = new Set<string>();
    let at = 0;
    for (const m of text.matchAll(MARK))
    {
        parts.push(text.slice(at, m.index));
        for (const id of m[1].split(/\s*,\s*/))
        {
            seen.add(id);
            parts.push(<Chip key={`${m.index}-${id}`} id={id} title={byId[id]?.title} onShow={onShow} />);
        }
        at = m.index + m[0].length;
    }
    parts.push(text.slice(at));
    cites.filter((c) => !seen.has(c)).forEach((c) => parts.push(<Chip key={c} id={c} title={byId[c]?.title} onShow={onShow} />));
    return <>{parts}</>;
}

function Chip({ id, title, onShow }: { id: string; title?: string; onShow: (id: string) => void })
{
    return (
        <button onClick={() => onShow(id)} title={title}
            className={`ml-1 inline-flex -translate-y-px items-center rounded-[4px] px-1.5 align-middle font-sans text-[11px] font-medium leading-[18px] ${id.startsWith("S") ? "bg-stamp/10 text-stamp" : "bg-old/10 text-old"} hover:ring-1 hover:ring-current`}>
            {id}
        </button>
    );
}

type CardProps = { s: Source; anchor: string; open: boolean; onToggle: () => void };

function StatuteCard({ parts, anchor, open, onToggle }: { parts: Source[]; anchor: (id: string) => string; open: boolean; onToggle: () => void })
{
    const s = parts[0];
    const others = s.counterparts ?? [];
    const text = parts.map((x) => x.text.split("\n").slice(1).join("\n") || x.text).join("\n");
    return (
        <div className={`relative rounded-[14px] bg-sheet p-4 ring-1 transition-shadow ${open ? "ring-stamp" : "ring-rule"}`}>
            {parts.map((x) => <span key={x.id} id={anchor(x.id)} className="absolute top-0 scroll-mt-24" />)}
            <div className="flex items-baseline justify-between gap-3">
                <div className="flex items-baseline gap-2">
                    <span className="text-[12px] font-medium text-stamp">{parts.map((x) => x.id).join(" ")}</span>
                    <Ref id={s.ref} />
                </div>
                {s.status && <Status status={s.ref.match(/^(IPC|CRPC|IEA):/) ? "repealed" : s.status} />}
            </div>
            <p className="mt-1 font-serif italic">{s.heading}</p>
            {others.length > 0 && (
                <p className="mt-2 text-sm text-graphite">
                    {s.ref.match(/^(IPC|CRPC|IEA):/) ? "Now " : "Was "}
                    {others.slice(0, 5).map((o, i) => <span key={o.id}>{i > 0 && ", "}<Ref id={o.id} /></span>)}
                    {others.length > 5 && ` and ${others.length - 5} more`}
                    <span className="text-graphite/80">. {relation(others[0].relation)}</span>
                </p>
            )}
            {(s.classified ?? []).map((r) => (
                <p key={r.offence} className="mt-2 text-[13px] leading-snug text-graphite">
                    <span className="text-ink/80">{r.offence.replace(/\.$/, "")}</span> · {[r.cognizable, r.bailable, r.triable_by, r.punishment].map((x) => x.replace(/\.$/, "")).join(" · ")}
                </p>
            ))}
            <Excerpt text={text} open={open} onToggle={onToggle} />
            {s.official && <div className="mt-2"><Source href={s.official}>Official text</Source></div>}
        </div>
    );
}

function JudgmentCard({ s, anchor, open, onToggle }: CardProps)
{
    const year = s.decided_on?.slice(0, 4);
    return (
        <div id={anchor} className={`scroll-mt-24 rounded-[14px] bg-sheet p-4 ring-1 transition-shadow ${open ? "ring-old" : "ring-rule"}`}>
            <div className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1">
                <div className="flex items-baseline gap-2">
                    <span className="text-[12px] font-medium text-old">{s.id}</span>
                    <Link href={`/judgments/${encodeURIComponent(s.ref)}`} className="font-serif text-[17px] font-semibold underline-offset-4 hover:underline">
                        {titleCase(s.case ?? s.title)}
                    </Link>
                </div>
                <span className="text-[12px] text-graphite">{s.role === "headnote" ? "From the headnote" : "From the judgment"}</span>
            </div>
            <p className="figures mt-1 text-sm text-graphite">{[year, s.citation, "Supreme Court of India"].filter(Boolean).join(" · ")}</p>
            {(s.bench ?? []).length >= 2 && (
                <p className="mt-0.5 text-[13px] text-graphite">{s.bench!.length >= 5 ? "Constitution Bench" : `Bench of ${s.bench!.length}`}: {s.bench!.join(", ")}</p>
            )}
            {(s.cites ?? []).length > 0 && (
                <p className="mt-2 text-sm text-graphite">
                    Turns on {s.cites!.slice(0, 4).map((c, i) => (
                        <span key={c.id}>
                            {i > 0 && ", "}<Ref id={c.id} />
                            {c.counterparts.length > 0 && <span> (now <Ref id={c.counterparts[0]} />)</span>}
                        </span>
                    ))}
                </p>
            )}
            <Excerpt text={s.text} open={open} onToggle={onToggle} />
            {s.original && <div className="mt-2"><Source href={s.original}>Original judgment (PDF)</Source></div>}
        </div>
    );
}

function Excerpt({ text, open, onToggle }: { text: string; open: boolean; onToggle: () => void })
{
    return (
        <div className="mt-3">
            <p className={`font-serif text-[15px] leading-relaxed whitespace-pre-line text-ink/80 ${open ? "" : "line-clamp-3"}`}>{text}</p>
            <button onClick={onToggle} className="mt-1 text-[13px] text-stamp hover:underline">{open ? "Show less" : "Read the passage"}</button>
        </div>
    );
}

function Action({ href: to, children }: { href: string; children: React.ReactNode })
{
    return (
        <Link href={to} className="rounded-[4px] border border-rule px-3 py-1.5 text-[13px] text-ink/80 hover:border-stamp hover:text-stamp">{children}</Link>
    );
}

// The answer as a research note to paste into a brief: headed sections, cases with their
// citations and bench, sections with their old numbers and official links.
function Copy({ answer }: { answer: Answer })
{
    const [done, setDone] = useState(false);
    const text = () =>
    {
        const byId = Object.fromEntries((answer.context ?? []).map((s) => [s.id, s]));
        const clean = (t: string) => t.replace(MARK, "").trim();
        const ref = (ids: string[]) => ids.map((id) => (byId[id]?.kind === "statute" ? label(byId[id].ref) : titleCase(byId[id]?.case ?? id))).join("; ");
        const blocks = [`Question: ${answer.question}`, `Short answer\n${clean(answer.short_answer ?? "")}`];
        for (const [kind, title] of GROUPS)
        {
            const points = (answer.points ?? []).filter((p) => (p.kind ?? "law") === kind);
            if (points.length)
            {
                blocks.push(`${title}\n${points.map((p) => `- ${clean(p.text)} (${ref(p.cites)})`).join("\n")}`);
            }
        }
        const cases = (answer.authorities ?? []).filter((a) => byId[a.id]);
        if (cases.length)
        {
            blocks.push(`Cases to cite\n${cases.map((a) => `- ${titleCase(byId[a.id].case ?? byId[a.id].title)}, ${cite(byId[a.id])}: ${clean(a.proposition)}`).join("\n")}`);
        }
        const sections = [...new Map((answer.context ?? []).filter((s) => s.kind === "statute").map((s) => [s.ref, s])).values()];
        if (sections.length)
        {
            blocks.push(`Sections\n${sections.map((s) => `- ${label(s.ref)}, ${s.heading}${(s.counterparts ?? []).length ? ` (${OLD.test(s.ref) ? "now" : "formerly"} ${s.counterparts!.slice(0, 5).map((c) => label(c.id)).join(", ")})` : ""}${s.official ? `: ${s.official}` : ""}`).join("\n")}`);
        }
        if ((answer.caveats ?? []).length)
        {
            blocks.push(`Caveats\n${answer.caveats!.map((c) => `- ${clean(c)}`).join("\n")}`);
        }
        blocks.push("Prepared with Dhara, a research aid; check every authority before relying on it.");
        return blocks.join("\n\n") + "\n";
    };
    return (
        <button onClick={async () =>
        {
            await navigator.clipboard.writeText(text());
            setDone(true);
            setTimeout(() => setDone(false), 1800);
        }}
        className="rounded-[4px] bg-[#1d1d3a] px-3 py-1.5 text-[13px] text-white hover:bg-stamp">
            {done ? "Copied" : "Copy as research note"}
        </button>
    );
}
