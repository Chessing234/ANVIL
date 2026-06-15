import type { CredentialItem } from "@/types/education";

export const CREDENTIAL_CATALOG: CredentialItem[] = [
  {
    id: "cred-1",
    conceptName: "DNS tunneling triage",
    category: "Network",
    completedAt: "2026-05-20T15:30:00Z",
    score: 96,
    tokenId: "0x7a3f…c91",
    chain: "Tutorial L2",
    badges: ["DFIR", "SOC-200"],
  },
  {
    id: "cred-2",
    conceptName: "Ransomware memory forensics",
    category: "Malware",
    completedAt: "2026-04-11T09:00:00Z",
    score: 91,
    tokenId: "0x2b91…8ff",
    chain: "Tutorial L2",
    badges: ["IR-ready", "CSTA-3B"],
  },
  {
    id: "cred-3",
    conceptName: "Hash integrity lab",
    category: "Crypto",
    completedAt: "2026-03-02T18:45:00Z",
    score: 88,
    tokenId: "0xcc10…441",
    chain: "Tutorial L2",
    badges: ["Integrity", "Crypto-101"],
  },
  {
    id: "cred-4",
    conceptName: "Phishing triage sprint",
    category: "Network",
    completedAt: "2026-06-05T12:10:00Z",
    score: 94,
    tokenId: "0x91aa…102",
    chain: "Tutorial L2",
    badges: ["Phishing-IR", "Human-centric"],
  },
];
