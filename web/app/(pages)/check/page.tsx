"use client";

import { useState } from "react";
import { post } from "@/lib/api";
import { Button, Heading, Ref, field } from "@/components/ui";

type Row = { sub: string; offence: string; punishment: string; cognizable: string; bailable: string; triable_by: string };
type Flag =
    {
        raw: string;
        start: number;
        end: number;
        provision: string;
        sub: string;
        issue: string;
        note: string;
        suggest: { id: string; sub: string }[];
        classified: Row[];
    };

const SAMPLE = "The accused was arrested on 12.03.2025 and an FIR was registered u/s 420 IPC and Section 120B IPC. "
    + "Anticipatory bail was sought under Section 438 CrPC. The prosecution also relies on Section 65B of the Evidence Act.";

const ACT: Record<string, string> = { CRPC: "CrPC", IEA: "of the Evidence Act" };
const tone = (f: Flag) => (f.issue ? "issue" : f.note ? "note" : "ok");
const ORDER = { issue: 0, note: 1, ok: 2 };

export default function Check()
{
    const [text, setText] = useState("");
    const [date, setDate] = useState("");
    const [fir, setFir] = useState("");
    const [flags, setFlags] = useState<Flag[] | null>(null);
    const [checked, setChecked] = useState("");
    const [busy, setBusy] = useState(false);
    const [copied, setCopied] = useState(false);
    const [error, setError] = useState("");

    const run = async () =>
    {
        if (!text.trim())
        {
            return;
        }
        setBusy(true);
        setError("");
        try
        {
            setFlags(await post<Flag[]>("/v1/check", { text, offence_date: date || null, proceeding_date: fir || null }));
            setChecked(text);
        }
        catch
        {
            setError("The check didn’t go through. The service may be starting up; try again in a few seconds.");
        }
        setBusy(false);
    };
    const sample = () =>
    {
        setText(SAMPLE);
        setDate("2025-03-12");
        setFlags(null);
    };

    const counts = { issue: 0, note: 0, ok: 0 };
    flags?.forEach((f) => counts[tone(f)]++);
    const sorted = [...(flags ?? [])].sort((a, b) => ORDER[tone(a)] - ORDER[tone(b)] || a.start - b.start);

    return (
        <div className="mx-auto max-w-3xl">
            <Heading sub="Paste a draft, an FIR or a chargesheet. Offences are checked against the code in force on the offence date, procedure and evidence against the date the case began.">
                Check a draft
            </Heading>
            <textarea value={text} onChange={(e) => setText(e.target.value)} rows={7} maxLength={50000}
                onKeyDown={(e) =>
                {
                    if (e.key === "Enter" && (e.metaKey || e.ctrlKey))
                    {
                        run();
                    }
                }}
                placeholder="Paste the text here. Citations can be written any way lawyers write them: u/s 302/34 IPC, Section 438 Cr.P.C., S. 65-B of the Evidence Act, 103(1) BNS."
                className={`${field} w-full font-serif text-[17px] leading-relaxed placeholder:font-sans placeholder:text-[15px]`} />
            <div className="mt-1 text-right">
                <button onClick={sample} className="text-[13px] text-stamp hover:underline">Use a sample</button>
            </div>
            <div className="mt-2 flex flex-wrap items-end justify-center gap-6">
                <label className="text-sm text-graphite">Date of the offence
                    <input type="date" value={date} onChange={(e) => setDate(e.target.value)} className={`${field} figures mt-1 block text-ink`} />
                </label>
                <label className="text-sm text-graphite">FIR registered on (optional)
                    <input type="date" value={fir} onChange={(e) => setFir(e.target.value)} className={`${field} figures mt-1 block text-ink`} />
                </label>
                <Button onClick={run} disabled={busy || !text.trim()}>{busy ? "Checking" : "Check citations"}</Button>
            </div>
            {!date && text && <p className="mt-3 text-center text-[13px] text-graphite">Without an offence date, Dhara can only check that each section exists and isn’t repealed.</p>}
            {error && <p className="mt-4 text-center text-redtape">{error}</p>}

            {flags && (
                <section className="mt-12 space-y-8">
                    <div className="flex flex-wrap items-baseline justify-between gap-3">
                        <h2 className="text-[22px] tracking-[-0.02em]">
                            {flags.length === 0 ? "No citations found" : counts.issue ? `${counts.issue} of ${flags.length} citations need fixing` : `No wrong citations among ${flags.length}`}
                        </h2>
                        <p className="flex gap-4 text-[13px] text-graphite">
                            <Dot c="bg-redtape" />{counts.issue} to fix
                            <Dot c="bg-amber" />{counts.note} to confirm
                            <Dot c="bg-green" />{counts.ok} correct
                        </p>
                    </div>

                    {flags.length > 0 && (
                        <div className="rounded-[16px] bg-sheet p-6 ring-1 ring-rule">
                            <div className="flex items-baseline justify-between gap-3">
                                <h3 className="text-sm text-graphite">Your draft, with each citation marked</h3>
                                {counts.issue > 0 && (
                                    <button onClick={async () =>
                                    {
                                        await navigator.clipboard.writeText(corrected(checked, flags));
                                        setCopied(true);
                                        setTimeout(() => setCopied(false), 1600);
                                    }} className="rounded-[4px] border border-rule px-3 py-1 text-[13px] hover:border-stamp hover:text-stamp">
                                        {copied ? "Copied" : "Copy with corrections added"}
                                    </button>
                                )}
                            </div>
                            <p className="mt-3 font-serif text-[17px] leading-[1.8] whitespace-pre-wrap"><Marked text={checked} flags={flags} /></p>
                        </div>
                    )}

                    <ul className="divide-y divide-rule border-y border-rule">
                        {sorted.map((f, i) => (
                            <li key={i} className="py-4">
                                <div className="flex flex-wrap items-baseline gap-x-4 gap-y-1">
                                    <Dot c={{ issue: "bg-redtape", note: "bg-amber", ok: "bg-green" }[tone(f)]} />
                                    <span><Ref id={f.provision} link={!f.issue.startsWith("no such")} /><span className="figures text-graphite">{f.sub}</span></span>
                                    <span className={{ issue: "text-redtape", note: "text-amber", ok: "text-graphite" }[tone(f)]}>{f.issue ? capital(f.issue) : f.note || "Correct for these dates"}</span>
                                    {f.suggest.length > 0 && <span className="text-graphite">Use {f.suggest.map((s, j) => <span key={s.id + s.sub}>{j > 0 && " or "}<Ref id={s.id} /><span className="figures">{s.sub}</span></span>)}</span>}
                                </div>
                                {f.classified.map((r) => (
                                    <p key={r.offence} className="mt-1.5 pl-[22px] text-[13px] leading-snug text-graphite">
                                        <span className="text-ink/80">{r.offence.replace(/\.$/, "")}</span> · {[r.cognizable, r.bailable, r.triable_by, r.punishment].map((x) => x.replace(/\.$/, "")).join(" · ")}
                                    </p>
                                ))}
                            </li>
                        ))}
                    </ul>
                    {sorted.some((f) => f.classified.length) && <p className="text-[12px] text-graphite">Arrest, bail and court as listed in the First Schedule to the BNSS.</p>}
                </section>
            )}
        </div>
    );
}

