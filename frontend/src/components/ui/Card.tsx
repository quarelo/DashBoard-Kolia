import { cn } from "../../lib/utils";

interface CardProps {
  children: React.ReactNode;
  className?: string;
  hover?: boolean;
  onClick?: () => void;
  as?: "div" | "article";
}

export function Card({ children, className, hover, onClick, as: Tag = "div" }: CardProps) {
  return (
    <Tag
      onClick={onClick}
      className={cn(
        "bg-white rounded-xl border border-surface-border shadow-card",
        hover && "transition-all duration-200 hover:shadow-card-md hover:border-brand/25 cursor-pointer",
        onClick && "cursor-pointer",
        className
      )}
    >
      {children}
    </Tag>
  );
}

export function CardHeader({ children, className }: { children: React.ReactNode; className?: string }) {
  return <div className={cn("px-5 pt-5 pb-2", className)}>{children}</div>;
}

export function CardContent({ children, className }: { children: React.ReactNode; className?: string }) {
  return <div className={cn("px-5 pb-5", className)}>{children}</div>;
}

export function CardTitle({ children, className }: { children: React.ReactNode; className?: string }) {
  return <h3 className={cn("text-sm font-bold text-ink", className)}>{children}</h3>;
}

export function CardSubtitle({ children, className }: { children: React.ReactNode; className?: string }) {
  return <p className={cn("text-xs text-ink-secondary mt-0.5", className)}>{children}</p>;
}
