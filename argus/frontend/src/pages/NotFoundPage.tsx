import { Link } from "react-router";

import { EmptyState } from "@/components/ui/primitives";

export function NotFoundPage() {
  return (
    <EmptyState title="Page not found">
      <Link to="/" className="text-brand-600 hover:underline">Back to the dashboard</Link>
    </EmptyState>
  );
}
