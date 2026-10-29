import Image from "next/image";
import Link from "next/link";
import FindCard from "@/components/FindCard";
import Landscape from "@/components/Landscape";
import { ToolBody, cardClass, type Tool } from "@/components/ToolCard";
import AskBox from "@/components/AskBox";
import { BareAct, GazettePage, JudgmentPage, OldVolume, Ornament, Renumbered } from "@/components/Artifacts";
import { optional } from "@/lib/data";

const COVERAGE: [string, string, string][] =
    [
        ["The six criminal codes", "BNS, BNSS and BSA, and the IPC, CrPC and Evidence Act they replaced: 2,353 sections, with the BNSS First Schedule.", "NCRB Sankalan and India Code"],
        ["The official old-to-new tables", "1,310 links between the old and new sections, down to the subsection, each marked renumbered, merged, split or new.", "NCRB correspondence tables"],
        ["Supreme Court judgments", "9,686 criminal judgments of the Supreme Court of India, May 1950 to September 2026, with every section they cite.", "Supreme Court reports, via AWS Open Data"],
    ];

type Meta = { provisions: Record<string, number>; mapping_pairs: number; judgments: number };
type Page = Tool & { to: string };

const TOOLS: Page[] = [
    { to: "/research", name: "Research", cover: "research", card: "bg-[#e6def8]", stat: "9,686 Supreme Court judgments", cta: "Open",
        points: ["Ask about any offence, procedure or rule of evidence", "Finds precedent under old and new section numbers", "Every statement cites its source", "Follow-up questions keep the context"] },
    { to: "/judgments", name: "Judgments in today’s numbers", cover: "judgments", card: "bg-[#f6e7b0]", stat: "159,686 section references linked", cta: "Open",
        points: ["Search by section, case name or citation", "A BNS search finds the IPC-era judgments", "Every old section in the text shows its new number"] },
    { to: "/check", name: "Check a draft", cover: "check", card: "bg-[#f3d3cc]", stat: "Every citation checked", cta: "Open",
        points: ["Paste a draft, FIR or chargesheet", "Catches repealed and wrong-code sections", "Suggests the right section for the offence date"] },
];

