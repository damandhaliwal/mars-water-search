import type { AgentAction, Regime } from "./types";
export const regimeLabels: Record<Regime, string> = {
  private: "Private",
  ai_pool: "AI pool",
  human_assisted: "Human assisted",
};
export const actionLabels: Record<AgentAction, string> = {
  move: "Move",
  observe: "Observe",
  drill: "Drill",
  join_ai_pool: "Join AI pool",
  choose_human: "Choose human",
  invalid_decision: "Invalid decision",
};
export function agentColor(id: string) {
  const known: Record<string, string> = {
    A: "#a14f35",
    B: "#466b86",
    C: "#8b6086",
    D: "#4a7966",
  };
  let hash = 0;
  for (const character of id)
    hash = (hash * 31 + character.charCodeAt(0)) >>> 0;
  return known[id] ?? `hsl(${(hash * 137.508) % 360} 40% 42%)`;
}
