import { Badge } from "@/components/ui/badge";

type PageHeaderProps = {
  eyebrow?: string;
  title: string;
  description: string;
  badge?: string;
};

export function PageHeader({ eyebrow, title, description, badge }: PageHeaderProps) {
  return (
    <div className="mb-6 flex flex-col gap-3 lg:flex-row lg:items-end lg:justify-between">
      <div>
        {eyebrow ? <p className="mb-2 text-xs font-semibold uppercase tracking-[0.18em] text-signal-cyan">{eyebrow}</p> : null}
        <h1 className="page-heading">{title}</h1>
        <p className="mt-2 max-w-3xl text-sm leading-6 text-slate-400">{description}</p>
      </div>
      {badge ? <Badge variant="outline">{badge}</Badge> : null}
    </div>
  );
}
