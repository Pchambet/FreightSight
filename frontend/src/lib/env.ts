import "server-only";
import { z } from "zod";

// Server-only configuration. The browser never talks to the API directly in Phase 0:
// every mutation goes through a Server Action, every read through a Server Component.
const schema = z.object({
  API_URL: z.string().url(),
  // Temporary tenant selector until real auth lands (Phase 1). Sent as X-Org-Id.
  ORG_ID: z.string().uuid(),
  NEXT_PUBLIC_APP_ENV: z.enum(["local", "preview", "prod"]).default("local"),
});

const parsed = schema.safeParse({
  API_URL: process.env.API_URL,
  ORG_ID: process.env.ORG_ID,
  NEXT_PUBLIC_APP_ENV: process.env.NEXT_PUBLIC_APP_ENV,
});

if (!parsed.success) {
  const issues = parsed.error.issues.map((i) => `${i.path.join(".")}: ${i.message}`).join("; ");
  throw new Error(`Invalid environment. Copy .env.example to frontend/.env.local. ${issues}`);
}

export const env = parsed.data;
