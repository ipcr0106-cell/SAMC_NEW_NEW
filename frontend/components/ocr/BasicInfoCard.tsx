"use client";

import { Package } from "lucide-react";
import Card from "@/components/ui/Card";
import Input from "@/components/ui/Input";
import Toggle from "@/components/ui/Toggle";

interface BasicInfo {
  productName: string;
  isFirstImport: boolean;
  isOrganic: boolean;
}

interface BasicInfoCardProps {
  data: BasicInfo;
  onChange: (data: BasicInfo) => void;
}

export default function BasicInfoCard({ data, onChange }: BasicInfoCardProps) {
  return (
    <Card>
      <div className="flex items-center gap-2.5 mb-5">
        <div className="flex items-center justify-center w-8 h-8 rounded-lg bg-purple-50 text-purple-600">
          <Package size={16} />
        </div>
        <h3 className="text-sm font-bold text-slate-900">기본 정보</h3>
      </div>

      <div className="space-y-4">
        <Input
          label="제품명"
          value={data.productName}
          onChange={(e) =>
            onChange({ ...data, productName: e.target.value })
          }
          placeholder="예: FJ 캡 프론티어 위스키"
        />

        <div className="grid grid-cols-2 gap-4 pt-1">
          <Toggle
            label="최초 수입 여부"
            description="이전 수입 이력 없는 신규 제품"
            checked={data.isFirstImport}
            onChange={(checked) =>
              onChange({ ...data, isFirstImport: checked })
            }
          />
          <Toggle
            label="유기인증 여부"
            description="유기농·친환경 인증 보유 제품"
            checked={data.isOrganic}
            onChange={(checked) =>
              onChange({ ...data, isOrganic: checked })
            }
          />
        </div>
      </div>
    </Card>
  );
}
