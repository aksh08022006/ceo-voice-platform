import { ArrowDown } from "lucide-react";
import Link from "next/link";

import { Reveal } from "@/components/motion/reveal";
import { buttonStyles } from "@/components/ui/button";

const steps = [
  { title: "Choose a voice", text: "Explore each person’s writing patterns and choose the platform you’re writing for." },
  { title: "Make your point", text: "Describe your idea, supply the facts, and choose the viewpoint and feeling you want to convey." },
  { title: "Shape the draft", text: "Edit the opening, move paragraphs, and add your own details. Re-Voice can refine the wording around your edits." },
  { title: "Give it a final read", text: "Check the meaning, facts, and voice. Copy the draft when you’re satisfied with it." },
];

export default function LandingPage() {
  return (
    <>
      <section className="page-shell flex min-h-[calc(100vh-4rem)] flex-col justify-center py-24">
        <Reveal>
          <p className="eyebrow">CEO Voice · The Narrative Company</p>
          <h1 className="balanced mt-8 max-w-5xl font-display text-[clamp(3.25rem,8vw,7.5rem)] font-medium leading-[0.92] tracking-[-0.065em]">A distinct voice.<br />A clearer point.</h1>
          <p className="mt-10 max-w-xl text-lg leading-8 text-muted-foreground sm:text-xl">Draft posts and replies shaped by each person’s writing. Bring your idea, choose how it should feel, and keep your edits at the center.</p>
          <div className="mt-10 flex flex-wrap gap-3"><Link className={buttonStyles({ size: "lg" })} href="/generate">Start writing</Link><Link className={buttonStyles({ variant: "secondary", size: "lg" })} href="/documentation">Read the guide</Link></div>
        </Reveal>
        <ArrowDown aria-hidden="true" className="mt-20 h-4 w-4 text-muted-foreground" />
      </section>
      <section className="page-shell py-24 sm:py-32" aria-labelledby="workflow-heading">
        <Reveal><p className="eyebrow">How it works</p><h2 id="workflow-heading" className="mt-5 max-w-3xl font-display text-4xl font-medium tracking-[-0.04em] sm:text-6xl">Your idea, with room to refine.</h2></Reveal>
        <ol className="mt-14 grid gap-x-12 sm:grid-cols-2">
          {steps.map((step, index) => <li className="border-t border-border py-8" key={step.title}><span className="font-mono text-xs text-muted-foreground">{String(index + 1).padStart(2, "0")}</span><h3 className="mt-4 font-display text-2xl font-medium tracking-tight">{step.title}</h3><p className="mt-4 max-w-lg text-sm leading-7 text-muted-foreground">{step.text}</p></li>)}
        </ol>
      </section>
    </>
  );
}
