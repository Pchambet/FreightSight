"use client";

import { useState, useTransition } from "react";
import { useRouter } from "next/navigation";
import { useTranslations } from "next-intl";
import { Plus } from "lucide-react";
import { toast } from "sonner";
import { btnPrimary, input } from "@/components/layout/AppShell";
import { createContainer } from "@/features/actions";

export default function NewContainerForm() {
  const t = useTranslations("containers.new");
  const [value, setValue] = useState("");
  const [pending, startTransition] = useTransition();
  const router = useRouter();

  return (
    <form
      className="flex items-center gap-2"
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
      <input
        value={value}
        onChange={(e) => setValue(e.target.value)}
        placeholder="MSCU1234567"
        pattern="[A-Za-z]{4}[0-9]{7}"
        title={t("title")}
        required
        className={`${input} w-44 font-mono uppercase`}
      />
      <button type="submit" disabled={pending} className={btnPrimary}>
        <Plus className="w-4 h-4 mr-1.5" />
        {t("submit")}
      </button>
    </form>
  );
}
