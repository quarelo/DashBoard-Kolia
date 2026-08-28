import logoBlackSrc from "../../assets/Group 8.svg";  // texto preto  → fundo claro
import logoLightSrc from "../../assets/Group 9.svg";  // texto branco → fundo escuro
import logoWhiteSrc from "../../assets/Group 6.svg";  // tudo branco  → fundo laranja/colorido
import iconSrc      from "../../assets/Group.svg";    // apenas ícone laranja

type LogoVariant =
  | "horizontal-dark"   // ícone laranja + texto preto  (fundos brancos/claros)
  | "horizontal-light"  // ícone laranja + texto branco (fundos escuros)
  | "horizontal-white"  // tudo branco                  (fundos coloridos/laranja)
  | "icon";             // apenas o símbolo laranja

interface KoliaLogoProps {
  variant?: LogoVariant;
  /** Altura em px — largura é calculada proporcionalmente. Default: 32 */
  height?: number;
  className?: string;
}

export function KoliaLogo({
  variant = "horizontal-dark",
  height = 32,
  className = "",
}: KoliaLogoProps) {
  const src =
    variant === "horizontal-dark"  ? logoBlackSrc :
    variant === "horizontal-light" ? logoLightSrc :
    variant === "horizontal-white" ? logoWhiteSrc :
    iconSrc;

  const aspectRatio = variant === "icon" ? 578 / 545 : 5720 / 1392;
  const width = Math.round(height * aspectRatio);

  return (
    <img
      src={src}
      alt="KOLIA"
      width={width}
      height={height}
      style={{ height, width }}
      className={`object-contain select-none ${className}`}
      draggable={false}
    />
  );
}
