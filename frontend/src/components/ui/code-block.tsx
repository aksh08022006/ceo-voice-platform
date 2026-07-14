import { cn } from "@/lib/utils";

export function CodeBlock({ children, className }: { children: string; className?: string }) {
  return (
    <pre
      className={cn(
        "overflow-x-auto rounded-lg border border-border bg-surface p-5 font-mono text-xs leading-6 text-foreground",
        className,
      )}
    >
      <code>{children}</code>
    </pre>
  );
}
