import Link from "next/link";

export function SiteFooter() {
  return (
    <footer className="mt-24 border-t border-border">
      <div className="page-shell flex flex-col gap-4 py-8 text-xs text-muted-foreground sm:flex-row sm:items-center sm:justify-between">
        <p>Evidence-backed executive communication.</p>
        <div className="flex gap-5">
          <Link className="hover:text-foreground" href="/documentation">
            Documentation
          </Link>
          <a
            className="hover:text-foreground"
            href="https://github.com/akshhkaushik/ceo-voice-platform"
            rel="noreferrer"
            target="_blank"
          >
            Source
          </a>
        </div>
      </div>
    </footer>
  );
}
