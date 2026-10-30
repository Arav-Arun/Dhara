import { optional } from "@/lib/data";
import { Heading } from "@/components/ui";
import Landscape from "@/components/Landscape";

type Meta =
    {
        provisions: Record<string, number>;
        mapping_pairs: number;
        judgments: number;
        relations: Record<string, number>;
        passages: number;
        references: number;
    };
type Results = Record<string, Record<string, Record<string, number> | number>>;

const RELATIONS: [string, string][] =
    [
        ["equivalent", "Renumbered, same text or nearly"],
        ["merged", "Merged with other sections"],
        ["partial", "Partly moved"],
        ["split", "Split across several"],
        ["new", "New, no earlier section"],
        ["omitted", "Dropped"],
    ];

const SEARCHES =
    [
        ["Keyword search", "Exact words, case names and legal terms. Section numbers are set aside here, so they cannot drown out the words.", "BM25"],
        ["Citation graph", "Judgments that cite the sections you named, under either numbering.", "Section references"],
        ["Meaning search", "The same idea put in different words.", "bge-m3, dense"],
        ["Weighted terms", "Rare, telling words, weighted by a learned model.", "bge-m3, sparse"],
    ];

export const metadata = { title: "How it works" };

export default async function Method()
{
    const [meta, results] = await Promise.all([optional<Meta>("/v1/meta"), optional<Results>("/v1/results")]);
    const p = meta?.provisions ?? {};
    const sum = (acts: string[]) => acts.reduce((a, b) => a + (p[b] ?? 0), 0);
    return (
        <div>
            <Heading sub="What Dhara reads, how it finds what you need, and how every answer is checked before you see it.">
                How Dhara works
            </Heading>

            <Section title="What it reads" sub="Four public sources, read once and joined into one library.">
                <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
                    <Source tint="bg-[#e6def8]" name="The new codes" from="NCRB Sankalan portal"
                        figure={sum(["BNS", "BNSS", "BSA"])} unit="sections"
                        what="BNS, BNSS and BSA, with NCRB’s marking of what changed and the commencement dates from the Gazette."
                        becomes="Each section split into sub-sections, provisos, explanations and illustrations." />
                    <Source tint="bg-[#f6e7b0]" name="The old codes" from="India Code"
                        figure={sum(["IPC", "CRPC", "IEA"])} unit="sections"
                        what="IPC, CrPC and the Indian Evidence Act, as last amended before 1 July 2024."
                        becomes="Split the same way, so old and new can be compared part by part." />
                    <Source tint="bg-[#c6e3df]" name="The correspondence tables" from="NCRB"
                        figure={meta?.mapping_pairs} unit="official links"
                        what="Which old section became which new one."
                        becomes="Each link labelled by what happened to the section.">
                        {meta?.relations && <Relations counts={meta.relations} />}
                    </Source>
                    <Source tint="bg-[#f3d3cc]" name="Supreme Court judgments" from="Dattam Labs dataset, CC-BY-4.0"
                        figure={meta?.judgments} unit="criminal judgments"
                        what="From 1950 onwards, headnotes and full text."
                        becomes={meta?.passages
                            ? `${fmt(meta.passages)} passages, with ${fmt(meta.references)} section references linked to the statute.`
                            : "Split into passages, with every section reference linked to the statute."} />
                </div>
            </Section>

            <Section title="Compared with what exists" sub="Government portals hold the text and the tables. Court search holds the judgments. Chatbots answer but don’t check. Dhara joins all three and checks every citation.">
                <div className="mx-auto max-w-5xl"><Landscape /></div>
            </Section>

            <Section title="How a question is answered" sub="One question, followed through every step.">
                <ol className="relative mx-auto max-w-4xl">
                    <Step n={1} title="Your question">
                        <p className="rounded-[14px] border border-rule bg-sheet px-5 py-4 text-[17px]">
                            Can the High Court quash a case under <span className="text-stamp">BNS 316</span> once the parties settle?
                        </p>
                    </Step>
                    <Step n={2} title="Both numberings"
                        text="Section numbers are read and joined to their counterparts in the other code, using the official tables.">
                        <div className="flex flex-wrap items-center gap-3 text-[15px]">
                            <Chip tone="new">BNS 316</Chip>
                            <span className="text-graphite">replaces</span>
                            <Chip tone="old">IPC 405 to 409</Chip>
                        </div>
                        <p className="mt-3 text-[15px] text-graphite">
                            Only 2 judgments in the library cite BNS 316. 592 cite the IPC sections it replaced. Searching the new number alone
                            would miss nearly all of them.
                        </p>
                    </Step>
                    <Step n={3} title="Four searches at once" text="Each finds a hundred candidates its own way.">
                        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
                            {SEARCHES.map(([name, what, tag]) => (
                                <div key={name} className="flex flex-col rounded-[14px] bg-sheet p-4 ring-1 ring-rule">
                                    <h4 className="font-medium">{name}</h4>
                                    <p className="mt-1.5 text-[14px] leading-snug text-graphite">{what}</p>
                                    <p className="mt-auto pt-3 text-[12px] text-stamp">{tag}</p>
                                </div>
                            ))}
                        </div>
                        <FanIn />
                    </Step>
                    <Step n={4} title="Merge and re-rank"
                        text="The four lists are merged by rank. A cross-encoder fine-tuned on Indian criminal judgments then re-reads the top 50 judgment passages next to your question and puts them in order; on held-out questions it finds the right judgment in the top 10 more often than any search alone. The same model checks that the question is about criminal law at all. The best 8 sections and 12 judgments go forward.">
                        <Tags items={["Reciprocal rank fusion", "Fine-tuned cross-encoder", "Out-of-scope check"]} />
                    </Step>
                    <Step n={5} title="A second look"
                        text="If something is missing, such as the procedural provision that goes with an offence, Dhara runs up to two more searches. Here it would look for the High Court’s inherent powers, BNSS 528, once CrPC 482. Each extra search is shown to you." />
                    <Step n={6} title="The answer"
                        text="Written only from the passages retrieved. Every statement cites one, and judgments are named with their year and citation.">
                        <Tags items={["Short answer first", "Section and judgment cited per statement"]} />
                    </Step>
                    <Step n={7} title="Every citation checked" last>
                        <ul className="grid gap-2 sm:grid-cols-3">
                            {["The passage was really retrieved", "The section exists", "It was in force on the date"].map((c) => (
                                <li key={c} className="flex items-center gap-2 rounded-[12px] bg-sheet px-3 py-2.5 text-[14px] ring-1 ring-rule">
                                    <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.8" className="shrink-0 text-green" aria-hidden="true"><path d="m3.5 8.5 3 3 6-7" /></svg>
                                    {c}
                                </li>
                            ))}
                        </ul>
                        <p className="mt-3 text-[15px] text-graphite">
                            A citation that fails is removed. When the sources are too weak to answer, Dhara says so instead of guessing.
                        </p>
                    </Step>
                </ol>
            </Section>

            {results && Object.keys(results).length > 0 && <Scores results={results} />}
        </div>
    );
}

