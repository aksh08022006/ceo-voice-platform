import { AlertCircle, Inbox } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";

export function PageSkeleton() {
  return (
    <div className="page-shell py-20" aria-label="Loading content" role="status">
      <Skeleton className="h-3 w-24" />
      <Skeleton className="mt-8 h-14 max-w-2xl" />
      <Skeleton className="mt-5 h-5 max-w-xl" />
      <div className="mt-16 grid gap-8 md:grid-cols-2">
        <Skeleton className="h-80" />
        <Skeleton className="h-80" />
      </div>
      <span className="sr-only">Loading</span>
    </div>
  );
}

export function EmptyState({ title, message }: { title: string; message: string }) {
  return (
    <div className="flex min-h-64 flex-col items-center justify-center border-y border-border px-6 text-center">
      <Inbox aria-hidden="true" className="mb-5 h-5 w-5 text-muted-foreground" />
      <h2 className="font-display text-xl font-medium">{title}</h2>
      <p className="mt-2 max-w-md text-sm leading-6 text-muted-foreground">{message}</p>
    </div>
  );
}

export function ErrorState({ reset }: { reset: () => void }) {
  return (
    <div className="flex min-h-[60vh] flex-col items-center justify-center px-6 text-center">
      <AlertCircle aria-hidden="true" className="mb-5 h-5 w-5 text-muted-foreground" />
      <h1 className="font-display text-3xl font-medium">Something interrupted this view.</h1>
      <p className="mt-3 max-w-lg text-sm leading-6 text-muted-foreground">
        No data was changed. Retry the request or inspect the system report if the issue continues.
      </p>
      <Button className="mt-7" onClick={reset} variant="secondary">
        Try again
      </Button>
    </div>
  );
}
