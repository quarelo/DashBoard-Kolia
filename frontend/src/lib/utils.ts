import { type ClassValue, clsx } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

/**
 * O tooltip de um segmento do Gráfico de Produto: "3 reuniões com reclamação".
 *
 * Os números de `ProductBreakdown` contam reuniões, não itens, e o rótulo tem
 * de dizer isso — "3 reclamações" num número que vale 3 reuniões é a leitura
 * errada mais fácil de fazer. Vive aqui porque a mesma barra é desenhada em
 * duas telas (Dashboard e Produtos) e as duas precisam da mesma frase.
 */
export function meetingMarkLabel(count: number, mark: "reclamação" | "gap" | "elogio"): string {
  return `${count} ${count === 1 ? "reunião" : "reuniões"} com ${mark}`;
}
