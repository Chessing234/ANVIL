import type { LessonDefinition, LessonSummary } from "@/types/education";

const baseSummaries: LessonSummary[] = [
  {
    id: "lesson-dns-tunnel",
    title: "DNS Tunnel Detective",
    subtitle: "Follow exfiltration through recursive resolvers.",
    difficulty: "Intermediate",
    categories: ["Network", "Forensics"],
    concepts: ["DNS", "entropy", "beaconing"],
    durationMinutes: 35,
    rating: 4.8,
    enrollCount: 18200,
    thumbnailGradient: "from-indigo-600 via-violet-600 to-fuchsia-600",
    cstaCodes: ["2-IC-20", "3A-NI-04"],
    createdAt: "2026-05-12T10:00:00Z",
    trending: true,
    recommended: true,
    progressPercent: 42,
  },
  {
    id: "lesson-ransomware-forensics",
    title: "Ransomware Lab: Memory Triage",
    subtitle: "Correlate MFT, prefetch, and AmCache artifacts.",
    difficulty: "Advanced",
    categories: ["Malware", "Forensics"],
    concepts: ["MFT", "YARA", "RTP"],
    durationMinutes: 55,
    rating: 4.9,
    enrollCount: 12400,
    thumbnailGradient: "from-rose-600 via-amber-600 to-orange-600",
    cstaCodes: ["3B-AP-13"],
    createdAt: "2026-04-02T10:00:00Z",
    trending: true,
    progressPercent: 0,
  },
  {
    id: "lesson-crypto-hashes",
    title: "Hash Gym: Integrity under fire",
    subtitle: "Length extension, Merkle roots, and HSM hints.",
    difficulty: "Beginner",
    categories: ["Crypto", "Network"],
    concepts: ["SHA-256", "HMAC", "PKI"],
    durationMinutes: 22,
    rating: 4.6,
    enrollCount: 9600,
    thumbnailGradient: "from-emerald-600 via-teal-600 to-cyan-600",
    cstaCodes: ["2-DA-07"],
    createdAt: "2026-03-18T10:00:00Z",
    recommended: true,
  },
  {
    id: "lesson-phishing-soc",
    title: "Phishing triage for SOC rookies",
    subtitle: "Headers, SPF/DKIM/DMARC, and user empathy.",
    difficulty: "Beginner",
    categories: ["Network"],
    concepts: ["email auth", "OSINT", "UEBA"],
    durationMinutes: 18,
    rating: 4.7,
    enrollCount: 22100,
    thumbnailGradient: "from-sky-600 via-indigo-600 to-blue-700",
    cstaCodes: ["1A-IC-17"],
    createdAt: "2026-06-01T10:00:00Z",
    progressPercent: 100,
  },
  {
    id: "lesson-apt-story",
    title: "Purple team tabletop: APT29 remix",
    subtitle: "Collaborative narrative with branching outcomes.",
    difficulty: "Advanced",
    categories: ["Malware", "Network"],
    concepts: ["ATT&CK", "C2", "hunting"],
    durationMinutes: 70,
    rating: 4.95,
    enrollCount: 5400,
    thumbnailGradient: "from-purple-700 via-indigo-700 to-slate-900",
    cstaCodes: ["3A-AP-15", "3B-NI-02"],
    createdAt: "2026-01-20T10:00:00Z",
  },
  {
    id: "lesson-logs-101",
    title: "Log literacy in 25 minutes",
    subtitle: "JSON lines, CEF, and cardinality traps.",
    difficulty: "Beginner",
    categories: ["Forensics"],
    concepts: ["JSON", "regex", "pipelines"],
    durationMinutes: 25,
    rating: 4.5,
    enrollCount: 31000,
    thumbnailGradient: "from-slate-700 via-indigo-600 to-violet-700",
    cstaCodes: ["2-AP-10"],
    createdAt: "2025-12-05T10:00:00Z",
  },
];

