import type { ReactNode } from "react";

export const metadata = {
  title: "frontend",
  description: "Scaffolded by coding-os",
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
