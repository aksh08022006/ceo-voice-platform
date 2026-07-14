"use client";

import { useQuery } from "@tanstack/react-query";
import { ArrowRight } from "lucide-react";
import Link from "next/link";

import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { api } from "@/lib/api";

export function ProfilesList() {
  const query = useQuery({ queryKey: ["profiles"], queryFn: api.profiles });
  if (query.isPending) return <div className="space-y-4"><Skeleton className="h-28 w-full" /><Skeleton className="h-28 w-full" /></div>;
  if (query.isError) return <p className="border-y border-border py-12 text-muted-foreground">Profiles are unavailable because the backend could not be reached.</p>;
  return <div className="border-t border-border">{query.data.map((profile) => <Link className="group grid gap-6 border-b border-border py-8 transition-colors hover:bg-muted/30 sm:grid-cols-[1fr_9rem_1.5rem] sm:items-center sm:px-3" href={`/profiles/${profile.slug}`} key={profile.slug}><div><h2 className="font-display text-2xl font-medium tracking-tight">{profile.name}</h2><p className="mt-2 max-w-xl text-sm leading-6 text-muted-foreground">{profile.summary}</p></div><Badge className="border-primary/30 text-primary">{profile.status}</Badge><ArrowRight className="h-4 w-4 text-muted-foreground transition-transform group-hover:translate-x-1" /></Link>)}</div>;
}
