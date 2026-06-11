import express from "express";

import { healthRouter } from "./routes/health.js";
import { errorHandler } from "./middleware/error-handler.js";

export function createApp() {
  const app = express();
  app.use(express.json());
  app.use("/health", healthRouter);
  app.use(errorHandler); // MUST stay last — Express dispatches in registration order
  return app;
}

const port = Number(process.env.PORT ?? 3000);
createApp().listen(port, () => {
  console.log(`{{PROJECT_NAME}} backend listening on :${port}`);
});
