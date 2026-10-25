import { Suspense } from "react";
import { ScoutStart } from "@/components/ScoutStart";

export default function ScoutPage() {
  return (
    <Suspense fallback={<main className="app">Loading the scouting start.</main>}>
      <ScoutStart />
    </Suspense>
  );
}
