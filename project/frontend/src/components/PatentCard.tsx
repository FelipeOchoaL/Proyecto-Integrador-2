import Link from "next/link";
import { FileText, ArrowRight, Tag } from "lucide-react";
import type { PatentSummary } from "@/lib/api";

interface Props {
  patent: PatentSummary;
}

const STATUS_MAP: Record<string, { label: string; bg: string; text: string; dot: string }> = {
  G: { label: "Concedida", bg: "bg-emerald-50", text: "text-emerald-700", dot: "bg-emerald-500" },
  A: { label: "Solicitud", bg: "bg-amber-50", text: "text-amber-700", dot: "bg-amber-500" },
  B: { label: "Publicada", bg: "bg-blue-50", text: "text-blue-700", dot: "bg-blue-500" },
};

export default function PatentCard({ patent }: Props) {
  const status = STATUS_MAP[patent.ls] ?? {
    label: patent.ls || "—",
    bg: "bg-gray-50",
    text: "text-gray-600",
    dot: "bg-gray-400",
  };

  const abstract =
    patent.ab && patent.ab.length > 220
      ? patent.ab.replace(/<[^>]*>/g, " ").replace(/\s+/g, " ").trim().slice(0, 220) + "…"
      : patent.ab?.replace(/<[^>]*>/g, " ").replace(/\s+/g, " ").trim();

  return (
    <Link
      href={`/patentes/${patent.id}`}
      className="group block rounded-2xl bg-white/80 backdrop-blur-sm border border-gray-100 p-6 hover:shadow-xl hover:shadow-primary-500/5 hover:border-primary-200 transition-all duration-300 hover:-translate-y-0.5"
    >
      <div className="flex items-start gap-4">
        <div className="hidden sm:flex shrink-0 w-11 h-11 rounded-xl bg-gradient-to-br from-primary-50 to-primary-100 items-center justify-center text-primary-500 group-hover:from-primary-100 group-hover:to-primary-200 transition-colors">
          <FileText className="w-5 h-5" />
        </div>

        <div className="flex-1 min-w-0 space-y-3">
          <div className="flex items-start justify-between gap-3">
            <h2 className="text-base font-semibold text-gray-900 group-hover:text-primary-700 transition-colors leading-snug line-clamp-2">
              {patent.ti || "Sin título"}
            </h2>
            <span className={`shrink-0 flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium ${status.bg} ${status.text}`}>
              <span className={`w-1.5 h-1.5 rounded-full ${status.dot}`} />
              {status.label}
            </span>
          </div>

          <div className="flex flex-wrap items-center gap-2">
            <span className="inline-flex items-center gap-1 px-2.5 py-1 bg-gray-50 border border-gray-100 text-gray-700 rounded-lg text-xs font-mono">
              <Tag className="w-3 h-3" />
              {patent.pn}
            </span>
            {patent.ws && (
              <span className="px-2.5 py-1 bg-primary-50 text-primary-600 rounded-lg text-xs font-medium">
                {patent.ws}
              </span>
            )}
          </div>

          {abstract && (
            <p className="text-sm text-gray-500 leading-relaxed line-clamp-2">
              {abstract}
            </p>
          )}

          {patent.cpc && (
            <div className="flex flex-wrap gap-1.5">
              {patent.cpc
                .split(";")
                .slice(0, 3)
                .map((code) => (
                  <span
                    key={code}
                    className="px-2 py-0.5 bg-primary-50/60 text-primary-600/80 rounded-md text-[11px] font-mono"
                  >
                    {code.trim()}
                  </span>
                ))}
              {patent.cpc.split(";").length > 3 && (
                <span className="px-2 py-0.5 text-gray-400 text-[11px]">
                  +{patent.cpc.split(";").length - 3} más
                </span>
              )}
            </div>
          )}

          <div className="flex items-center gap-1 text-xs font-medium text-primary-500 opacity-0 group-hover:opacity-100 transition-opacity pt-1">
            Ver detalle
            <ArrowRight className="w-3.5 h-3.5 group-hover:translate-x-1 transition-transform" />
          </div>
        </div>
      </div>
    </Link>
  );
}
