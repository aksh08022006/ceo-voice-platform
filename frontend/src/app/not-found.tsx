import Link from "next/link";

import { buttonStyles } from "@/components/ui/button";

export default function NotFound() {
  return (
    <div className="page-shell flex min-h-[65vh] flex-col items-start justify-center">
      <p className="eyebrow">404</p>
      <h1 className="mt-5 font-display text-5xl font-medium tracking-[-0.04em]">Page not found.</h1>
      <p className="mt-4 max-w-md text-sm leading-6 text-muted-foreground">
        The requested workspace does not exist or is no longer published.
      </p>
      <Link className={buttonStyles({ variant: "secondary", size: "md", className: "mt-8" })} href="/">
        Return home
      </Link>
    </div>
  );
}
