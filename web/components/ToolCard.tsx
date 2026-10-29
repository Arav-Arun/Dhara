import Image from "next/image";

export type Tool = { name: string; cover: string; card: string; stat: string; points: string[]; cta: React.ReactNode };

// The inside of a home-page tool card, after the course covers on fanout.sh. The wrapper is a
// link for pages and a button for the ⌘K finder, so it is passed in rather than built here.
export function ToolBody({ t }: { t: Tool })
{
    return (
        <>
            <Folder src={`/art/cover-${t.cover}.jpg`} className="w-[56%] max-w-[230px] xl:w-[40%]" />
            <div className="flex flex-1 flex-col">
                <h3 className="text-[24px] leading-tight font-medium tracking-[-0.03em]">{t.name}</h3>
                <ul className="mt-3 space-y-1.5 text-[14px] text-ink/85">
                    {t.points.map((p) => <li key={p} className="flex gap-2"><span className="text-ink/50">+</span>{p}</li>)}
                </ul>
                <p className="mt-5 w-fit rounded-[4px] bg-sheet/70 px-3 py-1 text-[12px] text-ink/70">{t.stat}</p>
                <div className="mt-auto flex items-center justify-between pt-6 text-sm font-medium">
                    <span>{t.cta}</span>
                    <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" className="transition-transform group-hover:translate-x-1" aria-hidden="true"><path d="M2 8h11M9 4l4 4-4 4" /></svg>
                </div>
            </div>
        </>
    );
}

export function cardClass(t: Tool): string
{
    // cover above the text until the card is wide enough to set them side by side
    return `group flex flex-col gap-6 rounded-[18px] p-6 text-left xl:flex-row xl:items-center xl:gap-8 ${t.card}`;
}

// A file folder: printed front cover, two tabs peeking out on the right.
function Folder({ src, className }: { src: string; className: string })
{
    return (
        <div className={`relative shrink-0 ${className}`}>
            <div className="absolute top-[8%] -right-[7%] h-[24%] w-[12%] rounded-r-[8px] bg-black/15" />
            <div className="absolute top-[34%] -right-[7%] h-[22%] w-[12%] rounded-r-[8px] bg-black/10" />
            <div className="absolute inset-0 translate-x-[4%] rounded-[10px] bg-black/15" />
            <Image src={src} alt="" width={600} height={780}
                className="relative rounded-[10px] shadow-[0_14px_28px_-16px_rgba(0,0,0,.55)] ring-1 ring-black/10 transition-transform duration-300 group-hover:-translate-y-1 group-hover:-rotate-1" />
        </div>
    );
}