function Section({ title, sub, children }: { title: string; sub: string; children: React.ReactNode })
{
    return (
        <section className="mt-16 first-of-type:mt-4">
            <div className="mx-auto mb-8 max-w-2xl text-center">
                <h2 className="text-[30px] tracking-[-0.035em]">{title}</h2>
                <p className="mt-2 text-graphite">{sub}</p>
            </div>
            {children}
        </section>
    );
}

type SourceProps =
    {
        tint: string;
        name: string;
        from: string;
        figure?: number;
        unit: string;
        what: string;
        becomes: string;
        children?: React.ReactNode;
    };

function Source({ tint, name, from, figure, unit, what, becomes, children }: SourceProps)
{
    return (
        <article className={`flex flex-col rounded-[18px] p-5 ${tint}`}>
            <p className="text-[13px] text-ink/60">{from}</p>
            <h3 className="mt-1 text-[20px] font-medium tracking-[-0.02em]">{name}</h3>
            {figure !== undefined && (
                <p className="mt-4"><span className="figures text-[34px] tracking-[-0.03em]">{fmt(figure)}</span> <span className="text-[14px] text-ink/70">{unit}</span></p>
            )}
            <p className="mt-3 text-[14px] leading-snug text-ink/80">{what}</p>
            {children}
            <p className="mt-auto border-t border-ink/10 pt-3 text-[13px] leading-snug text-ink/70">
                <span className="text-ink">Becomes </span>{becomes.charAt(0).toLowerCase() + becomes.slice(1)}
            </p>
        </article>
    );
}

// One hue throughout: the bars only carry magnitude, and the label beside each says what it is.
function Relations({ counts }: { counts: Record<string, number> })
{
    const max = Math.max(...Object.values(counts));
    return (
        <ul className="mt-4 mb-4 space-y-1.5 text-[12px]">
            {RELATIONS.filter(([k]) => counts[k]).map(([k, name]) => (
                <li key={k} title={`${name}: ${counts[k]}`}>
                    <div className="flex justify-between text-ink/75"><span>{name}</span><span className="figures">{fmt(counts[k])}</span></div>
                    <div className="mt-0.5 h-1.5 rounded-full bg-sheet/60">
                        <div className="h-full rounded-full bg-[#2f6f68]" style={{ width: `${Math.max(2, (counts[k] / max) * 100)}%` }} />
                    </div>
                </li>
            ))}
        </ul>
    );
}

