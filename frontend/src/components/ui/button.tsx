import { cn } from "@/lib/utils";

type ButtonProps = React.ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: "primary" | "secondary" | "ghost";
};

export function Button({ className, variant = "primary", ...props }: ButtonProps) {
  return (
    <button
      className={cn(
        "inline-flex min-h-10 items-center justify-center gap-2 rounded-md px-4 text-sm font-medium transition focus:outline-none focus:ring-2 focus:ring-signal-cyan/60 disabled:cursor-not-allowed disabled:opacity-60",
        variant === "primary" && "bg-signal-cyan text-command-950 hover:bg-cyan-300",
        variant === "secondary" && "border border-white/10 bg-white/10 text-white hover:bg-white/15",
        variant === "ghost" && "text-slate-300 hover:bg-white/10 hover:text-white",
        className
      )}
      {...props}
    />
  );
}
