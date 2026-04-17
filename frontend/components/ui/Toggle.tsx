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
        <span className="ds-toggle-label">{label}</span>
        {description && (
          <span className="ds-toggle-description mt-0.5">{description}</span>
        )}
      </div>
      <div
        role="switch"
        aria-checked={checked}
        className={`relative inline-flex shrink-0 items-center focus:outline-none ds-toggle-track ${
          checked ? "ds-toggle-track-checked" : ""
        }`}
      >
        <span
          className={`inline-block ds-toggle-thumb transition-transform duration-200 ${
            checked ? "translate-x-6" : "translate-x-1"
          }`}
        />
      </div>
    </div>
  );
}
