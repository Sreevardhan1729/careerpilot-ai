import Link from "next/link";

export default function NotFound() {
  return (
    <main className="mx-auto max-w-md p-10 text-center">
      <h1 className="text-2xl font-semibold">Page not found</h1>
      <p className="mt-2 text-muted-foreground">That page doesn&apos;t exist.</p>
      <Link href="/dashboard" className="mt-4 inline-block text-primary underline">
        Go to the dashboard
      </Link>
    </main>
  );
}
