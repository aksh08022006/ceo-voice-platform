import type { Metadata } from "next";
import Link from "next/link";

export const metadata: Metadata = {
  title: "Writing guide",
  description: "Write, shape, and refine posts and replies with CEO Voice.",
};

const sections = [
  { id: "brief", label: "Start with a clear brief" },
  { id: "expression", label: "Shape the expression" },
  { id: "format", label: "Choose the format" },
  { id: "edit", label: "Edit and Re-Voice" },
  { id: "review", label: "Review before publishing" },
];

export default function DocumentationPage() {
  return (
    <div className="page-shell py-16 sm:py-24">
      <header className="mb-16 max-w-4xl border-b border-border pb-14">
        <p className="eyebrow">Writing guide</p>
        <h1 className="balanced mt-5 font-display text-5xl font-medium tracking-[-0.05em] sm:text-7xl">
          From a clear idea to a considered draft.
        </h1>
        <p className="mt-7 max-w-2xl text-lg leading-8 text-muted-foreground">
          Choose a voice, describe your point, and shape how it lands. Your edits guide the final wording.
        </p>
      </header>
      <div className="grid gap-14 lg:grid-cols-[12rem_minmax(0,52rem)] lg:gap-20">
        <nav aria-label="Guide sections" className="lg:sticky lg:top-24 lg:self-start">
          <ul className="space-y-3 text-sm text-muted-foreground">
            {sections.map((section) => <li key={section.id}><a className="transition-colors hover:text-foreground" href={`#${section.id}`}>{section.label}</a></li>)}
          </ul>
        </nav>
        <article className="space-y-16">
          <GuideSection id="brief" number="01" title="Give the draft something specific to say.">
            <p>Choose a person and platform, then describe the event, observation, or argument you want to communicate. Include the facts that matter and explain your angle. If a detail is uncertain, say so.</p>
            <div className="mt-6 rounded-lg border border-border p-5">
              <p className="text-xs font-medium uppercase tracking-wider text-foreground">Sample brief</p>
              <p className="mt-3">Our team is releasing a new developer tool next week. Explain why we chose an open-source approach. Keep the tone thoughtful, and avoid performance claims because we have not shared measurements.</p>
            </div>
            <p className="mt-5">For a personal story, supply the real detail you want included. A writing profile can guide expression; it cannot establish a new memory or company fact.</p>
          </GuideSection>
          <GuideSection id="expression" number="02" title="Choose the feeling and the point of view.">
            <p>Open Emotion, emoji &amp; viewpoint to guide the draft. Leave a control on its default to use the selected person’s observed writing habits.</p>
            <dl className="mt-6 divide-y divide-border border-y border-border">
              <Definition term="Emotional register">Choose a direction such as thoughtful reflection, gratitude, curiosity, enthusiasm, or concern.</Definition>
              <Definition term="Intensity and warmth">Adjust how strongly the emotion is expressed and how reserved or warm the wording feels.</Definition>
              <Definition term="Emoji">Follow the person’s observed use, omit emoji, or allow at most one when appropriate.</Definition>
              <Definition term="Viewpoint">State the position you want this draft to express.</Definition>
              <Definition term="Why this matters">Explain the reasoning behind that position. Use the facts you have supplied.</Definition>
            </dl>
            <p className="mt-5">Review that a change in tone has not strengthened a tentative claim or introduced a new one. Historical writing examples are context for style, not proof of a person’s current beliefs.</p>
          </GuideSection>
          <GuideSection id="format" number="03" title="Write for the conversation you’re in.">
            <p>Use LinkedIn for a longer post, or X for a single post or thread. LinkedIn defaults to 150–300 words; you can let the profile guide length instead. Each X post stays within 280 characters.</p>
            <p className="mt-5">For a comment, choose Comment / reply and paste the parent post. Pick your intent: add perspective, ask a question, disagree respectfully, acknowledge, or answer. Describe the specific contribution you want to make.</p>
            <p className="mt-5">Structural influence starts at a subtle 12%. Increase or reduce it to adjust how much the selected structure patterns shape the draft.</p>
          </GuideSection>
          <GuideSection id="edit" number="04" title="Make it yours, then refine the voice.">
            <p>Choose Edit and Re-Voice after generating. Replace the opening, correct facts, move paragraphs, and add the details you want to keep directly in Human edit.</p>
            <p className="mt-5">Use the optional note for wording guidance, such as “Keep my opening and paragraph order. Make the language more direct.” Re-Voice checks your structure and recognized details, including emoji. It may keep your text unchanged when no suitable refinement is made.</p>
            <p className="mt-5">You can edit the returned version again. Drafts can resume in the same browser tab for up to seven days after the latest successful step. Copy your text before closing the tab.</p>
          </GuideSection>
          <GuideSection id="review" number="05" title="Give the final draft a human read.">
            <p>Read it aloud. Check whether the opening, rhythm, viewpoint, and closing feel right for the person and audience. Confirm facts, attribution, dates, and personal details before publishing.</p>
            <p className="mt-5">The source panels show writing examples that informed the draft. The review page checks observable features such as length, formatting, and recognized details. These checks do not establish factual accuracy or approval by the person whose profile you selected.</p>
            <p className="mt-5">Profiles are based on available public writing and may have gaps in source coverage. You can inspect those details on the profile page. Comments currently draw style evidence from original posts.</p>
            <Link className="mt-7 inline-block font-medium text-primary underline underline-offset-4" href="/generate">Start a draft</Link>
          </GuideSection>
        </article>
      </div>
    </div>
  );
}

function GuideSection({ id, number, title, children }: { id: string; number: string; title: string; children: React.ReactNode }) {
  return <section className="scroll-mt-24" id={id}><p className="eyebrow">{number}</p><h2 className="mt-4 font-display text-3xl font-medium tracking-[-0.035em] sm:text-4xl">{title}</h2><div className="mt-5 text-base leading-8 text-muted-foreground">{children}</div></section>;
}

function Definition({ term, children }: { term: string; children: React.ReactNode }) {
  return <div className="grid gap-2 py-5 sm:grid-cols-[10rem_1fr]"><dt className="font-medium text-foreground">{term}</dt><dd>{children}</dd></div>;
}
