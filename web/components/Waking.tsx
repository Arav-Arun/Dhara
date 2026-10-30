"use client";

import { useEffect, useState } from "react";
import { API } from "@/lib/api";

// Pings the API when a page opens. If it hasn't answered within a few seconds it is probably
// waking from sleep on free hosting, so say so instead of letting the page look broken.
export default function Waking()
{
    const [state, setState] = useState<"ok" | "slow" | "down">("ok");

    useEffect(() =>
    {
        const started = Date.now();
        let stop = false;
        const slow = setTimeout(() => !stop && setState((s) => (s === "ok" ? "slow" : s)), 3000);
        (async () =>
        {
            // a waking instance can refuse connections at first, so keep asking for two minutes
            while (!stop && Date.now() - started < 120000)
            {
                const ok = await fetch(`${API}/v1/meta`, { signal: AbortSignal.timeout(90000) })
                    .then((r) => r.ok)
                    .catch(() => false);
                if (ok)
                {
                    stop = true;
                    setState("ok");
                    return;
                }
                setState("slow");
                await new Promise((r) => setTimeout(r, 3000));
            }
            if (!stop)
            {
                setState("down");
            }
        })();
        return () =>
        {
            stop = true;
            clearTimeout(slow);
        };
    }, []);

    if (state === "ok")
    {
        return null;
    }
    return (
        <div role="status" className="fixed inset-x-0 bottom-5 z-40 mx-auto w-fit max-w-[calc(100%-32px)] rounded-[4px] bg-[#1d1d3a] px-4 py-2.5 text-center text-[13px] text-white shadow-lg">
            {state === "slow"
                ? "Waking the search service. The first request after a quiet spell takes up to a minute."
                : "The search service isn’t answering right now. Please try again shortly."}
        </div>
    );
}
