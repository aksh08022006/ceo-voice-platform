"use client";

import { Menu, X } from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useState } from "react";

import { ThemeToggle } from "@/components/theme-toggle";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

const navigation = [
  { label: "Generate", href: "/generate" },
  { label: "Profiles", href: "/profiles" },
  { label: "Benchmarks", href: "/benchmarks" },
  { label: "Documentation", href: "/documentation" },
];

export function SiteHeader() {
  const pathname = usePathname();
  const [open, setOpen] = useState(false);

  return (
    <header className="sticky top-0 z-50 border-b border-border bg-background">
      <div className="page-shell flex h-16 items-center justify-between">
        <Link className="font-display text-sm font-semibold tracking-tight" href="/">
          CEO Voice
        </Link>
        <nav aria-label="Primary navigation" className="hidden items-center gap-1 lg:flex">
          {navigation.map((item) => (
            <Link
              key={item.href}
              href={item.href}
              className={cn(
                "rounded-md px-3 py-2 text-sm transition-colors duration-200",
                pathname.startsWith(item.href)
                  ? "text-foreground"
                  : "text-muted-foreground hover:text-foreground",
              )}
            >
              {item.label}
            </Link>
          ))}
          <a
            className="rounded-md px-3 py-2 text-sm text-muted-foreground transition-colors hover:text-foreground"
            href="https://github.com/aksh08022006/ceo-voice-platform"
            rel="noreferrer"
            target="_blank"
          >
            GitHub
          </a>
        </nav>
        <div className="flex items-center gap-1">
          <ThemeToggle />
          <Button
            aria-expanded={open}
            aria-label={open ? "Close navigation" : "Open navigation"}
            className="lg:hidden"
            onClick={() => setOpen((current) => !current)}
            size="icon"
            variant="ghost"
          >
            {open ? <X aria-hidden="true" className="h-4 w-4" /> : <Menu aria-hidden="true" className="h-4 w-4" />}
          </Button>
        </div>
      </div>
      {open ? (
        <nav aria-label="Mobile navigation" className="page-shell border-t border-border py-4 lg:hidden">
          {navigation.map((item) => (
            <Link
              key={item.href}
              className="block py-3 text-sm text-muted-foreground hover:text-foreground"
              href={item.href}
              onClick={() => setOpen(false)}
            >
              {item.label}
            </Link>
          ))}
          <a
            className="block py-3 text-sm text-muted-foreground hover:text-foreground"
            href="https://github.com/aksh08022006/ceo-voice-platform"
            rel="noreferrer"
            target="_blank"
          >
            GitHub
          </a>
        </nav>
      ) : null}
    </header>
  );
}