function lessonBlocksFor(id: string): LessonDefinition["blocks"] {
  if (id === "lesson-dns-tunnel") {
    return [
      {
        kind: "narrative",
        id: "b1",
        title: "Chapter 1 — Midnight resolver",
        paragraphs: [
          "Campus DNS spikes every ninety seconds. Students blame Wi-Fi; you suspect a covert channel.",
          "Your mentor left a sticky note: **entropy** is the smell test for benign hostnames.",
        ],
        dialogues: [
          { speaker: "Mentor Vega", text: "Treat every NXDOMAIN as a clue, not noise." },
          { speaker: "You", text: "If entropy is high and TTLs are tiny, do we pivot to NetFlow?" },
        ],
        glossary: {
          entropy: "Unpredictability in labels—random-looking subdomains often encode data.",
          NXDOMAIN: "DNS response meaning the domain does not exist.",
        },
      },
      {
        kind: "choice",
        id: "b2",
        question: "What is the safest first pivot when DNS entropy spikes campus-wide?",
        options: [
          { id: "a", label: "Block outbound 53/udp globally", correct: false },
          { id: "b", label: "Sample payloads + correlate with resolver identity", correct: true },
          { id: "c", label: "Reimage every student laptop", correct: false },
        ],
        successMessage: "Correct — preserve evidence while containing blast radius.",
        failureMessage: "Too blunt — triage before containment.",
      },
      {
        kind: "puzzle",
        id: "b3",
        prompt: "Decode the exfil marker: the subdomain is hex for ASCII. Submit the plaintext word (lowercase).",
        answer: "vault",
        caseSensitive: false,
        successMessage: "You recovered the marker — escalate to IR-1.",
      },
      {
        kind: "discovery",
        id: "b4",
        headline: "The resolver whispers",
        teaser: "Something synchronous hides inside TXT records…",
        reveal:
          "Attackers chunked data across TXT strings with jittered TTLs—classic DNS tunneling camouflaged as CDN telemetry.",
      },
      {
        kind: "reflection",
        id: "b5",
        prompt: "How would you explain DNS tunneling to a school board in two sentences?",
        guidance: "Avoid jargon; focus on data sneaking out disguised as normal lookups.",
        minChars: 40,
      },
    ];
  }

  return [
    {
      kind: "narrative",
      id: "g1",
      title: "Introduction",
      paragraphs: [
        "This lesson adapts real SOC workflows into a classroom-safe narrative.",
        "Use hints sparingly—DSH Hacks judges love self-driven discovery.",
      ],
      dialogues: [{ speaker: "Coach", text: "Read twice, click once." }],
      glossary: {
        SOC: "Security Operations Center — analysts monitoring detections.",
      },
    },
    {
      kind: "choice",
      id: "g2",
      question: "What is the primary goal of defensive triage?",
      options: [
        { id: "a", label: "Maximize alerts closed per hour", correct: false },
        { id: "b", label: "Reduce harm while preserving evidence", correct: true },
        { id: "c", label: "Disable all firewalls for visibility", correct: false },
      ],
      successMessage: "Exactly — harm reduction + evidence integrity.",
      failureMessage: "Review the SOC charter and try again.",
    },
    {
      kind: "reflection",
      id: "g3",
      prompt: "Which concept from this track will you teach a peer first?",
      guidance: "Pick something concrete you can demo in 3 minutes.",
      minChars: 20,
    },
  ];
}

function hintsFor(id: string): LessonDefinition["hintsByBlockId"] {
  if (id === "lesson-dns-tunnel") {
    return {
      b1: [
        "Hover glossary terms for quick definitions.",
        "Dialogue order mirrors SOC handoff cadence.",
        "Look for the word entropy in the narrative—it matters later.",
      ],
      b2: ["Eliminate answers that destroy evidence.", "Sampling beats global blocks.", "Think least privilege for DNS."],
      b3: ["The answer is a five-letter English noun.", "Hex decodes to letters you can type.", "Try common security nouns."],
      b4: ["TXT records can carry blobs.", "CDN mimicry is common.", "Click reveal when ready—confetti awaits."],
      b5: ["Mention students or families.", "Contrast normal vs suspicious lookups.", "Keep it under two sentences literally."],
    };
  }
  return {
    g1: ["Glossary chips are clickable.", "Scroll the narrative panel slowly.", "Coach lines are optional flavor."],
    g2: ["Two answers are jokes.", "Evidence matters in regulated sectors.", "Re-read the question literally."],
    g3: ["Pick one technique you actually practiced.", "Mention a tool or artifact by name.", "Keep it peer-teachable."],
  };
}

export function getLessonSummaries(): LessonSummary[] {
  return baseSummaries.map((s) => ({ ...s }));
}

export function getLessonDefinition(id: string): LessonDefinition | null {
  const summary = baseSummaries.find((s) => s.id === id);
  if (!summary) return null;
  return {
    id,
    title: summary.title,
    summary: { ...summary },
    blocks: lessonBlocksFor(id),
    hintsByBlockId: hintsFor(id),
  };
}
