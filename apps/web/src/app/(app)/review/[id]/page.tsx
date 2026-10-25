import { Suspense } from "react";
import { CoachReviewRoute } from "@/components/CoachReview";

export default function ReviewPage() {
  return (
    <Suspense>
      <CoachReviewRoute />
    </Suspense>
  );
}
