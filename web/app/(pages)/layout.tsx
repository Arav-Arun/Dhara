// Every page except the landing page sits in the same reading container.
export default function PagesLayout({ children }: { children: React.ReactNode })
{
    return <div className="mx-auto w-full max-w-6xl px-5 py-12">{children}</div>;
}
