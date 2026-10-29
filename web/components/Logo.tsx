import Link from "next/link";

// Scales of justice drawn with the same stroke weight as the wordmark's stems.
function Scales({ size = 26 }: { size?: number })
{
    return (
        <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5"
            strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
            <path d="M12 3.5v16" />
            <path d="M8.5 20h7" />
            <path d="M4.5 7h15" />
            <circle cx="12" cy="4.5" r="1" fill="currentColor" stroke="none" />
            <path d="M4.5 7 2 13M4.5 7 7 13" />
            <path d="M1.5 13a3 3 0 0 0 6 0Z" />
            <path d="M19.5 7 17 13M19.5 7 22 13" />
            <path d="M16.5 13a3 3 0 0 0 6 0Z" />
        </svg>
    );
}

export default function Logo()
{
    return (
        <Link href="/" className="flex items-center gap-2 text-ink" aria-label="Dhara home">
            <span className="text-stamp"><Scales /></span>
            <span className="text-[22px] font-medium tracking-[-0.03em]">Dhara</span>
        </Link>
    );
}
