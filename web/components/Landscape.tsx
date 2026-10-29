type Mark = "yes" | "no" | "partly";
type Row = { need: string; cells: [Mark, string][] };

const TOOLS = ["Government portals", "Court judgment search", "General AI chatbots", "Dhara"];

// Each claim here is about what the free, public options do by design, not about any one product's
// bugs. Paid databases are left out: their features change and we can't check them fairly.
const ROWS: Row[] =
    [
        {
            need: "Official text of the new codes, with the section each one replaced",
            cells: [["yes", "NCRB Sankalan"], ["no", ""], ["partly", "From memory, unchecked"], ["yes", "Both, linked part by part"]],
        },
        {
            need: "Judgments on IPC 302 when you ask about BNS 103",
            cells: [["no", "Statutes only"], ["partly", "Only if you type the old number"], ["no", "No judgment corpus"], ["yes", "Searches both numberings at once"]],
        },
        {
            need: "Ask in plain words, get an answer",
            cells: [["no", "Look up by section or keyword"], ["no", "Party, date or keyword"], ["yes", ""], ["yes", ""]],
        },
        {
            need: "Every statement tied to a passage you can read",
            cells: [["no", ""], ["no", ""], ["no", "Citations are not checked"], ["yes", "Unsupported statements removed"]],
        },
        {
            need: "The law as it stood on a given date",
            cells: [["partly", "Commencement notes"], ["no", ""], ["no", ""], ["yes", "Old code before 1 July 2024, new after"]],
        },
        {
            need: "Accuracy measured on held-out questions",
            cells: [["no", ""], ["no", ""], ["no", ""], ["yes", "Published on the Method page"]],
        },
    ];

const MARK: Record<Mark, [string, string]> =
    {
        yes: ["Yes", "M3.5 8.5l3 3 6-7"],
        partly: ["Partly", "M4 8h8"],
        no: ["No", "M4.5 4.5l7 7M11.5 4.5l-7 7"],
    };

export default function Landscape()
{
    return (
        <>
            <Table />
            {/* on a phone the table becomes one card per need, so nothing scrolls sideways */}
            <ul className="space-y-3 md:hidden">
                {ROWS.map((r) => (
                    <li key={r.need} className="rounded-[14px] bg-sheet p-4 ring-1 ring-rule">
                        <h3 className="text-[15px] leading-snug">{r.need}</h3>
                        <dl className="mt-3 divide-y divide-rule text-sm">
                            {r.cells.map(([mark, note], i) => (
                                <div key={i} className={`grid grid-cols-[42%_1fr] gap-3 py-2 ${i === TOOLS.length - 1 ? "-mx-2 rounded-[8px] bg-stamp/[.06] px-2" : ""}`}>
                                    <dt className={i === TOOLS.length - 1 ? "font-medium text-stamp" : "text-graphite"}>{TOOLS[i]}</dt>
                                    <dd><Cell mark={mark} note={note} ours={i === TOOLS.length - 1} /></dd>
                                </div>
                            ))}
                        </dl>
                    </li>
                ))}
            </ul>
        </>
    );
}

function Table()
{
    return (
        <div className="hidden overflow-hidden rounded-[18px] bg-sheet ring-1 ring-rule md:block">
            <table className="w-full text-left text-sm">
                <thead>
                    <tr className="border-b border-rule">
                        <th className="w-[28%] px-5 py-4 font-normal text-graphite">What you need</th>
                        {TOOLS.map((t, i) => (
                            <th key={t} className={`px-4 py-4 font-medium ${i === TOOLS.length - 1 ? "bg-stamp/[.06] text-stamp" : ""}`}>{t}</th>
                        ))}
                    </tr>
                </thead>
                <tbody>
                    {ROWS.map((r) => (
                        <tr key={r.need} className="border-b border-rule last:border-0 align-top">
                            <td className="px-5 py-4 text-ink/85">{r.need}</td>
                            {r.cells.map(([mark, note], i) => (
                                <td key={i} className={`px-4 py-4 ${i === TOOLS.length - 1 ? "bg-stamp/[.06]" : ""}`}>
                                    <Cell mark={mark} note={note} ours={i === TOOLS.length - 1} />
                                </td>
                            ))}
                        </tr>
                    ))}
                </tbody>
            </table>
        </div>
    );
}

function Cell({ mark, note, ours }: { mark: Mark; note: string; ours: boolean })
{
    const [word, path] = MARK[mark];
    const tone = mark === "yes" ? (ours ? "text-stamp" : "text-green") : mark === "partly" ? "text-amber" : "text-graphite/70";
    return (
        <div>
            <span className={`inline-flex items-center gap-1.5 font-medium ${tone}`}>
                <svg width="14" height="14" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.8" aria-hidden="true"><path d={path} /></svg>
                {word}
            </span>
            {note && <p className="mt-0.5 text-[13px] leading-snug text-graphite">{note}</p>}
        </div>
    );
}
