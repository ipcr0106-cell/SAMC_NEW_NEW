/**
 * 기능4: 부적절 문구·그림 이슈 목록 컴포넌트
 */

import type { LabelIssue } from "@/types/pipeline";
import { SEVERITY_LABEL } from "../types";

interface IssueListProps {
  issues: LabelIssue[];
  isConfirmed: boolean;
}

export default function IssueList({ issues, isConfirmed }: IssueListProps) {
  if (issues.length === 0) {
    return (
      <div className="text-sm text-green-600 bg-green-50 rounded p-3">
        부적절한 문구·그림이 발견되지 않았습니다.
      </div>
    );
  }

  return (
    <div className="space-y-2">
      <h3 className="text-sm font-semibold text-gray-700">
        부적절 문구·그림 ({issues.length}건)
      </h3>
      <ul className="space-y-2">
        {issues.map((issue, idx) => (
          <li
            key={idx}
            className={`rounded-md border p-3 text-sm space-y-1 ${
              issue.severity === "must_fix"
                ? "border-red-200 bg-red-50"
                : "border-yellow-200 bg-yellow-50"
            }`}
          >
            <div className="flex items-center gap-2">
              <span
                className={`text-xs font-medium px-1.5 py-0.5 rounded ${
                  issue.severity === "must_fix"
                    ? "bg-red-100 text-red-700"
                    : "bg-yellow-100 text-yellow-700"
                }`}
              >
                {SEVERITY_LABEL[issue.severity]}
              </span>
              {issue.location && (
                <span className="text-xs text-gray-400">{issue.location}</span>
              )}
            </div>
            <p className="font-medium">
              &ldquo;{issue.text}&rdquo;
            </p>
            <p className="text-gray-600">{issue.reason}</p>
            <p className="text-xs text-gray-400">근거: {issue.law_ref}</p>
          </li>
        ))}
      </ul>
    </div>
  );
}
