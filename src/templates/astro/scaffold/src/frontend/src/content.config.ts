import { defineCollection } from "astro:content";
import { glob } from "astro/loaders";
import { z } from "astro/zod";

// Content collections are the typed content SSOT. The Content Layer glob()
// loader reads entries from disk; the Zod schema is the contract — every
// entry's frontmatter is validated at build time, so a page reading
// collection data never guesses a field name.
const posts = defineCollection({
  loader: glob({ base: "./src/content/posts", pattern: "**/*.md" }),
  schema: z.object({
    title: z.string(),
    description: z.string(),
    publishedAt: z.coerce.date(),
    draft: z.boolean().default(false),
  }),
});

export const collections = { posts };
