import { Suspense } from "react";
import { PrepareWindowRoute } from "@/components/PrepareWindow";

export default function PreparePage() {
  return (
    <Suspense>
      <PrepareWindowRoute />
    </Suspense>
  );
}
