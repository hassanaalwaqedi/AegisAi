import { cn } from "@/lib/utils";

type CardProps = React.HTMLAttributes<HTMLDivElement>;

export function Card({ className, ...props }: CardProps) {
  return (
    <div
      className={cn("glass-panel rounded-lg p-5", className)}
      {...props}
    />
  );
}

export function CardHeader({ className, ...props }: CardProps) {
  return <div className={cn("mb-4 flex items-start justify-between gap-4", className)} {...props} />;
}

export function CardTitle({ className, ...props }: CardProps) {
  return <h2 className={cn("text-base font-semibold text-white", className)} {...props} />;
}

export function CardDescription({ className, ...props }: CardProps) {
  return <p className={cn("mt-1 text-sm text-slate-400", className)} {...props} />;
}
