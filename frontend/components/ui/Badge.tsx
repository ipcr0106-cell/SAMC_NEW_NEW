import { ReactNode } from "react";

interface BadgeProps {
  children: ReactNode;
  variant?: "blue" | "green" | "amber" | "red" | "slate" | "purple";
  size?: "sm" | "md";
  removable?: boolean;
  onRemove?: () => void;
}

const variantStyles = {
  blue: "ds-badge-blue",
  green: "ds-badge-green",
  amber: "ds-badge-amber",
  red: "ds-badge-red",
  slate: "ds-badge-slate",
  purple: "ds-badge-purple",
};

const sizeStyles = {
  sm: "ds-badge-sm",
  md: "ds-badge-md",
};

export default function Badge({
  children,
  variant = "blue",
  size = "sm",
  removable = false,
  onRemove,
}: BadgeProps) {
  return (
    <span
      className={`ds-badge ${variantStyles[variant]} ${sizeStyles[size]}`}
    >
      {children}
      {removable && (
        <button
          onClick={onRemove}
          className="ml-0.5 rounded-full p-0.5 transition-colors"
          style={{ color: "currentColor" }}
          type="button"
        >
          <svg
            width="12"
            height="12"
            viewBox="0 0 12 12"
            fill="none"
            stroke="currentColor"
            strokeWidth="1.5"
          >
            <path d="M3 3l6 6M9 3l-6 6" />
          </svg>
        </button>
      )}
    </span>
  );
}
