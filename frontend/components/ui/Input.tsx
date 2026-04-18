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
      ? "ds-input ds-input-inline px-2 py-1.5"
      : "ds-input px-3.5 py-2.5";

    if (inline) {
      return <input ref={ref} className={`${baseStyles} ${className}`} {...props} />;
    }

    return (
      <div className="flex flex-col" style={{ gap: "var(--ds-space-field-label-gap)" }}>
        {label && (
          <label className="ds-label">{label}</label>
        )}
        <input ref={ref} className={`${baseStyles} ${className}`} {...props} />
        {hint && !error && (
          <span className="text-xs" style={{ color: "var(--ds-color-text-tertiary)" }}>{hint}</span>
        )}
        {error && <span className="text-xs" style={{ color: "var(--ds-color-error-text)" }}>{error}</span>}
      </div>
    );
  }
);

Input.displayName = "Input";
export default Input;
