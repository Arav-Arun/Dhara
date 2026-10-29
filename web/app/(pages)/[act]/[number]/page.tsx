import Link from "next/link";
import { notFound } from "next/navigation";
import { Suspense } from "react";
import { href, label, type Counterpart, type Provision } from "@/lib/api";
import { cached } from "@/lib/data";
import { Ref, Source, Status, relation, titleCase } from "@/components/ui";
import DiffView from "@/components/DiffView";

const ACTS = ["bns", "bnss", "bsa", "ipc", "crpc", "iea"];
const OLD = ["IPC", "CRPC", "IEA"];

type Texts = { counterparts: Counterpart[]; texts: Record<string, { heading: string; text: string }> };

export async function generateMetadata(props: PageProps<"/[act]/[number]">)
{
    const { act, number } = await props.params;
    const p = await cached<Provision>(`/v1/provisions/${act}/${number}`);
    const name = label(`${act.toUpperCase()}:${number}`);
    return { title: p ? `${name}, ${p.heading}` : name };
}

export default function ProvisionPage(props: PageProps<"/[act]/[number]">)
{
    return (
        <Suspense fallback={<p className="text-graphite">Loading the section</p>}>
            <ProvisionView params={props.params} />
        </Suspense>
    );
}

async function ProvisionView({ params }: { params: Promise<{ act: string; number: string }> })
{
    const { act, number } = await params;
    if (!ACTS.includes(act.toLowerCase()))
    {
        notFound();
    }
    const [p, both] = await Promise.all([
        cached<Provision>(`/v1/provisions/${act}/${number}`),
        cached<Texts>(`/v1/compare/${act}/${number}`),
    ]);
    if (!p)
    {
        notFound();
    }
    const old = OLD.includes(p.act);

    return (
        <div className="grid gap-12 lg:grid-cols-[minmax(0,1fr)_300px]">
            <article>
                <p className="text-sm text-graphite">
                    {p.act_title}, Chapter {p.chapter_no}: {titleCase(p.chapter_title)}{p.subheading ? `. ${p.subheading}` : ""}
                </p>

                <div className="mt-6 grid gap-x-8 sm:grid-cols-[160px_minmax(0,1fr)]">
                    <aside className="mb-4 sm:mb-0 sm:text-right">
                        <div className={`figures font-serif text-[44px] leading-none font-semibold ${old ? "text-old" : "text-stamp"}`}>{p.number}</div>
                        <p className="mt-3 font-serif text-[15px] leading-snug italic">{p.heading}</p>
                    </aside>
                    <div className="max-w-[68ch]">
                        <div className="mb-6 flex flex-wrap items-center gap-x-6 gap-y-1">
                            <Status status={old ? "repealed" : p.status} note={old ? `in force until ${fmt(p.in_force_to)}` : `from ${fmt(p.in_force_from)}`} />
                            {p.official && <Source href={p.official}>{old ? `India Code PDF, page ${p.source_page}` : "Official text on NCRB Sankalan"}</Source>}
                            {p.flag && <span className="text-sm text-graphite">{p.flag === "new" ? "New in the 2023 code" : "Changed from the old code"}</span>}
                        </div>
                        <div className="space-y-4 font-serif text-[18px] leading-[1.72]">
                            {p.parts.map((part) => (
                                <Part key={part.id} kind={part.kind} label={part.label} text={part.text}
                                    added={part.added !== "[]"} pending={part.status === "not_commenced"} />
                            ))}
                        </div>
                    </div>
                </div>

                {p.classification.length > 0 && (
                    <section className="mt-12 sm:ml-[192px]">
                        <h2 className="font-serif text-lg font-semibold">Classification under the BNSS First Schedule</h2>
                        <table className="mt-3 w-full max-w-[68ch] text-sm">
                            <thead className="text-left text-graphite">
                                <tr><th className="py-2 pr-4 font-normal">Offence</th><th className="py-2 pr-4 font-normal">Punishment</th><th className="py-2 font-normal">Arrest, bail, court</th></tr>
                            </thead>
                            <tbody>
                                {p.classification.map((c, i) => (
                                    <tr key={i} className="border-t border-rule align-top">
                                        <td className="py-2 pr-4"><span className="figures text-graphite">{c.sub}</span> {c.offence}</td>
                                        <td className="py-2 pr-4">{c.punishment}</td>
                                        <td className="py-2">{[c.cognizable, c.bailable, c.triable_by].map((x) => x.replace(/\.$/, "")).join(", ")}</td>
                                    </tr>
                                ))}
                            </tbody>
                        </table>
                    </section>
                )}

                {both && <Changes id={p.id} both={both} />}
            </article>

            <aside className="space-y-10 text-sm lg:border-l lg:border-rule lg:pl-8">
                <section>
                    <h2 className="font-serif text-base font-semibold">{old ? "Replaced by" : "Earlier law"}</h2>
                    {p.counterparts.length === 0 && <p className="mt-2 text-graphite">Not in the official correspondence table.</p>}
                    <ul className="mt-3 space-y-4">
                        {p.counterparts.map((c, i) => (
                            <li key={i}>
                                {c.id ? <Ref id={c.id} /> : <span className="text-redtape">None</span>}
                                {c.heading && <span className="text-graphite">, {c.heading}</span>}
                                <p className="mt-0.5 text-graphite">{relation(c.relation)}</p>
                                {c.note && <p className="mt-0.5 text-[13px] text-graphite">{c.note}</p>}
                            </li>
                        ))}
                    </ul>
                    {p.counterparts.some((c) => c.id) && (
                        <a href="#changes" className="mt-4 inline-block text-stamp hover:underline">See how the wording changed</a>
                    )}
                </section>

                <section>
                    <h2 className="font-serif text-base font-semibold">Supreme Court judgments</h2>
                    <p className="mt-1 text-graphite">Citing this section or its counterpart, most relied on first.</p>
                    <ol className="mt-4 space-y-4">
                        {p.precedent.length === 0 && <li className="text-graphite">None in the corpus yet.</li>}
                        {p.precedent.map((j) => (
                            <li key={j.id}>
                                <p className="font-serif leading-snug">{titleCase(j.title)}</p>
                                <p className="mt-0.5 text-[13px] text-graphite">{j.citation || j.id}, {j.decided_on.slice(0, 4)}. Cites {j.via.map(label).join(" and ")}</p>
                            </li>
                        ))}
                    </ol>
                </section>

                {p.neighbours.length > 0 && (
                    <section>
                        <h2 className="font-serif text-base font-semibold">Nearby sections</h2>
                        <ul className="mt-3 space-y-1.5">
                            {p.neighbours.map((n) => (
                                <li key={n.id}>
                                    <Link href={href(n.id)} className="hover:text-stamp"><span className="figures inline-block w-10 text-graphite">{n.number}</span>{n.heading}</Link>
                                </li>
                            ))}
                        </ul>
                    </section>
                )}
            </aside>
        </div>
    );
}

