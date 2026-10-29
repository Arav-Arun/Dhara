import Link from "next/link";
import { notFound } from "next/navigation";
import { Suspense } from "react";
import { label } from "@/lib/api";
import { cached } from "@/lib/data";
import { Ref, Source, titleCase } from "@/components/ui";
import JudgmentReader, { type Passage } from "@/components/JudgmentReader";

type Cite = { id: string; mentions: number; counterparts: string[] };
type Judgment =
    {
        id: string;
        title: string;
        decided_on: string;
        citation: string;
        court: string;
        original: string;
        passages: Passage[];
        cites: Cite[];
        related: { id: string; title: string; decided_on: string; citation: string }[];
    };

const OLD = /^(IPC|CRPC|IEA):/;

export async function generateMetadata(props: PageProps<"/judgments/[id]">)
{
    const { id } = await props.params;
    const j = await cached<Judgment>(`/v1/judgments/${encodeURIComponent(decodeURIComponent(id))}`);
    return { title: j ? `${titleCase(j.title)} (${j.decided_on.slice(0, 4)})` : "Judgment" };
}

export default function JudgmentPage(props: PageProps<"/judgments/[id]">)
{
    return (
        <Suspense fallback={<p className="text-graphite">Loading the judgment</p>}>
            <JudgmentView params={props.params} />
        </Suspense>
    );
}

async function JudgmentView({ params }: { params: Promise<{ id: string }> })
{
    const { id } = await params;
    const j = await cached<Judgment>(`/v1/judgments/${encodeURIComponent(decodeURIComponent(id))}`);
    if (!j)
    {
        notFound();
    }
    const date = new Date(j.decided_on).toLocaleDateString("en-IN", { day: "numeric", month: "long", year: "numeric" });

    return (
        <div className="grid gap-10 lg:grid-cols-[minmax(0,1fr)_300px]">
            <article className="min-w-0">
                <div className="flex flex-wrap items-baseline justify-between gap-x-6 gap-y-1">
                    <p className="figures text-sm text-graphite">{j.court} · {date} · {j.citation}</p>
                    {j.original && <Source href={j.original}>Original judgment (PDF)</Source>}
                </div>
                <h1 className="mt-3 mb-8 font-serif text-[30px] leading-tight font-semibold tracking-[-0.01em] sm:text-[38px]">{titleCase(j.title)}</h1>
                <JudgmentReader jid={j.id} passages={j.passages} citeAs={citeAs(j)} />
            </article>

            <aside className="space-y-6 lg:sticky lg:top-24 lg:self-start">
                <div className="rounded-[16px] bg-sheet p-5 ring-1 ring-rule">
                    <h2 className="text-[17px]">Provisions it turns on</h2>
                    <p className="mt-1 text-[13px] text-graphite">With today’s counterpart, so it can be cited under the new codes.</p>
                    <ul className="mt-3 divide-y divide-rule text-sm">
                        {j.cites.slice(0, 10).map((c) => (
                            <li key={c.id} className="flex items-baseline justify-between gap-3 py-2">
                                <span>
                                    <Ref id={c.id} />
                                    {c.counterparts.length > 0 && <span className="text-graphite"> {OLD.test(c.id) ? "now" : "was"} {c.counterparts.slice(0, 2).map((o, i) => <span key={o}>{i > 0 && ", "}<Ref id={o} /></span>)}</span>}
                                </span>
                                <span className="figures shrink-0 text-[12px] text-graphite">{c.mentions}×</span>
                            </li>
                        ))}
                    </ul>
                </div>
                {j.related.length > 0 && (
                    <div className="rounded-[16px] bg-sheet p-5 ring-1 ring-rule">
                        <h2 className="text-[17px]">Related judgments</h2>
                        <p className="mt-1 text-[13px] text-graphite">Found from what this one decides, not from shared section numbers.</p>
                        <ul className="mt-3 space-y-3 text-sm">
                            {j.related.map((r) => (
                                <li key={r.id}>
                                    <Link href={`/judgments/${encodeURIComponent(r.id)}`} className="font-serif leading-snug hover:text-stamp">{titleCase(r.title)}</Link>
                                    <p className="figures mt-0.5 text-[12px] text-graphite">{r.decided_on.slice(0, 4)} · {r.citation || r.id}</p>
                                </li>
                            ))}
                        </ul>
                    </div>
                )}
            </aside>
        </div>
    );
}

// "Jitendra Raghuvanshi v. Babita Raghuvanshi, [2013] 2 S.C.R. 921 (on CrPC 482, now BNSS 528)"
function citeAs(j: Judgment): string
{
    const on = j.cites.slice(0, 2).map((c) =>
        c.counterparts.length && OLD.test(c.id) ? `${label(c.id)}, now ${c.counterparts.slice(0, 2).map(label).join(" and ")}` : label(c.id));
    return `${titleCase(j.title)}, ${j.citation || j.id}${on.length ? ` (on ${on.join("; ")})` : ""}`;
}
