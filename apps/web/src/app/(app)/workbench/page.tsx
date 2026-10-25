import { Suspense } from "react";
import { ReviewApp } from "@/components/ReviewApp";

export default function Page() {
  return (
    <Suspense fallback={<main className="app">Loading the review workspace.</main>}>
      <ReviewApp />
    </Suspense>
  );
}
