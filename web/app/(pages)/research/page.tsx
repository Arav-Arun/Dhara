"use client";

import { Suspense, useCallback, useEffect, useRef, useState } from "react";
import { useSearchParams } from "next/navigation";
import { API, failure, label } from "@/lib/api";
import { EXAMPLES } from "@/components/AskBox";
import AnswerView, { type Answer } from "@/components/Answer";

type Event = { stage: string; ms: number; [k: string]: unknown };
type Turn = { q: string; events: Event[]; answer: Answer | null; error: string };

// Reads the server-sent events from POST /v1/research: trace events as each stage finishes, then the answer.
async function stream(body: unknown, onEvent: (name: string, data: unknown) => void)
{
    const res = await fetch(`${API}/v1/research`, {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify(body),
    });
    if (!res.ok || !res.body)
    {
        onEvent("error", { message: failure(res.status) });
        return;
    }
    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";
    for (;;)
    {
        const { done, value } = await reader.read();
        if (done)
        {
            break;
        }
        buffer += decoder.decode(value, { stream: true });
        const blocks = buffer.split(/\r?\n\r?\n/);
        buffer = blocks.pop() ?? "";
        for (const block of blocks)
        {
            const name = block.match(/^event: (.*)$/m)?.[1] ?? "message";
            const data = block.match(/^data: (.*)$/m)?.[1];
            if (data)
            {
                onEvent(name, JSON.parse(data));
            }
        }
    }
}

function Research()
{
    const params = useSearchParams();
    const [q, setQ] = useState("");
    const [asOf, setAsOf] = useState("");
    const [turns, setTurns] = useState<Turn[]>([]);
    const [busy, setBusy] = useState(false);
    const bottom = useRef<HTMLDivElement>(null);

    const run = useCallback(async (text: string, previous: Turn[]) =>
    {
        if (!text.trim())
        {
            return;
        }
        const i = previous.length;
        // earlier answers go along so the agent can turn "and if he was a juvenile?" into a full question
        const history = previous.filter((t) => t.answer?.short_answer).map((t) => ({ q: t.answer!.question, a: t.answer!.short_answer! }));
        const patch = (f: (t: Turn) => Turn) => setTurns((all) => all.map((t, j) => (j === i ? f(t) : t)));
        setTurns([...previous, { q: text.trim(), events: [], answer: null, error: "" }]);
        setQ("");
        setBusy(true);
        await stream({ query: text.trim(), as_of: asOf || null, history }, (name, data) =>
        {
            if (name === "trace")
            {
                patch((t) => ({ ...t, events: [...t.events, data as Event] }));
            }
            else if (name === "answer")
            {
                patch((t) => ({ ...t, answer: data as Answer }));
            }
            else if (name === "error")
            {
                patch((t) => ({ ...t, error: (data as { message: string }).message }));
            }
        }).catch(() => patch((t) => ({ ...t, error: failure(0) })));
        // a stream that ended without an answer or an error was cut off on the way
        patch((t) => (t.answer || t.error ? t : { ...t, error: failure(0) }));
        setBusy(false);
    }, [asOf]);

    // a query in the URL (from the home page or ⌘K) runs once on arrival
    useEffect(() =>
    {
        const initial = params.get("q");
        if (!initial)
        {
            return;
        }
        const t = setTimeout(() => run(initial, []), 0);
        return () => clearTimeout(t);
    }, [params, run]);

    useEffect(() =>
    {
        if (turns.length > 1)
        {
            bottom.current?.scrollIntoView({ behavior: "smooth", block: "end" });
        }
    }, [turns.length]);

    const ask = (text: string) => run(text, turns);
    const last = turns.at(-1);

    if (turns.length === 0)
    {
        return (
            <div className="mx-auto max-w-3xl">
                <h1 className="text-center text-[40px] tracking-[-0.04em] sm:text-[48px]">Research</h1>
                <p className="mt-1 text-center text-graphite">
                    Ask about any offence, procedure or rule of evidence, in your own words or by section number.
                </p>
                <div className="mt-8"><Composer q={q} setQ={setQ} asOf={asOf} setAsOf={setAsOf} busy={busy} onAsk={ask} first /></div>
                <p className="mt-8 text-center text-sm text-graphite">Try one of these</p>
                <div className="mt-3 grid gap-2 sm:grid-cols-2">
                    {EXAMPLES.map((e) => (
                        <button key={e} onClick={() => ask(e)}
                            className="group flex items-start gap-2.5 rounded-[4px] border border-rule bg-sheet px-3.5 py-2.5 text-left text-[13px] leading-snug text-graphite hover:border-stamp hover:text-stamp">
                            <svg width="14" height="14" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" className="mt-0.5 shrink-0 text-graphite/60 group-hover:text-stamp" aria-hidden="true"><path d="M2 8h11M9 4l4 4-4 4" /></svg>
                            <span>{e}</span>
                        </button>
                    ))}
                </div>
            </div>
        );
    }

    return (
        <div className="grid gap-10 lg:grid-cols-[minmax(0,1fr)_300px]">
            <div className="min-w-0">
                <div className="space-y-14">
                    {turns.map((t, i) => (
                        <section key={i}>
                            <h2 className="text-[26px] leading-snug tracking-[-0.03em]">{t.q}</h2>
                            {t.answer && t.answer.question !== t.q && (
                                <p className="mt-1 text-sm text-graphite">Searched as: {t.answer.question}</p>
                            )}
                            <div className="mt-5">
                                {t.error && <p className="text-redtape">{t.error}</p>}
                                {!t.answer && !t.error && <Pending events={t.events} />}
                                {t.answer && <AnswerView turn={i} answer={t.answer} onAsk={ask} />}
                            </div>
                        </section>
                    ))}
                </div>
                <div ref={bottom} className="mt-12">
                    <Composer q={q} setQ={setQ} asOf={asOf} setAsOf={setAsOf} busy={busy} onAsk={ask} />
                </div>
                <button onClick={() => setTurns([])} disabled={busy} className="mt-4 text-sm text-graphite hover:text-stamp">Start a new research thread</button>
            </div>

            <aside className="lg:sticky lg:top-24 lg:max-h-[calc(100vh-7rem)] lg:self-start lg:overflow-y-auto">
                <TraceView events={last?.events ?? []} done={!!last?.answer} />
            </aside>
        </div>
    );
}

