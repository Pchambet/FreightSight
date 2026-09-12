"use client";

import { CircleHelp } from "lucide-react";
import { useId } from "react";

/** Short glossary help: visible on hover and keyboard focus. */
export default function Hint({ text }: { text: string }) {
  const id = useId();
  return (
    <span className="relative inline-flex group/hint">
      <button
        type="button"
        aria-label={text}
        aria-describedby={id}
        className="p-0.5 rounded text-slate-400 hover:text-slate-600 focus:outline-none focus-visible:ring-2 focus-visible:ring-blue-500"
      >
        <CircleHelp className="w-3.5 h-3.5" aria-hidden />
      </button>
      <span
        id={id}
        role="tooltip"
        className="pointer-events-none absolute left-1/2 bottom-full z-20 mb-1.5 w-56 -translate-x-1/2 rounded-md bg-slate-900 px-2.5 py-2 text-xs font-normal normal-case tracking-normal text-white opacity-0 shadow-lg transition-opacity group-focus-within/hint:opacity-100 group-hover/hint:opacity-100"
      >
        {text}
      </span>
    </span>
  );
}
