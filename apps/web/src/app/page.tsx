import type { Metadata } from "next";
import { Landing } from "@/components/landing/Landing";
import "./landing.css";

export const metadata: Metadata = {
  title: "SecondLook: a second look at every touch",
  description: "Upload a match clip, click your player once, and a coach accepts or rejects every moment SecondLook marks.",
};

export default function Home() {
  return <Landing />;
}
