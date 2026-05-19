"use client";

import { useState } from "react";
import { FileDown, Loader2 } from "lucide-react";
import { exportPdf } from "@/lib/api";

interface Props {
  query: string;
  topK?: number;
}

export default function ExportButton({ query, topK = 20 }: Props) {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleExport() {
    setLoading(true);
    setError(null);
    try {
      await exportPdf(query, topK);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Error desconocido");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="flex flex-col items-end gap-1">
      <button
        onClick={handleExport}
        disabled={loading}
        className="flex items-center gap-2 px-4 py-2 rounded-xl bg-primary-600 text-white text-sm font-medium hover:bg-primary-700 disabled:opacity-60 disabled:cursor-not-allowed transition-colors"
      >
        {loading ? (
          <>
            <Loader2 className="w-4 h-4 animate-spin" />
            Generando PDF...
          </>
        ) : (
          <>
            <FileDown className="w-4 h-4" />
            Exportar PDF
          </>
        )}
      </button>
      {error && (
        <p className="text-xs text-red-500">{error}</p>
      )}
    </div>
  );
}
