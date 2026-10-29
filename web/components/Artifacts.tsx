// The objects on an Indian criminal lawyer's desk, drawn in HTML and CSS for the landing hero.

const LINE = { fill: "none", stroke: "currentColor", strokeWidth: 1.6, strokeLinecap: "round", strokeLinejoin: "round" } as const;

export function Ornament({ className = "" }: { className?: string })
{
    return (
        <svg viewBox="0 0 120 20" className={className} aria-hidden="true">
            <g {...LINE} strokeWidth={1.3}>
                <path d="M6 14h30M84 14h30" />
                <path d="M36 14c4-10 14-10 14-2 0 5-6 6-8 3M84 14c-4-10-14-10-14-2 0 5 6 6 8 3" />
                <circle cx="60" cy="10" r="3.5" />
                <path d="M53 14q7 6 14 0" />
            </g>
        </svg>
    );
}

export function BareAct()
{
    return (
        <div className="relative h-64 w-48 overflow-hidden rounded-[6px] bg-[#9e2a24] p-4 text-[#f3e6d0] shadow-[0_18px_40px_-18px_rgba(0,0,0,.45)]">
            <div className="halftone absolute inset-0 text-[#f3e6d0] opacity-25" />
            <div className="relative flex h-full flex-col border border-[#f3e6d0]/50 p-3">
                <p className="text-[10px]">Bare Act with short notes</p>
                <p className="mt-4 font-serif text-[18px] leading-[1.2]">The Bharatiya Nyaya Sanhita, 2023</p>
                <div className="mt-auto space-y-0.5 text-[10px] leading-snug opacity-80">
                    <p>Act 45 of 2023</p>
                    <p>In force from 1 July 2024</p>
                </div>
            </div>
        </div>
    );
}

export function OldVolume()
{
    return (
        <div className="relative h-56 w-40 overflow-hidden rounded-[4px] bg-[#2f4a3a] p-4 text-[#e8dcc0] shadow-[0_18px_40px_-18px_rgba(0,0,0,.45)]">
            <div className="absolute inset-y-0 left-3 w-px bg-[#e8dcc0]/30" />
            <p className="mt-8 text-center font-serif text-[19px] leading-tight">The Indian Penal Code</p>
            <p className="mt-1 text-center font-serif text-[13px] italic opacity-80">1860</p>
            <div className="mx-auto mt-6 h-px w-16 bg-[#e8dcc0]/50" />
            <p className="mt-6 text-center text-[10px] opacity-70">In force until 30 June 2024</p>
        </div>
    );
}

export function GazettePage()
{
    return (
        <div className="w-60 rounded-[4px] bg-sheet p-4 text-[9px] leading-[1.5] text-graphite shadow-[0_14px_36px_-18px_rgba(0,0,0,.35)]">
            <p className="text-center font-serif text-[13px] text-ink">The Gazette of India</p>
            <p className="text-center">Extraordinary, Part II, Section 3</p>
            <div className="my-2 h-px bg-rule" />
            <p className="font-medium text-ink">S.O. 850(E). 23 February 2024</p>
            <p className="mt-1">
                In exercise of the powers conferred by sub-section (2) of section 1 of the Bharatiya Nyaya Sanhita,
                2023, the Central Government hereby appoints the 1st day of July, 2024 as the date on which the
                provisions of the said Sanhita, except sub-section (2) of section 106, shall come into force.
            </p>
        </div>
    );
}

export function JudgmentPage()
{
    return (
        <div className="w-64 rounded-[4px] bg-sheet p-4 text-[9px] leading-[1.55] text-graphite shadow-[0_14px_36px_-18px_rgba(0,0,0,.35)]">
            <p className="text-ink">[2025] 10 S.C.R. 131</p>
            <p className="mt-1 font-serif text-[12px] text-ink">Mamman Khan v. State of Haryana</p>
            <div className="my-2 h-px bg-rule" />
            <p>
                Code of Criminal Procedure, 1973, s.223 (now s.246 of the Bharatiya Nagarik Suraksha Sanhita, 2023):
                joint trial of persons accused of the same offence committed in the course of the same transaction…
            </p>
        </div>
    );
}

export function Renumbered({ from, to }: { from: string; to: string })
{
    return (
        <div className="flex items-center gap-3 rounded-full bg-ink px-4 py-2.5 text-[13px] text-paper shadow-lg">
            <span className="text-[#d9c39a]">{from}</span>
            <span className="opacity-50">now</span>
            <span className="font-medium">{to}</span>
        </div>
    );
}
