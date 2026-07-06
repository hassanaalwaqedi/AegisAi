import { cn } from "@/lib/utils";

export function Input({ className, ...props }: React.InputHTMLAttributes<HTMLInputElement>) {
  return (
    <input
      className={cn(
        "min-h-10 w-full rounded-md border border-white/10 bg-command-900 px-3 text-sm text-white outline-none transition focus:border-signal-cyan/60 focus:ring-2 focus:ring-signal-cyan/20",
        className
      )}
      {...props}
    />
  );
}
