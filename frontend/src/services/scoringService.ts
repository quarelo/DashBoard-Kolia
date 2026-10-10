import { apiRequest } from "../lib/api";
import type { MotiveSide, MotiveWeightInput, ScoringRuler, ScoringSimulation } from "../types";

export function fetchScoringRuler(): Promise<ScoringRuler> {
  return apiRequest<ScoringRuler>("/api/dashboard/scoring");
}

export function simulateScoringRuler(motives: MotiveWeightInput[]): Promise<ScoringSimulation> {
  return apiRequest<ScoringSimulation>("/api/dashboard/scoring/simulate", {
    method: "POST",
    body: { motives },
  });
}

export function saveScoringRuler(motives: MotiveWeightInput[]): Promise<ScoringRuler> {
  return apiRequest<ScoringRuler>("/api/dashboard/scoring", {
    method: "PUT",
    body: { motives },
  });
}

/** Os títulos da tela. "Risco de churn" é jargão; o card diz a mesma coisa sem ele. */
export const sideLabels: Record<MotiveSide, string> = {
  CHURN: "Risco de perder o cliente",
  OPPORTUNITY: "Oportunidade de venda",
};
