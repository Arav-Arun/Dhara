"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";

export const EXAMPLES = [
    "When can a High Court quash an FIR after the parties settle?",
    "Is a confession made to a police officer admissible as evidence?",
    "What must the police tell a person at the time of arrest?",
    "Can bail be refused only because the offence is serious?",
    "What does the new law say about mob lynching?",
    "Must a magistrate hear the accused before taking cognizance of a complaint?",
];

// The main way into Dhara: ask in plain words, land on Research with the question running.
export default function AskBox({ autoFocus = false }: { autoFocus?: boolean })
{
    const [q, setQ] = useState("");
    const router = useRouter();
    const ask = (text: string) =>
    {
        if (text.trim())
        {
            router.push(`/research?q=${encodeURIComponent(text.trim())}`);
        }
    };

    return (
        <div className="rounded-[22px] border border-rule bg-sheet/85 p-2 text-left shadow-[0_30px_60px_-30px_rgba(35,35,143,.35)] backdrop-blur">
            <form
                onSubmit={(e) =>
                {
                    e.preventDefault();
                    ask(q);
                }}
                className="rounded-[16px] border border-rule bg-sheet p-4"
            >
                <textarea
                    value={q}
                    onChange={(e) => setQ(e.target.value)}
                    onKeyDown={(e) =>
                    {
                        if (e.key === "Enter" && !e.shiftKey)
                        {
                            e.preventDefault();
                            ask(q);
                        }
                    }}
                    autoFocus={autoFocus}
                    rows={2}
                    maxLength={1000}
                    placeholder="Ask anything about Indian criminal law: an offence, bail, evidence, procedure, a section number…"
                    className="w-full resize-none bg-transparent text-[18px] leading-relaxed outline-none placeholder:text-graphite/70"
                />
                <div className="mt-2 flex items-center justify-between gap-3">
                    <p className="text-[13px] text-graphite">Answers cite the statute and Supreme Court judgments they rely on.</p>
                    <button type="submit" disabled={!q.trim()}
                        className="rounded-[4px] bg-[#1d1d3a] px-5 py-2 text-sm text-white hover:bg-stamp disabled:opacity-40">
                        Ask
                    </button>
                </div>
            </form>
            <div className="grid gap-2 px-1 pt-2 pb-1 sm:grid-cols-2">
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
