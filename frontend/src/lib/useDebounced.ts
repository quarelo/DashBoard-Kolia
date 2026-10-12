import { useEffect, useState } from "react";

/** O valor depois de `delay` ms parado.
 *
 * A busca da lista de reuniões virou uma chamada ao backend, e sem isso cada
 * tecla digitada era uma consulta: "1153738" disparava sete.
 */
export function useDebounced<T>(value: T, delay = 300): T {
  const [settled, setSettled] = useState(value);

  useEffect(() => {
    const timer = setTimeout(() => setSettled(value), delay);
    return () => clearTimeout(timer);
  }, [value, delay]);

  return settled;
}
