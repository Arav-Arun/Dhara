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
        let answered = false;
        const slow = setTimeout(() => !answered && setState("slow"), 3000);
        fetch(`${API}/v1/meta`, { signal: AbortSignal.timeout(90000) })
            .then((r) =>
            {
                answered = true;
                setState(r.ok ? "ok" : "down");
            })
            .catch(() =>
            {
                answered = true;
                setState("down");
            });
        return () => clearTimeout(slow);
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
