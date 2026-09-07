"use client";

import { useState, useRef } from "react";
import { Sparkles, UploadCloud, Loader2, CheckCircle2 } from "lucide-react";
import { useRouter } from "next/navigation";
import { toast } from "sonner";

export default function AIInvoiceUpload({ containerId }: { containerId: string }) {
  const [isDragging, setIsDragging] = useState(false);
  const [isUploading, setIsUploading] = useState(false);
  const [success, setSuccess] = useState(false);
  const router = useRouter();
  const fileInputRef = useRef<HTMLInputElement>(null);

  const handleFile = async (file: File) => {
    if (!file || file.type !== "application/pdf") {
      toast.error("Please upload a PDF file.");
      return;
    }
    
    setIsUploading(true);
    setSuccess(false);

    const formData = new FormData();
    formData.append("file", file);

    try {
      const res = await fetch(`http://localhost:8001/api/containers/${containerId}/upload-invoice`, {
        method: "POST",
        body: formData,
      });

      if (!res.ok) {
        throw new Error("Upload failed");
      }

      setSuccess(true);
      toast.success("Invoice parsed successfully. Landed costs updated.");
      router.refresh();
      setTimeout(() => setSuccess(false), 3000);
    } catch (e) {
      console.error(e);
      toast.error("Error uploading invoice. Please try again.");
    } finally {
      setIsUploading(false);
    }
  };

  return (
    <div className="bg-gradient-to-br from-indigo-500 to-purple-600 p-[1.5px] rounded-xl shadow-sm">
      <div className="bg-white rounded-[10.5px] p-6 text-center overflow-hidden relative">
        <div className="absolute top-0 right-0 p-3">
          <div className="bg-indigo-50 text-indigo-600 text-[10px] uppercase tracking-wider font-bold px-2 py-1 rounded-full flex items-center gap-1 border border-indigo-100">
            <Sparkles className="w-3 h-3" />
            AI Parse
          </div>
        </div>

        <h3 className="text-base font-semibold text-slate-900 mb-1 flex items-center justify-center gap-2">
          Automated Invoice
        </h3>
        <p className="text-xs text-slate-500 mb-4">Drag and drop a PDF to auto-extract costs</p>

        <div
          className={`border-2 border-dashed rounded-lg p-6 transition-all duration-200 cursor-pointer ${
            isDragging ? "border-indigo-500 bg-indigo-50" : "border-slate-200 hover:border-indigo-400 hover:bg-slate-50"
          }`}
          onDragOver={(e) => { e.preventDefault(); setIsDragging(true); }}
          onDragLeave={() => setIsDragging(false)}
          onDrop={(e) => {
            e.preventDefault();
            setIsDragging(false);
            const file = e.dataTransfer.files?.[0];
            if (file) handleFile(file);
          }}
          onClick={() => fileInputRef.current?.click()}
        >
          <input
            type="file"
            accept="application/pdf"
            className="hidden"
            ref={fileInputRef}
            onChange={(e) => {
              const file = e.target.files?.[0];
              if (file) handleFile(file);
              // Reset the value so the same file can be uploaded again if needed
              if (e.target) e.target.value = '';
            }}
          />
          
          <div className="flex flex-col items-center justify-center">
            {isUploading ? (
              <Loader2 className="w-8 h-8 text-indigo-600 animate-spin mb-2" />
            ) : success ? (
              <CheckCircle2 className="w-8 h-8 text-emerald-500 mb-2" />
            ) : (
              <UploadCloud className={`w-8 h-8 mb-2 ${isDragging ? "text-indigo-600" : "text-slate-400"}`} />
            )}
            
            <p className="text-sm font-medium text-slate-700">
              {isUploading ? "Extracting data with AI..." : success ? "Extracted successfully!" : "Click or drop PDF here"}
            </p>
          </div>
        </div>
      </div>
    </div>
  );
}
