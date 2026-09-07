"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { UploadCloud, FileType, Loader2, CheckCircle2 } from "lucide-react";
import { toast } from "sonner";

export default function UploadCSV() {
  const [file, setFile] = useState<File | null>(null);
  const [loading, setLoading] = useState(false);
  const [isDragging, setIsDragging] = useState(false);
  const router = useRouter();

  const handleDrag = (e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    if (e.type === "dragenter" || e.type === "dragover") {
      setIsDragging(true);
    } else if (e.type === "dragleave") {
      setIsDragging(false);
    }
  };

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setIsDragging(false);
    if (e.dataTransfer.files && e.dataTransfer.files[0]) {
      const droppedFile = e.dataTransfer.files[0];
      if (droppedFile.name.endsWith('.csv')) {
        setFile(droppedFile);
      } else {
        toast.error("Please upload a CSV file");
      }
    }
  };

  const handleUpload = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!file) return;

    setLoading(true);

    const formData = new FormData();
    formData.append("file", file);
    // Hardcoded organization ID for MVP
    formData.append("org_id", "123e4567-e89b-12d3-a456-426614174000");

    try {
      const res = await fetch("http://localhost:8001/api/purchase-orders/upload", {
        method: "POST",
        body: formData,
      });

      if (!res.ok) {
        throw new Error("Failed to upload the file");
      }

      const data = await res.json();
      toast.success(
        <div className="flex flex-col">
          <span className="font-semibold text-slate-900">Upload Successful</span>
          <span className="text-slate-500">{data.rows_processed} rows processed, {data.containers_linked} containers linked.</span>
        </div>
      );
      
      setFile(null);
      // Refresh the page to load new containers
      router.refresh();
    } catch (err: any) {
      toast.error(err.message || "An unexpected error occurred");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="bg-white p-6 rounded-xl shadow-sm border border-slate-200">
      <div className="flex items-center gap-2 mb-4">
        <div className="bg-blue-100 p-1.5 rounded-lg">
          <UploadCloud className="w-5 h-5 text-blue-600" />
        </div>
        <h2 className="text-lg font-semibold text-slate-900">Import Purchase Orders</h2>
      </div>
      
      <form onSubmit={handleUpload} className="flex flex-col space-y-5">
        
        <div 
          className={`relative border-2 border-dashed rounded-lg p-6 flex flex-col items-center justify-center transition-colors
            ${isDragging ? "border-blue-500 bg-blue-50" : "border-slate-300 hover:bg-slate-50"}
            ${file ? "bg-slate-50 border-slate-300" : ""}
          `}
          onDragEnter={handleDrag}
          onDragLeave={handleDrag}
          onDragOver={handleDrag}
          onDrop={handleDrop}
        >
          <input 
            type="file" 
            accept=".csv"
            onChange={(e) => setFile(e.target.files?.[0] || null)}
            className="absolute inset-0 w-full h-full opacity-0 cursor-pointer"
            id="csv-upload"
          />
          
          {file ? (
            <div className="flex flex-col items-center text-center">
              <CheckCircle2 className="w-10 h-10 text-emerald-500 mb-2" />
              <p className="text-sm font-medium text-slate-900">{file.name}</p>
              <p className="text-xs text-slate-500 mt-1">{(file.size / 1024).toFixed(1)} KB</p>
              <button 
                type="button" 
                onClick={(e) => { e.preventDefault(); setFile(null); }}
                className="text-xs text-red-500 hover:text-red-600 font-medium mt-3 z-10 relative"
              >
                Remove file
              </button>
            </div>
          ) : (
            <div className="flex flex-col items-center text-center pointer-events-none">
              <FileType className="w-10 h-10 text-slate-400 mb-3" />
              <p className="text-sm font-medium text-slate-700">Click to upload or drag and drop</p>
              <p className="text-xs text-slate-500 mt-1">CSV files only</p>
            </div>
          )}
        </div>

        <button 
          type="submit" 
          disabled={!file || loading}
          className="relative w-full flex items-center justify-center bg-blue-600 hover:bg-blue-700 text-white font-medium py-2.5 px-4 rounded-lg disabled:opacity-50 disabled:hover:bg-blue-600 transition-colors shadow-sm focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2"
        >
          {loading ? (
            <>
              <Loader2 className="w-4 h-4 mr-2 animate-spin" />
              Processing...
            </>
          ) : (
            "Process via Vizion"
          )}
        </button>
      </form>
    </div>
  );
}
