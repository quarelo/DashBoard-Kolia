import type { TfidfTerm } from "../types";
import tfidfData from "../data/tfidf.json";

const terms: TfidfTerm[] = tfidfData as TfidfTerm[];

export const tfidfService = {
  getAll(): TfidfTerm[] {
    return terms;
  },

  getTopTerms(count = 10): TfidfTerm[] {
    return [...terms]
      .sort((a, b) => b.weight - a.weight)
      .slice(0, count);
  },

  getByCategory(category: string): TfidfTerm[] {
    return terms.filter((t) => t.category === category);
  },

  getCategories(): string[] {
    return [...new Set(terms.map((t) => t.category))];
  },

  getWordCloudData() {
    return terms.map((t) => ({
      text: t.term,
      value: Math.round(t.weight * 100),
    }));
  },
};
