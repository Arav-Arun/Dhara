// The page itself is a client component, so its title is set here. The template is repeated
// because a layout's own title would otherwise replace the root one for the judgment pages below.
export const metadata = { title: { default: "Judgments", template: "%s · Dhara" } };

export default function Layout({ children }: { children: React.ReactNode })
{
    return children;
}
