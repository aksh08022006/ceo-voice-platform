"use client";

import { useQuery } from "@tanstack/react-query";

import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { api } from "@/lib/api";

export function BenchmarkCases() {
  const query = useQuery({ queryKey: ["walkthroughs"], queryFn: api.walkthroughs });
  if (query.isPending) return <Skeleton className="h-56 w-full" />;
  if (query.isError) return <p className="border-y border-border py-12 text-muted-foreground">Benchmark cases are unavailable because the backend could not be reached.</p>;
  return <div className="overflow-x-auto border-y border-border"><table className="w-full min-w-[680px] border-collapse text-left text-sm"><caption className="sr-only">Backend-served regression cases</caption><thead><tr className="border-b border-border font-mono text-[10px] uppercase tracking-wider text-muted-foreground"><th className="px-3 py-4 font-medium">Case</th><th className="px-3 py-4 font-medium">Profile</th><th className="px-3 py-4 font-medium">Platform</th><th className="px-3 py-4 font-medium">State</th></tr></thead><tbody>{query.data.map((item) => <tr className="border-b border-border last:border-0" key={item.slug}><td className="px-3 py-6 font-display text-lg font-medium">{item.title}</td><td className="px-3 py-6 text-muted-foreground">{item.profile_name}</td><td className="px-3 py-6 capitalize">{item.platform}</td><td className="px-3 py-6"><Badge>Ready to run</Badge></td></tr>)}</tbody></table></div>;
}
