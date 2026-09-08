"use client";

import { useTransition } from "react";
import { useRouter } from "next/navigation";
import { useTranslations } from "next-intl";
import { Sparkles } from "lucide-react";
import { toast } from "sonner";
import { btnSecondary } from "@/components/layout/AppShell";
import { loadSampleData } from "@/features/actions";

/** Empty-state shortcut: fills the organization with one demo shipment so the board has something to show. */
export default function LoadSampleDataButton() {
  const t = useTranslations("containers.sample");
  const [pending, startTransition] = useTransition();
  const router = useRouter();

  return (
    <button
      type="button"
      disabled={pending}
      className={btnSecondary}
      onClick={() =>
        startTransition(async () => {
          const result = await loadSampleData();
          if (!result.ok) return void toast.error(result.error);
          toast.success(t("loaded"));
          router.refresh();
        })
      }
    >
      <Sparkles className="w-4 h-4 mr-1.5" />
      {pending ? t("loading") : t("load")}
    </button>
  );
}
