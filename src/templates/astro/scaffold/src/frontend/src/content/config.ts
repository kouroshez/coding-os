import { defineCollection, z } from "astro:content";

// Content collections are the typed content SSOT. The Zod schema is the
// contract — every entry's frontmatter is validated at build time, so a
// page reading collection data never guesses a field name.
const posts = defineCollection({
  type: "content",
  schema: z.object({
    title: z.string(),
    description: z.string(),
    publishedAt: z.coerce.date(),
    draft: z.boolean().default(false),
  }),
});

export const collections = { posts };
