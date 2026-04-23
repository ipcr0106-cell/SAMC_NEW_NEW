import { ButtonHTMLAttributes, ReactNode } from "react";

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: "primary" | "secondary" | "ghost" | "danger";
  size?: "sm" | "md" | "lg";
  children: ReactNode;
  icon?: ReactNode;
}

const variantStyles = {
  primary: "ds-btn-primary",
  secondary: "ds-btn-secondary",
  ghost: "ds-btn-ghost",
  danger: "ds-btn-danger",
};

const sizeStyles = {
  sm: "ds-btn-size-sm",
  md: "ds-btn-size-md",
  lg: "ds-btn-size-lg",
};

export default function Button({
  variant = "primary",
  size = "md",
  children,
  icon,
  className = "",
  ...props
}: ButtonProps) {
  return (
    <button
      className={`ds-btn ${variantStyles[variant]} ${sizeStyles[size]} ${className}`}
      {...props}
    >
      {icon && <span className="ds-btn-icon shrink-0">{icon}</span>}
      {children}
    </button>
  );
}