type ComposerProps =
    {
        q: string;
        setQ: (v: string) => void;
        asOf: string;
        setAsOf: (v: string) => void;
        busy: boolean;
        onAsk: (q: string) => void;
        first?: boolean;
    };

function Composer({ q, setQ, asOf, setAsOf, busy, onAsk, first }: ComposerProps)
{
    return (
        <form
            onSubmit={(e) =>
            {
                e.preventDefault();
                onAsk(q);
            }}
            className="rounded-[18px] border border-rule bg-sheet p-4 shadow-[0_20px_40px_-28px_rgba(35,35,143,.35)] focus-within:border-stamp"
        >
            <textarea value={q} onChange={(e) => setQ(e.target.value)} rows={first ? 3 : 2} maxLength={1000}
                onKeyDown={(e) =>
                {
                    if (e.key === "Enter" && !e.shiftKey)
                    {
                        e.preventDefault();
                        onAsk(q);
                    }
                }}
                placeholder={first ? "For example: can a magistrate grant bail in a non-bailable offence punishable with life imprisonment?" : "Ask a follow-up. Earlier answers are taken into account."}
                className="w-full resize-none bg-transparent text-[17px] leading-relaxed outline-none placeholder:text-graphite/70" />
            <div className="mt-2 flex flex-wrap items-center justify-between gap-3">
                <label className="flex items-center gap-2 text-[13px] text-graphite">
                    Law as on
                    <input type="date" value={asOf} onChange={(e) => setAsOf(e.target.value)}
                        className="figures rounded-[4px] border border-rule bg-sheet px-2 py-1 text-ink outline-none focus:border-stamp" />
                    {!asOf && <span>today</span>}
                </label>
                {first && <span className="text-[13px] text-graphite">Answers from the six criminal codes and Supreme Court judgments, 1950 to September 2026</span>}
                <button type="submit" disabled={busy || !q.trim()}
                    className="rounded-[4px] bg-[#1d1d3a] px-5 py-2 text-sm text-white hover:bg-stamp disabled:opacity-40">
                    {busy ? "Researching" : "Ask"}
                </button>
            </div>
        </form>
    );
}

