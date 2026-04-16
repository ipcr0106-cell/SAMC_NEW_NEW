import { InputHTMLAttributes, forwardRef } from "react";

interface InputProps extends InputHTMLAttributes<HTMLInputElement> {
  label?: string;
  hint?: string;
  error?: string;
  /** inline: 테이블 내부용 (테두리 없이 hover/focus 시만 표시) */
  inline?: boolean;
}

const Input = forwardRef<HTMLInputElement, InputProps>(
  ({ label, hint, error, inline = false, className = "", ...props }, ref) => {
    const baseStyles = inline
      ? "w-full bg-transparent px-2 py-1.5 text-sm text-slate-800 rounded-lg border border-transparent hover:border-slate-200 focus:border-blue-500 focus:ring-1 focus:ring-blue-500/20 outline-none transition-all placeholder:text-slate-300"
      : "w-full bg-white px-3.5 py-2.5 text-sm text-slate-800 rounded-xl border border-slate-200 hover:border-slate-300 focus:border-blue-500 focus:ring-2 focus:ring-blue-500/20 outline-none transition-all placeholder:text-slate-400";

    if (inline) {
      return <input ref={ref} className={`${baseStyles} ${className}`} {...props} />;
    }

    return (
      <div className="flex flex-col gap-1.5">
        {label && (
          <label className="text-sm font-medium text-slate-700">{label}</label>
        )}
        <input ref={ref} className={`${baseStyles} ${className}`} {...props} />
        {hint && !error && (
          <span className="text-xs text-slate-400">{hint}</span>
        )}
        {error && <span className="text-xs text-red-500">{error}</span>}
      </div>
    );
  }
);

Input.displayName = "Input";
export default Input;