function Step({ n, title, text, last, children }: { n: number; title: string; text?: string; last?: boolean; children?: React.ReactNode })
{
    return (
        <li className={`relative grid grid-cols-[32px_1fr] gap-5 ${last ? "" : "pb-10"}`}>
            {!last && <span className="absolute top-8 bottom-0 left-[15px] w-px bg-rule" aria-hidden="true" />}
            <span className="figures relative z-10 flex h-8 w-8 items-center justify-center rounded-full bg-[#1d1d3a] text-[13px] text-white">{n}</span>
            <div className="pt-1">
                <h3 className="text-[20px] tracking-[-0.02em]">{title}</h3>
                {text && <p className="mt-1.5 max-w-[68ch] leading-relaxed text-graphite">{text}</p>}
                {children && <div className="mt-4">{children}</div>}
            </div>
        </li>
    );
}

// Four lines meeting in one point, under the four search cards: the lists becoming one.
function FanIn()
{
    return (
        <svg viewBox="0 0 400 36" preserveAspectRatio="none" className="hidden h-9 w-full text-graphite/40 lg:block" aria-hidden="true">
            {[50, 150, 250, 350].map((x) => <path key={x} d={`M${x} 0 C${x} 22, 200 14, 200 36`} fill="none" stroke="currentColor" vectorEffect="non-scaling-stroke" />)}
        </svg>
    );
}

function Chip({ tone, children }: { tone: "new" | "old"; children: React.ReactNode })
{
    return (
        <span className={`figures rounded-[4px] px-3 py-1 font-medium ${tone === "new" ? "bg-stamp/10 text-stamp" : "bg-old/10 text-old"}`}>{children}</span>
    );
}

function Tags({ items }: { items: string[] })
{
    return (
        <div className="flex flex-wrap gap-2">
            {items.map((t) => <span key={t} className="rounded-[4px] bg-sheet px-3 py-1 text-[13px] text-stamp ring-1 ring-rule">{t}</span>)}
        </div>
    );
}

// Each setup adds one piece to the one above it, so the bars read as the gain from that piece.
function Scores({ results }: { results: Results })
{
    const rows = Object.entries(results).map(([name, r]) =>
        ({
            name,
            precedent: (r.precedent as Record<string, number>)?.["recall@10"] ?? 0,
            statute: (r.statute as Record<string, number>)?.["ndcg@10"],
        }));
    const best = Math.max(...rows.map((r) => r.precedent));
    return (
        <Section title="How well it works"
            sub="Measured on questions whose right answers we know, kept apart from everything the system was built or trained on. The bars show how often the right judgment is in the top ten.">
            <div className="mx-auto max-w-4xl rounded-[18px] bg-sheet p-6 ring-1 ring-rule sm:p-8">
                <ul className="space-y-3">
                    {rows.map((r) => (
                        <li key={r.name} className="grid items-center gap-x-4 gap-y-1 sm:grid-cols-[minmax(0,1fr)_minmax(0,1.3fr)]"
                            title={`${r.name}: ${pct(r.precedent)} judgments, ${pct(r.statute)} sections`}>
                            <span className="text-[14px] text-ink/85">{r.name}</span>
                            <div className="flex items-center gap-3">
                                <div className="h-2.5 flex-1 rounded-full bg-paper">
                                    <div className={`h-full rounded-full ${r.precedent === best ? "bg-stamp" : "bg-periwinkle"}`} style={{ width: `${r.precedent * 100}%` }} />
                                </div>
                                <span className="figures w-10 text-right text-[14px]">{pct(r.precedent)}</span>
                            </div>
                        </li>
                    ))}
                </ul>
                <details className="mt-6 text-sm">
                    <summary className="cursor-pointer text-graphite">Show as a table, with section ranking</summary>
                    <table className="figures mt-4 w-full text-left">
                        <thead className="text-graphite"><tr className="border-b border-rule"><th className="py-2 font-normal">Search setup</th><th className="font-normal">Right judgment in the top 10</th><th className="font-normal">Right section ranked first or near it</th></tr></thead>
                        <tbody>
                            {rows.map((r) => (
                                <tr key={r.name} className="border-b border-rule"><td className="py-2">{r.name}</td><td>{pct(r.precedent)}</td><td>{pct(r.statute)}</td></tr>
                            ))}
                        </tbody>
                    </table>
                </details>
            </div>
        </Section>
    );
}

function fmt(n: number | undefined): string
{
    return n === undefined ? "" : n.toLocaleString("en-IN");
}

function pct(x: number | undefined): string
{
    return x === undefined ? "" : `${Math.round(x * 100)}%`;
}
