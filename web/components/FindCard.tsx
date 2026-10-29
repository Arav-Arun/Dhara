"use client";

import { openFinder } from "@/components/CommandPalette";
import { ToolBody, cardClass, type Tool } from "@/components/ToolCard";

const FIND: Tool =
    {
        name: "Any section, old or new",
        cover: "find",
        card: "bg-[#c6e3df]",
        stat: "2,353 sections, 1,310 official links",
        points: ["Type 302, BNS 103 or murder", "Its counterpart in the other code", "Every changed word marked", "The Supreme Court judgments on it"],
        cta: <>Press <kbd className="rounded border border-ink/20 px-1.5 font-[system-ui] text-[12px]">⌘ K</kbd> or click</>,
    };

// Not a page of its own: the card opens the ⌘K finder.
export default function FindCard()
{
    return <button onClick={openFinder} className={cardClass(FIND)}><ToolBody t={FIND} /></button>;
}
