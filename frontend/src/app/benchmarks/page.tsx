import type { Metadata } from "next";
import Link from "next/link";

import { buttonStyles } from "@/components/ui/button";

export const metadata: Metadata = { title: "Examples" };

const examples = [
  { title: "An open-source perspective", format: "LinkedIn post", idea: "Explain why an open approach matters to your company. Name the decision or event behind the post, and connect it to the point you want to make.", note: "Try Open infrastructure in the generator for a sample brief with Ali’s voice." },
  { title: "A technical observation", format: "X thread", idea: "Describe a change you see in how teams build AI systems. Develop one technical point across a short thread, keeping predictions separate from measured results.", note: "Try Compound AI in the generator for a sample brief with Matei’s voice." },
  { title: "Credit to the team", format: "LinkedIn post", idea: "Share a milestone and explain what the team contributed. Supply the names and details you want included, then choose a grateful register.", note: "Keep the credit specific. Include only details you can confirm." },
  { title: "A question worth asking", format: "X reply", idea: "Respond to a claim with a focused question. Paste the original post, describe what you want clarified, and choose Ask a question as the reply intent.", note: "Use a curious register and explain why the answer matters." },
];

export default function ExamplesPage() {
  return (
    <div className="page-shell py-16 sm:py-24">
      <header className="mb-14 max-w-4xl">
        <p className="eyebrow">Examples</p>
        <h1 className="balanced mt-5 font-display text-5xl font-medium tracking-[-0.05em] sm:text-7xl">A few ways to begin.</h1>
        <p className="mt-6 max-w-2xl text-lg leading-8 text-muted-foreground">Use these starting points to shape your own brief. Add the facts, viewpoint, and details that belong in your draft.</p>
      </header>
      <div className="grid gap-x-12 sm:grid-cols-2">
        {examples.map((example) => <section className="border-t border-border py-8" key={example.title}><p className="eyebrow">{example.format}</p><h2 className="mt-4 font-display text-2xl font-medium tracking-tight">{example.title}</h2><p className="mt-4 text-sm leading-7 text-muted-foreground">{example.idea}</p><p className="mt-4 text-sm leading-7">{example.note}</p></section>)}
      </div>
      <div className="mt-10 flex flex-wrap gap-3"><Link className={buttonStyles({ size: "lg" })} href="/generate">Start writing</Link><Link className={buttonStyles({ variant: "secondary", size: "lg" })} href="/documentation">Read the guide</Link></div>
    </div>
  );
}
