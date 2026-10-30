import "server-only";
import { cacheLife } from "next/cache";
import { API } from "@/lib/api";

// Statutes, the mapping and precedent lists only change when the corpus is rebuilt, so server
// pages cache them for a day. Pages stay fast (and keep working) even if the API is asleep.
// A sleeping API takes a while to wake, so wait for it; if it still hasn't answered, error.tsx
// waits on and reloads the page. Only a real 404 returns null.
export async function cached<T>(path: string): Promise<T | null>
{
    "use cache";
    cacheLife("days");
    const res = await fetch(`${API}${path}`, { signal: AbortSignal.timeout(40000) });
    if (res.status === 404)
    {
        return null;
    }
    if (!res.ok)
    {
        throw new Error(`The Dhara API answered ${res.status}`);
    }
    return res.json() as Promise<T>;
}

// For page extras (counts, scores) that can be left out while the API is away, including during
// a build. A miss is only kept for a few minutes, so the page fills in once the API answers.
export async function optional<T>(path: string): Promise<T | null>
{
    "use cache";
    try
    {
        const res = await fetch(`${API}${path}`, { signal: AbortSignal.timeout(9000) });
        if (res.ok)
        {
            cacheLife("days");
            return (await res.json()) as T;
        }
    }
    catch
    {
        // asleep or unreachable: fall through
    }
    cacheLife("minutes");
    return null;
}
