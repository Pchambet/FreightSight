"use client";

import { useRef, useState, useTransition } from "react";
import { useRouter } from "next/navigation";
import { useTranslations } from "next-intl";
import { FileUp, Loader2 } from "lucide-react";
import { toast } from "sonner";
import { btnPrimary, label } from "@/components/layout/AppShell";
import FileTooLarge from "@/components/shared/FileTooLarge";
import { uploadInvoice } from "@/features/actions";
import { isTooLarge } from "@/lib/uploads";

export default function UploadForm() {
  const t = useTranslations("invoices.upload");
  const [file, setFile] = useState<File | null>(null);
  const [pending, start] = useTransition();
  const inputRef = useRef<HTMLInputElement>(null);
  const router = useRouter();
  const tooLarge = isTooLarge(file);

  const submit = () => {
    if (!file || tooLarge) return;
    const fd = new FormData();
    fd.append("file", file);
    start(async () => {
      // A request refused before the action runs (the connection dropped, a body over a limit)
      // rejects instead of returning a result: said here, rather than left to take the page down.
      const r = await uploadInvoice(fd).catch(() => null);
      if (!r) return void toast.error(t("failed"));
      if (!r.ok) return void toast.error(r.error);
      toast.success(t("done"));
      setFile(null);
      if (inputRef.current) inputRef.current.value = "";
      router.push(`/invoices/${r.data.id}`);
    });
  };

  return (
    <div className="p-5 space-y-2">
      <div className="flex flex-col sm:flex-row sm:items-end gap-4">
        <div className="flex-1 min-w-0">
          <span id="invoice-file-label" className={label}>{t("fileLabel")}</span>
          <label
            aria-labelledby="invoice-file-label"
            className="flex items-center gap-3 rounded-md border border-dashed border-slate-300 px-4 py-3 cursor-pointer hover:bg-slate-50 focus-within:ring-2 focus-within:ring-blue-500"
          >
            <FileUp className="w-5 h-5 text-slate-400 shrink-0" aria-hidden />
            <span className="text-sm text-slate-600 truncate">{file ? file.name : t("choose")}</span>
            <input
              ref={inputRef}
              id="invoice-file"
              type="file"
              accept="application/pdf,image/png,image/jpeg"
              className="sr-only"
              aria-invalid={tooLarge || undefined}
              aria-describedby={tooLarge ? "invoice-file-too-large" : undefined}
              onChange={(e) => setFile(e.target.files?.[0] ?? null)}
            />
          </label>
        </div>
        <button type="button" onClick={submit} disabled={!file || tooLarge || pending} className={`${btnPrimary} shrink-0`}>
          {pending ? <Loader2 className="w-4 h-4 mr-2 animate-spin" aria-hidden /> : null}
          {pending ? t("uploading") : t("submit")}
        </button>
      </div>
      {tooLarge ? <FileTooLarge id="invoice-file-too-large" file={file} kind="invoice" /> : null}
    </div>
  );
}
