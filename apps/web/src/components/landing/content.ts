export type Credit = { use: string; title: string; creator: string; licence: string; licenceUrl: string; page: string; change: string };

export const CREDITS: Record<"stadium" | "five" | "fifteen" | "nine" | "follow" | "pitch", Credit> = {
  stadium: {
    use: "Hero stadium",
    title: "Mecz piłkarski Wisła Kraków - Zagłębie Sosnowiec, 28 października 2022",
    creator: "Krzysztof Popławski",
    licence: "CC BY 4.0",
    licenceUrl: "https://creativecommons.org/licenses/by/4.0",
    page: "https://commons.wikimedia.org/wiki/File:Mecz_pi%C5%82karski_Wis%C5%82a_Krak%C3%B3w_-_Zag%C5%82%C4%99bie_Sosnwoiec,_28_pa%C5%BAdziernika_2022,_Po%C5%BCegnanie_Stadionu_Ludowego,_KP.jpg",
    change: "Resized, greyscale.",
  },
  five: {
    use: "Phone, Blue 5",
    title: "Americans lose 3-1 to Germans in 15th Annual Sportsfest soccer match (8531011)",
    creator: "Staff Sgt. Max Daigle, U.S. Air Force",
    licence: "Public domain",
    licenceUrl: "https://creativecommons.org/publicdomain/mark/1.0/",
    page: "https://commons.wikimedia.org/wiki/File:Americans_lose_3-1_to_Germans_in_15th_Annual_Sportsfest_soccer_match_(8531011).jpg",
    change: "Cropped.",
  },
  fifteen: {
    use: "Phone, Blue 15",
    title: "Bulgaria hosts exhibition soccer match for U S Soldiers (7200668)",
    creator: "Spc. Dean Johnson, U.S. Army",
    licence: "Public domain",
    licenceUrl: "https://creativecommons.org/publicdomain/mark/1.0/",
    page: "https://commons.wikimedia.org/wiki/File:Bulgaria_hosts_exhibition_soccer_match_for_U_S_Soldiers_(7200668).jpg",
    change: "Cropped.",
  },
  nine: {
    use: "Phone, Green 9",
    title: "Heading the ball",
    creator: "Newfoundlandguy",
    licence: "CC BY-SA 4.0",
    licenceUrl: "https://creativecommons.org/licenses/by-sa/4.0",
    page: "https://commons.wikimedia.org/wiki/File:Heading_the_ball.jpg",
    change: "Cropped; same licence.",
  },
  follow: {
    use: "Follow one player",
    title: "Americans lose 3-1 to Germans in 15th Annual Sportsfest soccer match (8531012)",
    creator: "Staff Sgt. Max Daigle, U.S. Air Force",
    licence: "Public domain",
    licenceUrl: "https://creativecommons.org/publicdomain/mark/1.0/",
    page: "https://commons.wikimedia.org/wiki/File:Americans_lose_3-1_to_Germans_in_15th_Annual_Sportsfest_soccer_match_(8531012).jpg",
    change: "Resized.",
  },
  pitch: {
    use: "Closing pitch",
    title: "Glossop North End v Charnock Richard - 25 October 2025 03",
    creator: "Dominic Nelson",
    licence: "CC BY-SA 4.0",
    licenceUrl: "https://creativecommons.org/licenses/by-sa/4.0",
    page: "https://commons.wikimedia.org/wiki/File:Glossop_North_End_v_Charnock_Richard_-_25_October_2025_03.jpg",
    change: "Resized, greyscale; same licence.",
  },
};

export type Spot = { x: number; y: number; rx: number };

export type PhoneShot = {
  src: string;
  alt: string;
  label: string;
  player: Spot;
  head: { x: number; y: number };
  ball: { x: number; y: number; r: number };
  others: Spot[];
  drift: number;
};

export const SHOTS: PhoneShot[] = [
  {
    src: "/landing/phone-5.jpg",
    alt: "A player in a blue shirt, number 5, runs with the ball at his feet while a player in white closes in.",
    label: "Blue 5",
    player: { x: 450, y: 902, rx: 78 },
    head: { x: 318, y: 60 },
    ball: { x: 79, y: 865, r: 74 },
    others: [],
    drift: -1,
  },
  {
    src: "/landing/phone-15.jpg",
    alt: "A player in blue and yellow, number 15, steps toward the ball in an amateur match.",
    label: "Blue 15",
    player: { x: 246, y: 780, rx: 64 },
    head: { x: 340, y: 250 },
    ball: { x: 323, y: 718, r: 44 },
    others: [{ x: 156, y: 680, rx: 30 }, { x: 488, y: 930, rx: 52 }],
    drift: -1,
  },
  {
    src: "/landing/phone-9.jpg",
    alt: "A player in green and gold jumps to head a high ball on a pitch lined with autumn trees.",
    label: "Green 9",
    player: { x: 282, y: 922, rx: 58 },
    head: { x: 312, y: 300 },
    ball: { x: 311, y: 74, r: 38 },
    others: [],
    drift: 1,
  },
];

export const FOLLOW = {
  src: "/landing/follow.jpg",
  alt: "A player in blue runs with the ball between three players in white on a grass pitch.",
  label: "Carry",
  player: { x: 577, y: 724, rx: 62 },
  head: { x: 735, y: 96 },
  chipAt: { x: 800, y: 150 },
  ball: { x: 888, y: 710, r: 52 },
  others: [
    { x: 255, y: 890, rx: 60 },
    { x: 470, y: 716, rx: 44 },
    { x: 1170, y: 752, rx: 60 },
  ],
};

export const SAMPLE = {
  player: "Wide player",
  clip: "Clip 1",
  durationMs: 30000,
  trackedMs: 29500,
  confidence: { score: 37, band: "Low" },
  parts: [
    { label: "Footage", points: 0, max: 25 },
    { label: "Actions seen", points: 8.8, max: 25 },
    { label: "Clips with actions", points: 6.7, max: 20 },
    { label: "Clear outcomes", points: 15, max: 15 },
    { label: "Coach accepted", points: 6.4, max: 15 },
  ],
  moments: [
    { id: "m1", action: "receive", startMs: 10080, status: "accepted", outcome: "controlled", outcomeDetail: "controlled", text: "Receives the ball" },
    { id: "m2", action: "pass", startMs: 12480, status: "accepted", outcome: "completed", outcomeDetail: "completed", text: "Plays the ball to a teammate" },
    { id: "m3", action: "receive", startMs: 16880, status: "accepted", outcome: "controlled", outcomeDetail: "controlled", text: "Receives the ball" },
    { id: "m4", action: "loss", startMs: 18800, status: "suggestion", outcome: "lost", outcomeDetail: "lost", text: "Loses the ball to an opponent" },
    { id: "m5", action: "receive", startMs: 24560, status: "suggestion", outcome: "controlled", outcomeDetail: "controlled", text: "Receives the ball" },
    { id: "m6", action: "carry", startMs: 24560, status: "suggestion", outcome: "retained", outcomeDetail: "retained", text: "Carries the ball" },
    { id: "m7", action: "pass", startMs: 27520, status: "suggestion", outcome: "completed", outcomeDetail: "completed", text: "Plays the ball to a teammate" },
  ],
};
