"use client";

// Almost always the API waking from sleep on free hosting, so say that and offer to try again.
export default function Error({ retry }: { error: unknown; retry: () => void })
{
    return (
        <div className="mx-auto max-w-xl px-5 py-32 text-center">
            <h1 className="text-[38px] tracking-[-0.04em]">Starting up</h1>
            <p className="mt-3 text-graphite">
                Dhara’s search service sleeps when nobody is using it and takes up to a minute to wake. Try again in a few seconds.
            </p>
            <button onClick={retry} className="mt-8 rounded-[4px] bg-[#1d1d3a] px-5 py-2 text-sm text-white hover:bg-stamp">Try again</button>
        </div>
    );
}
