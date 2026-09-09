"use client";

import { useRef, useState, useTransition } from "react";
import { useRouter } from "next/navigation";
import { useTranslations } from "next-intl";
import { FileUp, Loader2 } from "lucide-react";
import { toast } from "sonner";
import { btnPrimary } from "@/components/layout/AppShell";
import { uploadInvoice } from "@/features/actions";

export default function UploadForm() {
  const t = useTranslations("invoices.upload");
  const [file, setFile] = useState<File | null>(null);
  const [pending, start] = useTransition();
  const inputRef = useRef<HTMLInputElement>(null);
  const router = useRouter();

  const submit = () => {
    if (!file) return;
    const fd = new FormData();
    fd.append("file", file);
    start(async () => {
      const r = await uploadInvoice(fd);
      if (!r.ok) return void toast.error(r.error);
      toast.success(t("done"));
      setFile(null);
      if (inputRef.current) inputRef.current.value = "";
      router.push(`/invoices/${r.data.id}`);
    });
  };

  return (
    <div className="p-5 flex flex-col sm:flex-row sm:items-center gap-4">
      <label className="flex-1 flex items-center gap-3 rounded-md border border-dashed border-slate-300 px-4 py-3 cursor-pointer hover:bg-slate-50">
        <FileUp className="w-5 h-5 text-slate-400 shrink-0" />
        <span className="text-sm text-slate-600 truncate">{file ? file.name : t("choose")}</span>
        <input ref={inputRef} type="file" accept="application/pdf,image/png,image/jpeg" className="sr-only" onChange={(e) => setFile(e.target.files?.[0] ?? null)} />
      </label>
      <button type="button" onClick={submit} disabled={!file || pending} className={btnPrimary}>
        {pending ? <Loader2 className="w-4 h-4 mr-2 animate-spin" /> : null}{pending ? t("uploading") : t("submit")}
      </button>
    </div>
  );
}
