import type { PageLoad } from "./$types";

// Universal load for the landing route — runs on server then client.
// Real data fetching goes here via the injected `fetch`; never bare global fetch.
export const load: PageLoad = async () => {
  return { title: "{{PROJECT_NAME}}" };
};
