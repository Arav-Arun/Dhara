"use client";

import { diffWords } from "diff";

// Word-level diff, old to new: removed words struck through in red, added words underlined in blue.
export default function DiffView({ before, after }: { before: string; after: string })
{
    return (
        <p className="font-serif text-[16px] leading-[1.75] whitespace-pre-wrap">
            {diffWords(before, after).map((p, i) =>
            {
                if (p.added)
                {
                    return <ins key={i} className="bg-stamp-wash text-stamp decoration-stamp/40 underline-offset-4">{p.value}</ins>;
                }
                if (p.removed)
                {
                    return <del key={i} className="text-redtape decoration-redtape/60">{p.value}</del>;
                }
                return <span key={i}>{p.value}</span>;
            })}
        </p>
    );
}
