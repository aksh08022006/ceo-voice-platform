export const profiles = [
  {
    slug: "ali-ghodsi",
    name: "Ali Ghodsi",
    status: "Published",
    coverage: 96,
    version: "v4.2",
    summary: "Direct, systems-oriented writing with short declarative openings and evidence-led explanation.",
  },
  {
    slug: "matei-zaharia",
    name: "Matei Zaharia",
    status: "Published",
    coverage: 93,
    version: "v3.8",
    summary: "Technical clarity, measured claims, and structured movement from problem to mechanism.",
  },
  {
    slug: "jensen-huang",
    name: "Jensen Huang",
    status: "Review required",
    coverage: 81,
    version: "v1.7",
    summary: "Mission-led narrative with high-conviction statements and broad organizational framing.",
  },
] as const;

export const generatedDraft = `The fastest teams are not the ones making the most decisions.

They are the ones who know who owns each decision.

Clear ownership removes coordination loops. It gives people the context and authority to move without waiting for another meeting.

That compounds: faster learning, sharper accountability, and more time spent building.

When execution slows down, ask one question first: who owns the next decision?`;

export const voiceEvidence = [
  { label: "Declarative opening", confidence: "0.96", source: "HVM · rhetorical.opening.v2" },
  { label: "Short paragraph cadence", confidence: "0.94", source: "HVM · formatting.paragraph.v3" },
  { label: "Mechanism before claim", confidence: "0.91", source: "HVM · narrative.reasoning.v2" },
];

export const structureEvidence = [
  { label: "Contrast-led hook", confidence: "0.89", source: "VKR · hook.contrast.v1" },
  { label: "Problem → mechanism → action", confidence: "0.92", source: "VKR · arc.explanatory.v2" },
];

export const benchmarkRows = [
  { leader: "Ali Ghodsi", platform: "LinkedIn", score: 91, status: "Warning", suite: "core-v1" },
  { leader: "Matei Zaharia", platform: "X", score: 91, status: "Warning", suite: "core-v1" },
  { leader: "Jensen Huang", platform: "LinkedIn", score: 91, status: "Warning", suite: "core-v1" },
] as const;
