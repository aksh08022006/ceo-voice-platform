# CEO Voice frontend

Editorial product interface for the CEO Voice Platform. It uses Next.js 15 App Router, TypeScript,
Tailwind CSS, owned shadcn-style primitives, Framer Motion, React Hook Form, Zod, TanStack Query,
Lucide, and Sonner.

## Local development

```bash
npm ci
npm run dev
```

Open `http://localhost:3000`. The current data adapter is an explicitly synthetic in-browser
fixture because the backend release does not expose an HTTP API. Replace functions in
`src/lib/demo-data.ts` and mutation adapters with a typed API client when that transport exists;
page and component contracts do not depend on Python internals.

## Quality gate

```bash
npm run lint
npm run typecheck
npm run build
```

## Routes

- `/` — product explanation and architecture timeline
- `/generate` — governed generation workspace
- `/revoice` — protected human-edit restoration
- `/evaluation` — multidimensional quality report
- `/profiles` and `/profiles/[slug]` — published voice-profile inspection
- `/benchmarks` — synthetic regression suite disclosure
- `/documentation` — product and governance concepts

Light mode is the editorial default; dark mode uses the same neutral tokens. Motion stays below
300ms and respects `prefers-reduced-motion`.
