export type FrameMark = {
  state: "unmarked" | "located" | "not_visible" | "uncertain";
  source?: "manual" | "estimated" | null;
};

export function summarize(marks: FrameMark[]) {
  const counts = { unmarked: 0, manual: 0, estimated: 0, notVisible: 0, uncertain: 0 };
  for (const mark of marks) {
    if (mark.state === "not_visible") counts.notVisible += 1;
    else if (mark.state === "uncertain") counts.uncertain += 1;
    else if (mark.state === "located" && mark.source === "estimated") counts.estimated += 1;
    else if (mark.state === "located") counts.manual += 1;
    else counts.unmarked += 1;
  }
  return counts;
}

export function summaryLine(marks: FrameMark[]) {
  const counts = summarize(marks);
  return `${counts.manual} manual, ${counts.estimated} estimated, ${counts.uncertain} uncertain, ${counts.notVisible} not visible, ${counts.unmarked} not annotated`;
}

/** Uncertain frames first, then an unannotated frame between the first and last location. */
export function nextAttention(frameIds: string[], marks: Record<string, FrameMark>): string | null {
  const uncertain = frameIds.find((id) => marks[id]?.state === "uncertain");
  if (uncertain) return uncertain;
  const located = frameIds.filter((id) => marks[id]?.state === "located");
  if (located.length < 2) return null;
  const first = frameIds.indexOf(located[0]);
  const last = frameIds.indexOf(located[located.length - 1]);
  for (let index = first + 1; index < last; index += 1) {
    const state = marks[frameIds[index]]?.state ?? "unmarked";
    if (state === "unmarked") return frameIds[index];
  }
  return null;
}
