// Thin typed client for the Dhara API. Server components call it directly; client
// components use the same functions in the browser.

export const API = process.env.NEXT_PUBLIC_DHARA_API ?? "http://localhost:8787";

export type Counterpart =
    {
        id: string | null;
        relation: "equivalent" | "merged" | "split" | "partial" | "new" | "omitted";
        changed: boolean;
        note: string;
        similarity: number | null;
        tags: string[];
        in_reverse_table: boolean;
        heading: string | null;
    };

export type Part =
    {
        id: string;
        kind: string;
        label: string;
        text: string;
        status: string;
        added: string;
        changed: string;
        deleted: string;
    };

type Precedent =
    {
        id: string;
        title: string;
        decided_on: string;
        citation: string;
        mentions: number;
        via: string[];
    };

export type Provision =
    {
        id: string;
        act: string;
        number: string;
        heading: string;
        chapter_no: string;
        chapter_title: string;
        subheading: string;
        status: string;
        flag: string;
        notes: string;
        source_url: string | null;
        official: string;
        source_page: number | null;
        act_title: string;
        in_force_from: string;
        in_force_to: string | null;
        parts: Part[];
        classification: { sub: string; offence: string; punishment: string; cognizable: string; bailable: string; triable_by: string }[];
        counterparts: Counterpart[];
        precedent: Precedent[];
        neighbours: { id: string; number: string; heading: string }[];
    };

export async function post<T>(path: string, body: unknown): Promise<T>
{
    const res = await fetch(`${API}${path}`, {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify(body),
    });
    if (!res.ok)
    {
        throw new Error(`${res.status} ${await res.text()}`);
    }
    return res.json() as Promise<T>;
}

// "BNS:103" -> "/bns/103"; "CRPC:438" -> "/crpc/438"
export function href(id: string): string
{
    const [act, num] = id.split(":");
    return `/${act.toLowerCase()}/${num}`;
}

export function label(id: string): string
{
    const [act, num] = id.split(":");
    const name: Record<string, string> = { CRPC: "CrPC", IEA: "Evidence Act" };
    return `${name[act] ?? act} ${num}`;
}

// What to tell the reader when a model-backed call is refused.
export function failure(status: number): string
{
    if (status === 429)
    {
        return "Six questions a minute is the limit. Try again shortly.";
    }
    if (status === 422)
    {
        return "That’s too long or too short to ask. Keep it under a thousand characters.";
    }
    if (status === 503)
    {
        return "Today’s budget for AI answers is used up. Search, judgments and section pages still work; answers return tomorrow.";
    }
    return "The service didn’t answer. Try again in a moment.";
}
