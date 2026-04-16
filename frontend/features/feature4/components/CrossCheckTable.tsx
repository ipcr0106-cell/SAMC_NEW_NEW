/**
 * 기능4: 서류-라벨 내용 교차 검증 테이블
 */

import type { CrossCheckItem } from "@/types/pipeline";
import { CROSS_CHECK_FIELD_LABEL } from "../types";

interface CrossCheckTableProps {
  crossCheck: CrossCheckItem[];
  isConfirmed: boolean;
}

export default function CrossCheckTable({
  crossCheck,
  isConfirmed,
}: CrossCheckTableProps) {
  return (
    <div className="space-y-2">
      <h3 className="text-sm font-semibold text-gray-700">서류-라벨 내용 교차 검증</h3>
      <table className="w-full text-sm border-collapse">
        <thead>
          <tr className="bg-gray-50 text-gray-600 text-left">
            <th className="border px-3 py-2 font-medium">항목</th>
            <th className="border px-3 py-2 font-medium">라벨 표기</th>
            <th className="border px-3 py-2 font-medium">제출 서류</th>
            <th className="border px-3 py-2 font-medium">일치</th>
          </tr>
        </thead>
        <tbody>
          {crossCheck.map((item) => (
            <tr
              key={item.field}
              className={item.match ? "" : "bg-red-50"}
            >
              <td className="border px-3 py-2 font-medium text-gray-700">
                {CROSS_CHECK_FIELD_LABEL[item.field]}
              </td>
              <td className="border px-3 py-2 text-gray-600">{item.label_value}</td>
              <td className="border px-3 py-2 text-gray-600">{item.doc_value}</td>
              <td className="border px-3 py-2 text-center">
                {item.match ? (
                  <span className="text-green-600 font-bold">✓</span>
                ) : (
                  <span className="text-red-600 font-bold">✗</span>
                )}
                {item.note && (
                  <span className="ml-1 text-xs text-gray-400">({item.note})</span>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