// Old text beside new, every changed word marked. A merged section has several old sources, so
// each pair gets its own fold, the first one open.
function Changes({ id, both }: { id: string; both: Texts })
{
    const isOld = OLD.includes(id.split(":")[0]);
    const others = both.counterparts.filter((x) => x.id && both.texts[x.id] && both.texts[id]);
    if (others.length === 0)
    {
        return null;
    }
    return (
        <section id="changes" className="mt-14 scroll-mt-24 sm:ml-[192px]">
            <h2 className="font-serif text-lg font-semibold">How the wording changed</h2>
            <p className="mt-1 text-sm text-graphite">Old text on the left. On the right, the new text with added words marked and removed words struck through.</p>
            <div className="mt-4 divide-y divide-rule border-y border-rule">
                {others.map((o, i) =>
                {
                    const oldId = isOld ? id : o.id!;
                    const newId = isOld ? o.id! : id;
                    return (
                        <details key={o.id} open={i === 0} className="group py-4">
                            <summary className="cursor-pointer list-none text-sm">
                                <Ref id={oldId} link={oldId !== id} /> to <Ref id={newId} link={newId !== id} />
                                <span className="text-graphite">
                                    . {relation(o.relation)}{o.similarity !== null ? `, ${Math.round(o.similarity * 100)}% of the wording kept` : ""}
                                </span>
                                <span className="ml-2 text-stamp group-open:hidden">Show</span>
                            </summary>
                            <div className="mt-5 grid gap-8 md:grid-cols-2">
                                <p className="font-serif text-[16px] leading-[1.75] whitespace-pre-wrap text-graphite">{both.texts[oldId].text}</p>
                                <DiffView before={both.texts[oldId].text} after={both.texts[newId].text} />
                            </div>
                            {o.relation !== "equivalent" && (
                                <p className="mt-4 text-sm text-graphite">Not a one-to-one replacement, so some marked wording comes from the other sections merged here.</p>
                            )}
                        </details>
                    );
                })}
            </div>
        </section>
    );
}

function Part({ kind, label: tag, text, added, pending }: { kind: string; label: string; text: string; added: boolean; pending: boolean })
{
    if (kind === "illustration")
    {
        return <p className="pl-8 text-[16px] text-graphite"><span className="italic">{tag ? `Illustration ${tag}` : "Illustration"}.</span> {text}</p>;
    }
    const lead = kind === "explanation" || kind === "exception" || kind === "proviso"
        ? <span className="italic">{tag === "Proviso" ? "" : `${tag}. `}</span>
        : null;
    return (
        <p className={`relative ${kind === "subsection" ? "pl-10" : ""}`}>
            {kind === "subsection" && <span className="figures absolute left-0 text-graphite">{tag}</span>}
            {lead}
            <span className={added ? "bg-stamp-wash" : ""}>{text}</span>
            {pending && <span className="ml-2 font-sans text-sm text-amber">Not yet brought into force</span>}
        </p>
    );
}

function fmt(d: string | null): string
{
    if (!d)
    {
        return "";
    }
    return new Date(d).toLocaleDateString("en-IN", { day: "numeric", month: "long", year: "numeric" });
}
