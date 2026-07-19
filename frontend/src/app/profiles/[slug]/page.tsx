"use client";

import { useQuery } from "@tanstack/react-query";
import { useParams } from "next/navigation";

import { ProfileAnalyticsView } from "@/components/profile-analytics-view";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { api } from "@/lib/api";

export default function ProfilePage() {
  const slug = useParams<{ slug: string }>().slug;
  const query = useQuery({
    queryKey: ["profile-analytics", slug],
    queryFn: () => api.profileAnalytics(slug),
  });

  if (query.isPending) {
    return (
      <div className="page-shell space-y-8 py-24">
        <Skeleton className="h-48 w-full" />
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          <Skeleton className="h-28 w-full" />
          <Skeleton className="h-28 w-full" />
          <Skeleton className="h-28 w-full" />
          <Skeleton className="h-28 w-full" />
        </div>
      </div>
    );
  }

  if (query.isError) {
    return (
      <div className="page-shell py-24">
        <p className="eyebrow">Profile analytics unavailable</p>
        <h1 className="mt-5 max-w-2xl font-display text-5xl font-medium tracking-[-0.05em]">
          This profile has no published HVM inspection bundle.
        </h1>
        <p className="mt-6 max-w-2xl text-sm leading-7 text-muted-foreground">
          Detailed analytics are available only for real governed profile releases. The API did
          not return one for “{slug}”.
        </p>
      </div>
    );
  }

  const analytics = query.data;

  return (
    <div className="page-shell py-16 sm:py-24">
      <header className="border-b border-border pb-14">
        <div className="flex flex-wrap items-center gap-3">
          <p className="eyebrow">Voice evidence analytics</p>
          <Badge className="border-primary/30 text-primary">
            HVM v{analytics.release.version}
          </Badge>
          <Badge>{analytics.release.status}</Badge>
          <Badge>{analytics.release.authority} authority</Badge>
        </div>
        <h1 className="mt-5 font-display text-6xl font-medium tracking-[-0.055em] sm:text-8xl">
          {analytics.name}
        </h1>
        <p className="mt-3 text-sm text-muted-foreground">{analytics.role}</p>
        <p className="mt-6 max-w-3xl text-base leading-7 text-muted-foreground">
          {analytics.summary}
        </p>
        <p className="mt-8 max-w-4xl border-l-2 border-primary pl-5 text-sm leading-7">
          This page audits what the system measured from the admitted corpus, how those
          measurements are represented in HVM, and where the evidence is still insufficient. It
          intentionally does not convert descriptive coverage into an invented voice-accuracy
          score.
        </p>
      </header>
      <ProfileAnalyticsView analytics={analytics} />
    </div>
  );
}
