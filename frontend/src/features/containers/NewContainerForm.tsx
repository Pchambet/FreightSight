"use client";

import { useState, useTransition } from "react";
import { useRouter } from "next/navigation";
import { useTranslations } from "next-intl";
import { Plus } from "lucide-react";
import { toast } from "sonner";
import { btnPrimary, input, label } from "@/components/layout/AppShell";
import { createContainer } from "@/features/actions";

export default function NewContainerForm() {
  const t = useTranslations("containers.new");
  const [value, setValue] = useState("");
  const [pending, startTransition] = useTransition();
  const router = useRouter();

  return (
    <form
      className="flex flex-col sm:flex-row sm:items-end gap-2"
      onSubmit={(e) => {
        e.preventDefault();
        startTransition(async () => {
          const result = await createContainer(value);
          if (!result.ok) return void toast.error(result.error);
          toast.success(t("added"));
          setValue("");
          router.push(`/container/${result.data.id}`);
        });
      }}
    >
      <div className="w-full sm:w-auto">
        <label htmlFor="new-container-number" className={label}>{t("label")}</label>
        <input
          id="new-container-number"
          value={value}
          onChange={(e) => setValue(e.target.value)}
          placeholder="MSCU1234567"
          pattern="[A-Za-z]{4}[0-9]{7}"
          title={t("title")}
          aria-describedby="new-container-hint"
          required
          className={`${input} sm:w-44 font-mono uppercase`}
        />
        <p id="new-container-hint" className="text-xs text-slate-400 mt-1">{t("title")}</p>
      </div>
      <button type="submit" disabled={pending} className={`${btnPrimary} shrink-0`}>
        <Plus className="w-4 h-4 mr-1.5" />
        {t("submit")}
      </button>
    </form>
  );
}
