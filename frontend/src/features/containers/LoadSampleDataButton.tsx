"use client";

import { useTransition } from "react";
import { useRouter } from "next/navigation";
import { Sparkles } from "lucide-react";
import { toast } from "sonner";
import { btnSecondary } from "@/components/layout/AppShell";
import { loadSampleData } from "@/features/actions";

/** Empty-state shortcut: fills the organization with one demo shipment so the board has something to show. */
export default function LoadSampleDataButton() {
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
          toast.success("Sample data loaded");
          router.refresh();
        })
      }
    >
      <Sparkles className="w-4 h-4 mr-1.5" />
      {pending ? "Loading…" : "Load sample data"}
    </button>
  );
}
