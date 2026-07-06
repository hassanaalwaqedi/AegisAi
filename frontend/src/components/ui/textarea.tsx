import { cn } from "@/lib/utils";

export function Textarea({ className, ...props }: React.TextareaHTMLAttributes<HTMLTextAreaElement>) {
  return (
    <textarea
      className={cn(
        "min-h-28 w-full resize-y rounded-md border border-white/10 bg-command-900 px-3 py-2 text-sm text-white outline-none transition focus:border-signal-cyan/60 focus:ring-2 focus:ring-signal-cyan/20",
        className
      )}
      {...props}
    />
  );
}
