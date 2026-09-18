"use client";

import { CircleHelp } from "lucide-react";

/**
 * Short glossary help: visible on hover and keyboard focus.
 *
 * The text is the button's name, so a screen reader says it once, on focus; the bubble is for the eye
 * only (hidden from assistive technology, or the text would be read a second time as a description
 * and a third time in the page's flow). The button is 24 px square (WCAG 2.2 target size) while
 * taking the room of the 18 px it looks like: the negative margin gives the difference back.
 */
export default function Hint({ text }: { text: string }) {
  return (
    <span className="relative inline-flex group/hint">
      <button
        type="button"
        aria-label={text}
        className="-m-[3px] p-[5px] rounded text-slate-500 hover:text-slate-700 focus:outline-none focus-visible:ring-2 focus-visible:ring-blue-500"
      >
        <CircleHelp className="w-3.5 h-3.5" aria-hidden />
      </button>
      <span
        aria-hidden
        className="pointer-events-none absolute left-1/2 bottom-full z-20 mb-1.5 w-[min(14rem,calc(100vw-2rem))] -translate-x-1/2 rounded-md bg-slate-900 px-2.5 py-2 text-xs font-normal normal-case tracking-normal text-white opacity-0 shadow-lg transition-opacity group-focus-within/hint:opacity-100 group-hover/hint:opacity-100"
      >
        {text}
      </span>
    </span>
  );
}