export default async function Home()
{
    const meta = await optional<Meta>("/v1/meta");
    const sections = meta ? Object.values(meta.provisions).reduce((a, b) => a + b, 0) : null;
    return (
        <div>
            <section className="wash relative overflow-hidden">
                {/* on tablet widths the same desk, smaller, kept whole and set symmetrically in the margins */}
                <div className="pointer-events-none absolute inset-0 hidden lg:block" aria-hidden="true">
                    <div className="absolute top-16 left-[2%] origin-top-left -rotate-[8deg] scale-[.55] xl:top-14 xl:left-[3%] xl:scale-100"><OldVolume /></div>
                    <div className="absolute top-24 left-[5.5%] origin-top-left rotate-[5deg] scale-[.55] xl:left-[10%] xl:scale-100"><BareAct /></div>
                    <div className="absolute bottom-12 left-[2.5%] origin-bottom-left -rotate-[4deg] scale-[.55] xl:bottom-10 xl:left-[4%] xl:scale-100"><GazettePage /></div>
                    <div className="absolute top-14 right-[2%] origin-top-right rotate-[4deg] scale-[.55] xl:top-12 xl:right-[4%] xl:scale-100"><JudgmentPage /></div>
                    <div className="absolute top-[232px] right-[2%] hidden xl:block"><Renumbered from="IPC 302" to="BNS 103" /></div>
                    <div className="absolute right-[2%] bottom-12 origin-bottom-right rotate-[3deg] scale-[.55] rounded-[6px] bg-[#efe9dc] p-3 shadow-[0_22px_44px_-22px_rgba(0,0,0,.5)] xl:right-[5%] xl:bottom-8 xl:scale-100">
                        <Image src="/art/justitia.webp" alt="" width={210} height={297} className="mix-blend-multiply" priority />
                    </div>
                </div>

                <div className="relative mx-auto max-w-3xl px-5 pt-20 pb-24 text-center">
                    <Ornament className="mx-auto h-5 text-stamp" />
                    <p className="mx-auto mt-3 w-fit rounded-[4px] border border-stamp/15 bg-sheet/70 px-3 py-1 text-[13px] text-stamp">
                        Research assistant for Indian criminal law
                    </p>
                    <h1 className="mt-6 text-[46px] leading-[1.02] font-normal tracking-[-0.045em] sm:text-[72px]">
                        Ask anything about Indian criminal law.
                    </h1>
                    <p className="mx-auto mt-6 max-w-xl text-[17px] leading-relaxed text-graphite">
                        Offences, bail, arrest, evidence, procedure. Dhara reads the new codes, the old ones and the Supreme
                        Court’s criminal judgments together, and answers with the sources it used, under both section numbers.
                    </p>
                    <div className="mt-10"><AskBox /></div>
                </div>
            </section>

            <section className="mx-auto max-w-6xl px-5 pt-20">
                <div className="mx-auto max-w-2xl text-center">
                    <h2 className="text-[34px] tracking-[-0.035em]">Everything a criminal practice needs during the switch</h2>
                    <p className="mt-2 text-graphite">Research is the core. The others answer the questions that come up every day since 1 July 2024.</p>
                </div>
                <div className="mt-10 grid gap-5 md:grid-cols-2">
                    {TOOLS.map((t) => <Link key={t.to} href={t.to} className={cardClass(t)}><ToolBody t={t} /></Link>)}
                    <FindCard />
                </div>
            </section>

            <section className="mx-auto max-w-6xl px-5 py-24">
                <div className="grid gap-10 rounded-[20px] bg-sheet p-8 sm:p-12 lg:grid-cols-[1.3fr_1fr]">
                    <div>
                        <h2 className="text-[32px] leading-tight tracking-[-0.035em]">Why ordinary search falls short now</h2>
                        <p className="mt-5 font-serif text-[18px] leading-[1.7] text-ink/85">
                            In Supreme Court criminal judgments decided after July 2024, old-code citations still outnumber
                            new-code ones by about nineteen to one. A search that reads only “BNS 103” misses more than three
                            thousand judgments on IPC 302. Dhara searches both numberings at once, so the precedent is there
                            whichever code your question uses.
                        </p>
                    </div>
                    <dl className="grid grid-cols-2 gap-6 self-end">
                        <div><dt className="text-sm text-graphite">BNS sections cited by their new number</dt><dd className="figures mt-1 text-[40px] tracking-[-0.03em]">58</dd></div>
                        <div><dt className="text-sm text-graphite">Reachable through the old code</dt><dd className="figures mt-1 text-[40px] tracking-[-0.03em] text-stamp">321</dd></div>
                        {meta && <div><dt className="text-sm text-graphite">Sections across six codes</dt><dd className="figures mt-1 text-[28px]">{sections?.toLocaleString("en-IN")}</dd></div>}
                        {meta && <div><dt className="text-sm text-graphite">Supreme Court judgments</dt><dd className="figures mt-1 text-[28px]">{meta.judgments.toLocaleString("en-IN")}</dd></div>}
                    </dl>
                </div>

                <div className="mx-auto mt-24 max-w-2xl text-center">
                    <h2 className="text-[34px] tracking-[-0.035em]">What Dhara answers from</h2>
                    <p className="mt-2 text-graphite">Every answer comes from these sources and cites them. Anything else, such as civil, tax or family law, is declined rather than guessed.</p>
                </div>
                <div className="mx-auto mt-10 grid max-w-5xl gap-4 md:grid-cols-3">
                    {COVERAGE.map(([title, what, source]) => (
                        <div key={title} className="rounded-[18px] bg-sheet p-6 ring-1 ring-rule">
                            <h3 className="text-[17px] tracking-[-0.01em]">{title}</h3>
                            <p className="mt-2 text-[14px] leading-relaxed text-graphite">{what}</p>
                            <p className="mt-4 text-[13px] text-stamp">{source}</p>
                        </div>
                    ))}
                </div>

                <div className="mx-auto mt-24 max-w-2xl text-center">
                    <h2 className="text-[34px] tracking-[-0.035em]">What’s out there, and what it misses</h2>
                    <p className="mt-2 text-graphite">
                        The free options each cover one piece. None connects the new codes to the judgments written under the old ones.
                    </p>
                </div>
                <div className="mt-10"><Landscape /></div>
            </section>
        </div>
    );
}
