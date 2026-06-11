// Pre-install ambient stub so `npm run lint` (tsc --noEmit) passes on a fresh
// scaffold BEFORE `npm install` pulls @types/express. Real typings shadow this
// file automatically once node_modules exists — do not extend it.
declare module "express" {
  export interface Request { params: Record<string, string>; body: unknown }
  export interface Response { status(code: number): Response; json(body: unknown): Response }
  export type NextFunction = (err?: unknown) => void
  export type RequestHandler = (req: Request, res: Response, next: NextFunction) => unknown
  export interface Router {
    get(path: string, ...handlers: RequestHandler[]): Router
    use(...handlers: unknown[]): Router
  }
  export interface Application extends Router { listen(port: number, cb?: () => void): unknown }
  interface ExpressFactory { (): Application; Router(): Router; json(): RequestHandler }
  const express: ExpressFactory
  export default express
}

// Node globals used by the bootstrap, pre-install (real @types/node shadows this).
declare const process: { env: Record<string, string | undefined> };
declare const console: { log(...args: unknown[]): void; error(...args: unknown[]): void };
