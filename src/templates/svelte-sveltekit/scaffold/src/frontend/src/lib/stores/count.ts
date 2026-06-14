import { writable } from "svelte/store";

// Cross-component counter store for {{PROJECT_NAME}} — one store per file.
export const count = writable(0);
