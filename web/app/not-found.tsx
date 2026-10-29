import Link from "next/link";

export default function NotFound()
{
    return (
        <div className="mx-auto max-w-xl px-5 py-32 text-center">
            <h1 className="text-[38px] tracking-[-0.04em]">Nothing here</h1>
            <p className="mt-3 text-graphite">
                That section or judgment isn’t in Dhara. Press ⌘K to find a section by its old or new number, or ask in Research.
            </p>
            <Link href="/research" className="mt-8 inline-block rounded-[4px] bg-[#1d1d3a] px-5 py-2 text-sm text-white hover:bg-stamp">Go to Research</Link>
        </div>
    );
}
