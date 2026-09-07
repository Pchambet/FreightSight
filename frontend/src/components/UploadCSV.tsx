"use client";

import { useRef, useState, useTransition } from "react";
import { useRouter } from "next/navigation";
import { CheckCircle2, FileType, Loader2, UploadCloud } from "lucide-react";
import { toast } from "sonner";
import { uploadPurchaseOrders } from "@/features/actions";

export default function UploadCSV() {
  const [file, setFile] = useState<File | null>(null);
  const [isDragging, setIsDragging] = useState(false);
  const [pending, startTransition] = useTransition();
  const inputRef = useRef<HTMLInputElement>(null);
  const router = useRouter();

  const pick = (candidate: File | undefined) => {
    if (!candidate) return;
    if (!candidate.name.toLowerCase().endsWith(".csv")) {
      toast.error("Only CSV files are supported.");
      return;
    }
    setFile(candidate);
  };

  const submit = (e: React.FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    if (!file) return;
    const formData = new FormData();
    formData.append("file", file);
    startTransition(async () => {
      const result = await uploadPurchaseOrders(formData);
      if (!result.ok) {
        toast.error(result.error);
        return;
      }
      const { rows_processed, rows_skipped, containers_created, containers_linked } = result.data;
      toast.success(
        `${rows_processed} rows imported, ${containers_created} containers created, ${containers_linked} links.` +
          (rows_skipped.length ? ` ${rows_skipped.length} rows skipped.` : ""),
      );
      for (const skipped of rows_skipped.slice(0, 5)) {
        toast.warning(`Row ${skipped.row}: ${skipped.message}`);
      }
      setFile(null);
      if (inputRef.current) inputRef.current.value = "";
      router.refresh();
    });
  };

  return (
    <div className="bg-white p-5 rounded-lg border border-slate-200">
      <h2 className="text-sm font-semibold flex items-center gap-2 mb-1">
        <UploadCloud className="w-4 h-4 text-slate-500" />
        Import purchase orders
      </h2>
      <p className="text-xs text-slate-500 mb-4">
        CSV with <code className="font-mono">po_number</code>, <code className="font-mono">supplier_name</code>,{" "}
        <code className="font-mono">total_value</code>, <code className="font-mono">container_number</code>. Excel exports
        (UTF-8 BOM, semicolons, French decimals) are accepted.
      </p>

      <form onSubmit={submit} className="space-y-4">
        <div
          className={`relative border-2 border-dashed rounded-md p-6 flex flex-col items-center justify-center text-center transition-colors ${
            isDragging ? "border-blue-500 bg-blue-50" : "border-slate-300 hover:bg-slate-50"
          }`}
          onDragEnter={(e) => { e.preventDefault(); setIsDragging(true); }}
          onDragOver={(e) => { e.preventDefault(); setIsDragging(true); }}
          onDragLeave={(e) => { e.preventDefault(); setIsDragging(false); }}
          onDrop={(e) => { e.preventDefault(); setIsDragging(false); pick(e.dataTransfer.files?.[0]); }}
        >
          <input
            ref={inputRef}
            type="file"
            accept=".csv,text/csv"
            onChange={(e) => pick(e.target.files?.[0])}
            className="absolute inset-0 w-full h-full opacity-0 cursor-pointer"
            aria-label="Choose a CSV file"
          />
          {file ? (
            <>
              <CheckCircle2 className="w-8 h-8 text-emerald-500 mb-2" />
              <p className="text-sm font-medium">{file.name}</p>
              <p className="text-xs text-slate-500 mt-1">{(file.size / 1024).toFixed(1)} KB</p>
            </>
          ) : (
            <>
              <FileType className="w-8 h-8 text-slate-400 mb-2" />
              <p className="text-sm font-medium text-slate-700">Click to choose or drop a CSV</p>
            </>
          )}
        </div>

        <button
          type="submit"
          disabled={!file || pending}
          className="w-full inline-flex items-center justify-center bg-blue-600 hover:bg-blue-700 disabled:opacity-50 disabled:hover:bg-blue-600 text-white text-sm font-medium py-2 px-4 rounded-md focus:outline-none focus-visible:ring-2 focus-visible:ring-blue-500 focus-visible:ring-offset-2"
        >
          {pending ? (
            <>
              <Loader2 className="w-4 h-4 mr-2 animate-spin" />
              Importing…
            </>
          ) : (
            "Import"
          )}
        </button>
      </form>
    </div>
  );
}
