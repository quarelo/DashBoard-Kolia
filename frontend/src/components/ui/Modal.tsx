import { useEffect } from "react";
import { cn } from "../../lib/utils";

/**
 * Classes do container que rola **dentro** de um modal. Use sempre esta
 * constante em vez de `overflow-y-auto` solto.
 *
 * O `overscroll-contain` é o que impede o scroll de "encadear": sem ele, ao
 * chegar no fim da lista o scroll passa para a página atrás, e o usuário
 * continua rolando enquanto o modal fica parado e o fundo anda. Era metade da
 * sensação de scroll travado no modal do Gráfico de Produto.
 */
export const MODAL_SCROLL = "overflow-y-auto overscroll-contain";

interface ModalProps {
  onClose: () => void;
  /** `false` ignora clique fora — para uma ação em andamento que não deve ser
   * interrompida, como a exclusão de uma reunião. */
  dismissable?: boolean;
  /** `center` para diálogo centralizado, `right` para painel lateral. */
  align?: "center" | "right";
  /** O painel. Ele é filho do overlay, não irmão — ver o porquê abaixo. */
  children: React.ReactNode;
  className?: string;
}

/**
 * Overlay de modal: fundo, centralização, clique fora e travamento do scroll
 * da página.
 *
 * **Um elemento, não dois.** A versão anterior tinha o fundo e o container de
 * centralização como irmãos, e o container era `pointer-events-none` com o
 * painel `pointer-events-auto` por cima. O efeito colateral: a roda do mouse
 * só chegava ao modal quando o cursor estava sobre o painel. Com `max-w-2xl`
 * (672 px) numa tela de 1920, sobravam ~620 px de cada lado onde rolar movia a
 * página de trás em vez da lista — o scroll funcionava ou não conforme onde
 * estava o cursor, que era a principal causa da sensação de travado. Aqui o
 * overlay é um só, recebe os eventos, e fecha no clique apenas quando o alvo é
 * ele mesmo (clique dentro do painel não borbulha como "clique fora").
 *
 * **O scroll do `body` fica travado enquanto o modal está aberto.** Junto com
 * o `MODAL_SCROLL` nos containers internos, isso garante que nada atrás se
 * mexa.
 *
 * **O fundo é um irmão do painel, nunca um ancestral.** Esta separação existe
 * só por causa de desempenho, e a primeira versão deste componente errou nela:
 * ao unificar em um elemento, o `backdrop-blur` ficou no overlay e o painel —
 * com a lista que rola dentro dele — virou descendente de um elemento com
 * filtro. Um `backdrop-filter` estabelece bloco de contenção e impede que o
 * conteúdo que rola seja promovido a camada própria, então cada frame de scroll
 * voltava a ser pintado atravessando o filtro. O scroll continuou travado, e foi
 * o refactor que piorou. Se precisar de filtro no fundo, ele vai no `<div>`
 * absoluto abaixo — que é `pointer-events-none` para o clique seguir chegando ao
 * overlay.
 *
 * Fechar com `Esc` e prender o foco continuam **não** implementados aqui.
 */
export function Modal({
  onClose,
  dismissable = true,
  align = "center",
  children,
  className,
}: ModalProps) {
  useEffect(() => {
    const { body, documentElement } = document;
    const previousOverflow = body.style.overflow;
    const previousPadding = body.style.paddingRight;
    // Esconder a barra de rolagem alarga a página e empurra o conteúdo; o
    // padding equivalente evita esse salto ao abrir e fechar.
    const scrollbar = window.innerWidth - documentElement.clientWidth;
    body.style.overflow = "hidden";
    if (scrollbar > 0) body.style.paddingRight = `${scrollbar}px`;
    return () => {
      body.style.overflow = previousOverflow;
      body.style.paddingRight = previousPadding;
    };
  }, []);

  return (
    <div
      onClick={(event) => {
        if (dismissable && event.target === event.currentTarget) onClose();
      }}
      className={cn(
        "fixed inset-0 z-50 flex animate-fade-in",
        align === "center" ? "items-center justify-center p-4" : "items-stretch justify-end",
        className,
      )}
    >
      {/* Fundo. O `z-[-1]` é necessário, não decorativo: um elemento absoluto
          pinta *acima* de um irmão estático, qualquer que seja a ordem no DOM,
          então sem ele o fundo cobriria o painel. O overlay é `fixed` com
          z-index, logo cria contexto de empilhamento, e o -1 fica contido nele.
          `pointer-events-none` deixa o clique chegar ao overlay, que é quem
          decide fechar.
          O `backdrop-blur-[2px]` que havia aqui foi removido: 2 px é quase
          imperceptível e era a parte caríssima — um `backdrop-filter` cobrindo
          a viewport inteira é refeito sempre que algo muda, e atrás do modal do
          dashboard há cinco gráficos Recharts em SVG, numa máquina cuja GPU é
          dividida com o Ollama. Para trazer de volta, é só acrescentar a classe
          nesta linha. */}
      <div className="absolute inset-0 z-[-1] bg-black/25 pointer-events-none" />
      {children}
    </div>
  );
}
