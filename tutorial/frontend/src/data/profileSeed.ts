import type { LeaderboardRow, StudentProfile } from "@/types/education";

export const DEFAULT_PROFILE: StudentProfile = {
  id: "stu-demo",
  displayName: "Jordan Analyst",
  avatarGradient: "from-fuchsia-500 via-indigo-500 to-cyan-400",
  level: 4,
  levelTitle: "Threat Hunter",
  xp: 12400,
  xpToNext: 15000,
  streakDays: 12,
  lessonsCompleted: 28,
  achievements: [
    {
      id: "a1",
      title: "First investigation",
      description: "Completed your first guided SOC narrative.",
      icon: "shield",
      unlocked: true,
      unlockedAt: "2026-01-10",
    },
    {
      id: "a2",
      title: "Sandbox master",
      description: "Finished three sandbox challenges without resets.",
      icon: "terminal",
      unlocked: true,
    },
    {
      id: "a3",
      title: "10-day streak",
      description: "Maintain a 10-day learning streak.",
      icon: "flame",
      unlocked: true,
    },
    {
      id: "a4",
      title: "CISO track",
      description: "Reach CISO level in the progression ladder.",
      icon: "trophy",
      unlocked: false,
    },
  ],
};

export const WEEKLY_BOARD: LeaderboardRow[] = [
  { rank: 1, handle: "redTeamRiley", xp: 18200, streak: 18, lessonsCompleted: 34 },
  { rank: 2, handle: "blueMorgan", xp: 17640, streak: 12, lessonsCompleted: 31 },
  { rank: 3, handle: "Jordan Analyst", xp: 12400, streak: 12, lessonsCompleted: 28, isYou: true },
  { rank: 4, handle: "packetPat", xp: 11820, streak: 9, lessonsCompleted: 26 },
  { rank: 5, handle: "hashHarper", xp: 10950, streak: 7, lessonsCompleted: 24 },
];

export const MONTHLY_BOARD: LeaderboardRow[] = [
  { rank: 1, handle: "hashHarper", xp: 50200, streak: 21, lessonsCompleted: 62 },
  { rank: 2, handle: "redTeamRiley", xp: 48900, streak: 18, lessonsCompleted: 58 },
  { rank: 3, handle: "Jordan Analyst", xp: 41200, streak: 12, lessonsCompleted: 48, isYou: true },
];
