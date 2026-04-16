"use client";

interface ToggleProps {
  label: string;
  checked: boolean;
  onChange: (checked: boolean) => void;
  description?: string;
}

export default function Toggle({
  label,
  checked,
  onChange,
  description,
}: ToggleProps) {
  return (
    <div
      className="flex items-center justify-between gap-3 cursor-pointer group select-none"
      onClick={() => onChange(!checked)}
    >
      <div className="flex flex-col">
        <span className="text-sm font-medium text-slate-700">{label}</span>
        {description && (
          <span className="text-xs text-slate-400 mt-0.5">{description}</span>
        )}
      </div>
      <div
        role="switch"
        aria-checked={checked}
        className={`relative inline-flex h-6 w-11 shrink-0 items-center rounded-full transition-colors duration-200 focus:outline-none ${
          checked ? "bg-blue-600" : "bg-slate-200"
        }`}
      >
        <span
          className={`inline-block h-4 w-4 rounded-full bg-white shadow-sm transition-transform duration-200 ${
            checked ? "translate-x-6" : "translate-x-1"
          }`}
        />
      </div>
    </div>
  );
}
