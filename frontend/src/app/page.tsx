import { ArrowDown } from "lucide-react";
import Image from "next/image";
import Link from "next/link";

import { Reveal } from "@/components/motion/reveal";
import { buttonStyles } from "@/components/ui/button";

const stages = [
  "Ingestion",
  "Voice Analysis",
  "HVM Voice Profile",
  "Profile Builder",
  "Context Compiler",
  "Retrieval",
  "Generation",
  "Re-Voice",
  "Evaluation",
];

export default function LandingPage() {
  return (
    <>
      <section className="page-shell flex min-h-[calc(100vh-4rem)] flex-col justify-center py-24">
        <Reveal>
          <p className="eyebrow">CEO Voice Platform</p>
          <h1 className="balanced mt-8 max-w-5xl font-display text-[clamp(3.25rem,8vw,7.5rem)] font-medium leading-[0.92] tracking-[-0.065em]">
            Generate authentic executive communication.
          </h1>
          <p className="mt-10 max-w-xl text-lg leading-8 text-muted-foreground sm:text-xl">
            Evidence-backed.
            <br />
            Explainable.
            <br />
            Governed.
          </p>
          <div className="mt-10 flex flex-wrap gap-3">
            <Link className={buttonStyles({ size: "lg" })} href="/generate">
              Generate
            </Link>
            <Link className={buttonStyles({ variant: "secondary", size: "lg" })} href="/documentation">
              Documentation
            </Link>
            <a
              className={buttonStyles({ variant: "ghost", size: "lg" })}
              href="https://github.com/aksh08022006/ceo-voice-platform"
              rel="noreferrer"
              target="_blank"
            >
              GitHub
            </a>
          </div>
        </Reveal>
        <ArrowDown aria-hidden="true" className="mt-20 h-4 w-4 text-muted-foreground" />
      </section>

      <section className="page-shell py-28 sm:py-40" aria-labelledby="architecture-heading">
        <Reveal>
          <p className="eyebrow">Architecture</p>
          <h2 id="architecture-heading" className="mt-5 font-display text-4xl font-medium tracking-[-0.04em] sm:text-6xl">
            From evidence to accountable output.
          </h2>
        </Reveal>
        <Image alt="Ingestion, analysis, HVM, profile builder, context compiler, retrieval, generation, Re-Voice, and evaluation architecture" className="mt-16 hidden w-full border-y border-border dark:invert sm:block" height={320} priority={false} src="/architecture.svg" width={1440} />
        <ol className="mt-20 border-t border-border sm:hidden">
          {stages.map((stage, index) => (
            <li key={stage} className="border-b border-border">
              <Reveal delay={Math.min(index * 0.025, 0.12)}>
                <div className="grid min-h-28 grid-cols-[3rem_1fr] items-center gap-4 sm:min-h-32 sm:grid-cols-[6rem_1fr_auto]">
                  <span className="font-mono text-xs text-muted-foreground">0{index + 1}</span>
                  <span className="font-display text-2xl font-medium tracking-tight sm:text-4xl">{stage}</span>
                  {index < stages.length - 1 ? (
                    <ArrowDown aria-hidden="true" className="hidden h-4 w-4 text-muted-foreground sm:block" />
                  ) : null}
                </div>
              </Reveal>
            </li>
          ))}
        </ol>
      </section>
    </>
  );
}
