"use client";

import { useEffect, useState } from "react";
import { API } from "@/lib/api";

// Almost always the API waking from sleep on free hosting: wait for it to answer, then reload
// the page by itself, so nobody has to keep pressing a button.
export default function Error({ retry }: { error: unknown; retry: () => void })
{
    const [seconds, setSeconds] = useState(0);
    const [gaveUp, setGaveUp] = useState(false);

    useEffect(() =>
    {
        const started = Date.now();
        let stop = false;
        const tick = setInterval(() => setSeconds(Math.round((Date.now() - started) / 1000)), 1000);
        (async () =>
        {
            while (!stop && Date.now() - started < 120000)
            {
                const ok = await fetch(`${API}/v1/meta`, { signal: AbortSignal.timeout(20000) })
                    .then((r) => r.ok)
                    .catch(() => false);
                if (ok)
                {
                    if (!stop)
                    {
                        retry();
                    }
                    return;
                }
                await new Promise((r) => setTimeout(r, 3000));
            }
            if (!stop)
            {
                setGaveUp(true);
            }
        })();
        return () =>
        {
            stop = true;
            clearInterval(tick);
        };
    }, [retry]);

    return (
        <div className="mx-auto max-w-xl px-5 py-32 text-center">
            <h1 className="text-[38px] tracking-[-0.04em]">{gaveUp ? "Not answering" : "Starting up"}</h1>
            <p className="mt-3 text-graphite">
                {gaveUp
                    ? "Dhara’s search service isn’t answering right now. Please try again shortly."
                    : `Dhara’s search service is waking up. This page will load by itself in a moment (${seconds}s).`}
            </p>
            {gaveUp && (
                <button onClick={retry} className="mt-8 rounded-[4px] bg-[#1d1d3a] px-5 py-2 text-sm text-white hover:bg-stamp">Try again</button>
            )}
        </div>
    );
}