// While the answer is being written: the latest step, and grey bars where the answer will go.
function Pending({ events }: { events: Event[] })
{
    const now = events.at(-1);
    return (
        <div className="rounded-[18px] bg-sheet p-6 ring-1 ring-rule sm:p-8">
            <p className="flex items-center gap-2 text-sm text-stamp">
                <span className="h-2 w-2 animate-pulse rounded-full bg-stamp" />
                {now ? `${STAGE[now.stage] ?? now.stage}. Working on the next step` : "Reading the question"}
            </p>
            <div className="mt-5 space-y-3" aria-hidden="true">
                {[92, 78, 85, 60].map((w) => <div key={w} className="h-3 animate-pulse rounded-full bg-paper" style={{ width: `${w}%` }} />)}
            </div>
        </div>
    );
}

const STAGE: Record<string, string> =
    {
        rewrite: "Read the follow-up in context",
        route: "Read the question",
        "retrieve:statute": "Searched the codes",
        "retrieve:judgment": "Searched the judgments",
        "rerank:statute": "Re-ranked sections",
        "rerank:judgment": "Re-ranked judgments",
        gate: "Checked the question is about criminal law",
        plan: "Decided on further searches",
        budget: "Chose the passages",
        generate: "Wrote the answer",
        verify: "Checked every citation",
        abstain: "Declined: outside the criminal codes",
    };

function TraceView({ events, done }: { events: Event[]; done: boolean })
{
    const total = events.reduce((a, e) => a + e.ms, 0);
    const searches = events.filter((e) => e.stage.startsWith("retrieve:")).length;
    const budget = events.find((e) => e.stage === "budget");
    const verify = events.find((e) => e.stage === "verify");
    const kept = verify ? (verify.kept as number) : 0;
    const stats: [string, string][] =
        [
            ["Searches", String(searches)],
            ["Passages read", budget ? String((budget.passages as unknown[]).length) : "…"],
            ["Statements kept", verify ? `${kept} of ${kept + (verify.dropped as unknown[]).length}` : "…"],
            ["Time", done ? `${(total / 1000).toFixed(1)} s` : "…"],
        ];
    return (
        <div className="rounded-[18px] bg-sheet p-5 ring-1 ring-rule">
            <h2 className="text-[17px] tracking-[-0.01em]">How this answer was found</h2>
            <dl className="mt-4 grid grid-cols-2 gap-2">
                {stats.map(([k, v]) => (
                    <div key={k} className="rounded-[10px] bg-paper px-3 py-2">
                        <dt className="text-[12px] text-graphite">{k}</dt>
                        <dd className="figures text-[18px]">{v}</dd>
                    </div>
                ))}
            </dl>
            <ol className="mt-5 space-y-3 text-sm">
                {events.map((e, i) => <Step key={i} event={e} />)}
            </ol>
        </div>
    );
}

function Step({ event: e }: { event: Event })
{
    const refs = (e.refs as string[] | undefined) ?? [];
    const counterparts = (e.counterparts as string[] | undefined) ?? [];
    const searches = (e.searches as { query: string }[] | undefined) ?? [];
    const dropped = (e.dropped as unknown[] | undefined) ?? [];
    return (
        <li className="border-l-2 border-rule pl-3">
            <div className="flex justify-between gap-3"><span>{STAGE[e.stage] ?? e.stage}</span><span className="figures text-graphite">{e.ms} ms</span></div>
            {e.stage === "rewrite" && <p className="mt-0.5 text-graphite">“{e.question as string}”</p>}
            {refs.length > 0 && <p className="mt-0.5 text-graphite">Named {refs.map(label).join(", ")}</p>}
            {counterparts.length > 0 && <p className="mt-0.5 text-graphite">Also searched under {counterparts.map(label).join(", ")}</p>}
            {e.stage === "plan" && <p className="mt-0.5 text-graphite">{searches.length === 0 ? "None needed" : searches.map((s) => `“${s.query}”`).join("; ")}</p>}
            {e.stage === "verify" && <p className="mt-0.5 text-graphite">{dropped.length === 0 ? "All citations held up" : `${dropped.length} unsupported statement removed`}</p>}
        </li>
    );
}

export default function ResearchPage()
{
    return <Suspense><Research /></Suspense>;
}
