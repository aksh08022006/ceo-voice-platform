# CEO Voice frontend

Editorial product interface for the CEO Voice Platform. It uses Next.js 15 App Router, TypeScript,
Tailwind CSS, owned shadcn-style primitives, Framer Motion, React Hook Form, Zod, TanStack Query,
Lucide, and Sonner.

## Local development

```bash
npm ci
npm run dev
```

Start the backend from the repository root with `make api`, then open `http://localhost:3000`.
The typed client in `src/lib/api.ts` calls the FastAPI `/api/v1` endpoints for profiles, generation,
Re-Voice, and evaluation. It defaults to `http://127.0.0.1:8000`; set
`NEXT_PUBLIC_API_BASE_URL` when building for another API origin.

The backend selects showcase fixtures, development profiles, or reviewed published bundles.
Provider and retrieval settings stay on the backend; no API key belongs in a frontend environment
variable. The Generate form accepts only profile, platform, and idea. Workflow sessions currently
live in API process memory, so restarting the API loses those sessions. See the root
[quickstart](../README.md#quickstart) and [operations guide](../docs/OPERATIONS.md).

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
