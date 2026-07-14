import type { ReactNode } from "react";

import { AccordionItem } from "@/components/ui/accordion";

export function ReportSection({ title, children }: { title: string; children: ReactNode }) {
  return <AccordionItem title={title}>{children}</AccordionItem>;
}
