import type { ComplianceStatus, RiskLevel, Severity } from "@/lib/types";

export function Card({
  children,
  className = "",
}: {
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <div
      className={`rounded-xl border border-border bg-surface shadow-card ${className}`}
    >
      {children}
    </div>
  );
}

export function StatusBadge({ status }: { status: ComplianceStatus }) {
  const map: Record<ComplianceStatus, string> = {
    pass: "bg-success/15 text-success",
    warning: "bg-warning/15 text-warning",
    fail: "bg-danger/15 text-danger",
  };
  return (
    <span className={`inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-semibold uppercase ${map[status]}`}>
      {status}
    </span>
  );
}

export function RiskBadge({ risk }: { risk: RiskLevel }) {
  const map: Record<RiskLevel, string> = {
    low: "bg-success/15 text-success",
    medium: "bg-warning/15 text-warning",
    high: "bg-danger/15 text-danger",
  };
  return (
    <span className={`inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-semibold uppercase ${map[risk]}`}>
      {risk} risk
    </span>
  );
}

export function SeverityDot({ severity }: { severity: Severity }) {
  const map: Record<Severity, string> = {
    info: "bg-muted",
    low: "bg-brand",
    medium: "bg-warning",
    high: "bg-danger",
  };
  return (
    <span className={`inline-flex items-center gap-1.5 text-xs font-medium uppercase`}>
      <span className={`h-2 w-2 rounded-full ${map[severity]}`} />
      {severity}
    </span>
  );
}