function Dot({ c }: { c: string })
{
    return <span className={`inline-block h-1.5 w-1.5 shrink-0 self-center rounded-full ${c}`} />;
}

// The draft as checked, each citation underlined in its colour; a wrong one is followed by the fix.
function Marked({ text, flags }: { text: string; flags: Flag[] })
{
    const spans = group(flags);
    const out: React.ReactNode[] = [];
    let at = 0;
    for (const [start, group_] of spans)
    {
        const end = group_[0].end;
        const worst = group_.map(tone).sort((a, b) => ORDER[a] - ORDER[b])[0];
        out.push(text.slice(at, start));
        out.push(
            <span key={start}>
                <span className={`underline decoration-2 underline-offset-4 ${{ issue: "decoration-redtape", note: "decoration-amber", ok: "decoration-green/60" }[worst]}`}>{text.slice(start, end)}</span>
                {worst === "issue" && fixFor(group_) && <span className="ml-1 rounded-[4px] bg-stamp/10 px-1 align-[1px] font-sans text-[12px] font-medium text-stamp">{fixFor(group_)}</span>}
            </span>,
        );
        at = end;
    }
    out.push(text.slice(at));
    return <>{out}</>;
}

// One phrase can name several sections ("u/s 302/34 IPC"), so citations are grouped by where they start.
function group(flags: Flag[]): [number, Flag[]][]
{
    const by = new Map<number, Flag[]>();
    flags.forEach((f) => by.set(f.start, [...(by.get(f.start) ?? []), f]));
    return [...by.entries()].sort((a, b) => a[0] - b[0]);
}

// "now Sections 103 and 3(5) BNS", written the way it would sit in a draft
function fixFor(flags: Flag[]): string
{
    const fixes = flags.filter((f) => f.issue).flatMap((f) => f.suggest.slice(0, 1));
    if (fixes.length === 0)
    {
        return "";
    }
    const byAct = new Map<string, string[]>();
    fixes.forEach((s) =>
    {
        const [code, num] = s.id.split(":");
        const act = ACT[code] ?? code;
        byAct.set(act, [...(byAct.get(act) ?? []), num + s.sub]);
    });
    // old-code suggestions mean an old offence cited under the new code: "now" would be wrong there
    const older = fixes.every((s) => /^(IPC|CRPC|IEA):/.test(s.id));
    return (older ? "for these dates: " : "now ") + [...byAct.entries()].map(([act, nums]) => `${nums.length > 1 ? "Sections" : "Section"} ${nums.join(" and ")} ${act}`).join("; ");
}

// The draft with "(now Section 318(4) BNS)" added after each wrong citation; nothing else is changed.
function corrected(text: string, flags: Flag[]): string
{
    let out = text;
    for (const [, group_] of group(flags).reverse())
    {
        const fix = fixFor(group_);
        let at = group_[0].end;
        while (at > group_[0].start && ".,;:".includes(out[at - 1]))
        {
            at--; // "u/s 201 IPC." takes the note before its full stop
        }
        if (fix)
        {
            out = out.slice(0, at) + ` (${fix})` + out.slice(at);
        }
    }
    return out;
}

function capital(s: string): string
{
    return s.charAt(0).toUpperCase() + s.slice(1);
}
