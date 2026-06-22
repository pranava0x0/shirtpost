import { z } from "zod";

// Strict runtime schema for client env (mirrors the Pydantic guardrail on the
// backend). Fails loud at module load if misconfigured.
const schema = z.object({
  NEXT_PUBLIC_API_BASE_URL: z.string().url(),
});

const parsed = schema.safeParse({
  NEXT_PUBLIC_API_BASE_URL: process.env.NEXT_PUBLIC_API_BASE_URL,
});

if (!parsed.success) {
  throw new Error(
    "Invalid environment configuration:\n" +
      JSON.stringify(parsed.error.flatten().fieldErrors, null, 2),
  );
}

export const env = parsed.data;
