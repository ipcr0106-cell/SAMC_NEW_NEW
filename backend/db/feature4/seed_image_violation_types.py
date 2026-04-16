"""
기능4 이미지 위반 유형 시드 데이터 삽입 스크립트

26가지 초기 이미지 위반 유형을 f4_image_violation_types 테이블에 삽입합니다.
- source='seed', is_active=True (전문가가 검토·확정한 초기 목록)
- 이미 같은 type_name이 존재하면 스킵 (중복 방지)

실행:
  python seed_image_violation_types.py
"""

import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from supabase import create_client

load_dotenv(Path(__file__).parent.parent.parent / ".env")  # backend/.env 통합 사용

# =============================================================
# 시드 데이터 — 26가지 이미지 위반 유형
# =============================================================

SEED_TYPES = [
    {
        "type_name": "질병 치료·예방 암시",
        "sub_items": (
            "심장·간·혈관·뇌·신장·관절 등 특정 신체 부위의 치료·회복·개선을 나타내는 그림,"
            "질병명(암·당뇨·고혈압 등)과 함께 식품 이미지를 배치하여 치료 효과 암시,"
            "신체 비포/애프터 비교(복부·피부·혈관 등),"
            "X레이·MRI 이미지와 식품 조합"
        ),
        "default_severity": "must_fix",
        "severity_condition": "",
        "law_ref": "제2025-79호 제3조제1항제1호, 식품표시광고법 제8조제1항",
    },
    {
        "type_name": "의약품·의료기기 오인",
        "sub_items": (
            "주사기·수액백·알약·캡슐·정제·청진기·혈압계 등 의료 기구 이미지,"
            "흰 가운(백의) 입은 의사·약사·연구원 이미지,"
            "병원·약국·수술실·임상 환경을 연상케 하는 배경,"
            "처방전·의약품 포장 유사 디자인"
        ),
        "default_severity": "must_fix",
        "severity_condition": "",
        "law_ref": "제2025-79호 제3조제1항제2호",
    },
    {
        "type_name": "건강기능식품 마크 무단 사용",
        "sub_items": (
            "식약처 공식 건강기능식품 마크(파란 방패+사람 모양)를 허가 없이 사용,"
            "공식 마크와 유사한 색상·형태·문구의 자체 제작 마크,"
            "건강기능식품 문구와 유사 마크의 동시 사용으로 인증받은 것처럼 오인 유도"
        ),
        "default_severity": "must_fix",
        "severity_condition": "",
        "law_ref": "식품표시광고법 제10조, 건강기능식품법 제17조",
    },
    {
        "type_name": "효능·효과 과장 이미지",
        "sub_items": (
            "체중감량 비포/애프터(수치·사이즈 표시 포함),"
            "근육 성장 전후 비교,"
            "피부 개선·미백·주름 제거 전후 비교,"
            "N주 만에 ~kg 감량 등 수치 강조 그래프,"
            "경쟁 제품 대비 효능이 월등히 높음을 나타내는 막대그래프·파이차트"
        ),
        "default_severity": "review_needed",
        "severity_condition": "수치·비교 명시 시 must_fix",
        "law_ref": "제2025-79호 제3조제1항제4호",
    },
    {
        "type_name": "유기·친환경 인증 마크 무단 사용",
        "sub_items": (
            "국립농산물품질관리원 유기농 인증(녹색 잎사귀+글자) 마크 미허가 사용,"
            "USDA Organic 등 외국 유기 인증 마크를 국내 인증인 것처럼 오용,"
            "인증 없이 녹색 잎사귀·자연 심볼로 유기농 이미지 연상,"
            "무농약·자연산·천연 등 문구와 결합된 자연 이미지"
        ),
        "default_severity": "must_fix",
        "severity_condition": "",
        "law_ref": "식품표시광고법 제8조제2항, 친환경농어업법 제23조",
    },
    {
        "type_name": "원산지 오인 이미지",
        "sub_items": (
            "실제 원산지와 다른 국기·국가 지도·랜드마크(에펠탑·자유의여신상 등) 이미지,"
            "Made in ~ 표기와 다른 나라 이미지 혼용,"
            "외국 언어 포장 이미지로 수입품 오인,"
            "특정 지역 특산물처럼 보이게 하는 지역 상징 이미지"
        ),
        "default_severity": "must_fix",
        "severity_condition": "",
        "law_ref": "농수산물 원산지표시법 제5조, 제2025-79호 제3조제1항제3호",
    },
    {
        "type_name": "수상·인증·허가 마크 허위·오용",
        "sub_items": (
            "받지 않은 국내외 수상(대상·금상 등) 마크,"
            "FDA Approved 등 허위 외국 인증,"
            "ISO·GMP·HACCP 인증을 받지 않았거나 만료된 경우의 마크 사용,"
            "소비자 선정 등 임의 어워드 마크를 공인 인증처럼 표시,"
            "소고기·돼지고기 등 축산물 등급 마크(1++·1+·1·2등급 등)를 실제 판정 등급보다"
            " 높게 표시하거나 등급 판정을 받지 않은 제품에 사용,"
            "전통식품 품질인증(농림축산식품부 발급) 마크 미인증 제품에 사용,"
            "어린이 기호식품 품질인증(식약처 발급) 마크 미인증 제품에 사용"
        ),
        "default_severity": "must_fix",
        "severity_condition": "",
        "law_ref": (
            "제2025-79호 제3조제1항제3호, 식품표시광고법 제8조제1항,"
            "축산물위생관리법 제6조 (등급 표시), 전통식품산업의 육성 및 지원에 관한 법률 제22조"
        ),
    },
    {
        "type_name": "인체 내부 작용 과장 이미지",
        "sub_items": (
            "장내세균·프로바이오틱스 효과를 과장한 장(腸) 단면 이미지,"
            "DNA·세포·미토콘드리아 이미지로 유전자 수준 효과 암시,"
            "혈관 속 성분 흐름,"
            "뇌 활성화 이미지 등 과학적 효능 과장"
        ),
        "default_severity": "review_needed",
        "severity_condition": "",
        "law_ref": "제2025-79호 제3조제1항제4호",
    },
    {
        "type_name": "경쟁제품 비방·근거 없는 비교 이미지",
        "sub_items": (
            "경쟁사 제품을 열위로 표현하는 비교 이미지(색상·크기·형태로 암시 포함),"
            "타사 제품이라는 표기 없이 유사 패키지를 형편없이 묘사,"
            "근거 없이 업계 1위·유일한 제품 등을 나타내는 시각 요소"
        ),
        "default_severity": "must_fix",
        "severity_condition": "",
        "law_ref": "제2025-79호 제3조제1항제5호",
    },
    {
        "type_name": "어린이·취약계층 현혹 이미지",
        "sub_items": (
            "어린이 캐릭터·만화를 활용하여 건강 효능(키 성장·지능 향상 등) 과장,"
            "임산부·노인 이미지와 건강 효능을 연결하는 그림,"
            "건강 취약계층(환자·고령자)을 대상으로 한 치료 효과 암시 이미지"
        ),
        "default_severity": "review_needed",
        "severity_condition": "",
        "law_ref": "식품표시광고법 제8조제1항, 제2025-79호 제3조제1항",
    },
    {
        "type_name": "실제 제품·원재료와 상이한 이미지",
        "sub_items": (
            "실제 내용물과 다른 색상·형태·크기의 제품 이미지,"
            "원재료 비율과 다르게 고급 재료를 과도하게 강조한 이미지(딸기가 소량인데 딸기 가득),"
            "실제 식품과 다른 조리·완성 이미지로 기대치 오인 유도"
        ),
        "default_severity": "review_needed",
        "severity_condition": "명백한 허위 시 must_fix",
        "law_ref": "제2025-79호 제3조제1항제3호, 제2025-60호",
    },
    {
        "type_name": "영양성분·함량 과장 이미지",
        "sub_items": (
            "실제 함량과 달리 특정 영양소(비타민·미네랄·단백질 등)가 풍부한 것처럼 표현한 그래프,"
            "100배 더 많은 비타민C 등 근거 없는 수치 시각화,"
            "영양성분표 수치와 불일치하는 인포그래픽"
        ),
        "default_severity": "must_fix",
        "severity_condition": "",
        "law_ref": "제2025-79호 제3조제1항제4호, 제2025-60호 제5조",
    },
    {
        "type_name": "자연성·순수성 허위 이미지",
        "sub_items": (
            "합성 첨가물이 들어간 제품에 산·숲·계곡·들판 등 자연 배경 과도 사용으로 천연 오인,"
            "100% Natural 문구와 자연 이미지 결합으로 무첨가·천연 착각 유도,"
            "인공 색소·향료가 포함된 제품에 과일·채소 원물 이미지만 강조"
        ),
        "default_severity": "review_needed",
        "severity_condition": "",
        "law_ref": "제2025-79호 제3조제1항제3호",
    },
    {
        "type_name": "임상·과학 데이터 과장 이미지",
        "sub_items": (
            "실제 해당 제품을 대상으로 하지 않은 논문·임상 결과를 제품에 연결하는 이미지,"
            "논문 표지·의학저널·연구 그래프를 배경에 배치하여 임상 효과 과장,"
            "연구자 수·피험자 수·효과 수치를 왜곡·과장한 인포그래픽"
        ),
        "default_severity": "must_fix",
        "severity_condition": "",
        "law_ref": "제2025-79호 제3조제1항제4호",
    },
    {
        "type_name": "질병 진단·검진 장비 이미지",
        "sub_items": (
            "혈당측정기·체지방측정기·혈압계 이미지와 수치를 식품과 조합하여 진단 효과 암시,"
            "드시고 혈당을 재보세요 등 문구와 진단 기기 이미지 결합,"
            "정상 수치로 바뀌는 검사 결과지 이미지"
        ),
        "default_severity": "must_fix",
        "severity_condition": "",
        "law_ref": "제2025-79호 제3조제1항제1호 (질병 진단·치료 암시)",
    },
    {
        "type_name": "특정 연령층 타겟 과장 이미지 (어린이 외)",
        "sub_items": (
            "노인 대상 기억력·관절·심혈관 효과를 암시하는 이미지,"
            "임산부·수유부 대상 태아 발달·모유 성분 개선 효과 암시 이미지,"
            "청소년 대상 성장·집중력 향상 과장 이미지"
        ),
        "default_severity": "review_needed",
        "severity_condition": "",
        "law_ref": "제2025-79호 제3조제1항제1호·제4호",
    },
    {
        "type_name": "제조·가공 과정 허위 이미지",
        "sub_items": (
            "전통 수제·수작업 방식이 아닌데 장인이 직접 만드는 것처럼 표현,"
            "대규모 공장 생산이지만 소규모 전통 방식 이미지 사용,"
            "살균·방부 처리 과정을 무가공으로 오인하게 하는 이미지"
        ),
        "default_severity": "review_needed",
        "severity_condition": "",
        "law_ref": "제2025-79호 제3조제1항제3호 (소비자 기만)",
    },
    {
        "type_name": "국제·외국 기관 공인 허위 이미지",
        "sub_items": (
            "WHO·FAO 등 국제 기관 로고·마크를 허가 없이 사용,"
            "해외 유명 기관(Mayo Clinic·Harvard 등) 추천·인정 표시 허위 사용,"
            "외국어 공인 문구(Clinically Proven·Doctor Recommended)를 이미지로 강조"
        ),
        "default_severity": "must_fix",
        "severity_condition": "",
        "law_ref": "제2025-79호 제3조제1항제3호, 식품표시광고법 제8조제1항",
    },
    {
        "type_name": "체험담·후기 사진 허위 이미지",
        "sub_items": (
            "실제 소비자가 아닌 모델·배우 사진을 실제 사용 후 변화처럼 표현한 비포/애프터 이미지,"
            "OO님 후기라며 조작·연출된 체험 사진 삽입,"
            "제품 효과와 무관한 외모 개선 사진을 제품 사용 결과물로 암시,"
            "체중·피부·체형 변화를 과장하여 보여주는 편집 사진"
        ),
        "default_severity": "must_fix",
        "severity_condition": "",
        "law_ref": "제2025-79호 제3조제1항제4호, 식품표시광고법 제8조제1항 (허위·과장 광고)",
    },
    {
        "type_name": "포장 용량 과장 이미지",
        "sub_items": (
            "실제 내용량보다 포장재를 훨씬 크게 제작하여 많아 보이게 연출한 패키지 이미지,"
            "포장 내부 공간(과도한 에어 패키징)을 가득 찬 것처럼 라벨 이미지로 표현,"
            "동일 용량이지만 다른 제품보다 훨씬 커 보이도록 포장 비율을 왜곡한 이미지,"
            "묶음 제품을 낱개 수보다 많아 보이도록 배치한 제품 사진"
        ),
        "default_severity": "review_needed",
        "severity_condition": "명백한 불일치 시 must_fix",
        "law_ref": "제2025-79호 제3조제1항제3호, 식품표시광고법 제8조제1항 (소비자 기만)",
    },
    {
        "type_name": "알레르기 유발물질 오인·은폐 이미지",
        "sub_items": (
            "알레르기 유발물질(대두·밀·달걀·견과류 등)이 포함된 제품에 해당 원료가 없는 것처럼"
            " 묘사한 원재료 이미지(예: 견과류 無 아이콘·글루텐프리 심볼 허위 사용),"
            "알레르기 경고 문구가 시각적으로 강조된 이미지 요소에 가려지거나 묻혀 인식 불가,"
            "無○○ 표시와 함께 해당 성분이 없는 것처럼 오인하게 하는 그래픽 배치,"
            "이미지 디자인으로 법정 알레르기 표시 위치·색상 대비가 기준에 미달하여 식별 불가"
        ),
        "default_severity": "must_fix",
        "severity_condition": "",
        "law_ref": "식품표시광고법 제4조제1항, 제2025-60호 제6조 (알레르기 유발물질 표시 기준)",
    },
    {
        "type_name": "할랄·코셔 등 종교 인증 마크 허위 사용",
        "sub_items": (
            "이슬람 할랄 공인 인증 마크를 허가 없이 사용하거나 유사 문양으로 인증받은 것처럼 표시,"
            "유대교 코셔(Kosher / OU·KOF-K 등) 인증 마크 무단 사용,"
            "인증 없이 Halal-Friendly·돼지고기 無 이미지를 공식 종교 인증인 것처럼 오인 유도,"
            "인증 취소·만료된 마크를 계속 라벨에 유지"
        ),
        "default_severity": "must_fix",
        "severity_condition": "",
        "law_ref": "제2025-79호 제3조제1항제3호 (소비자 기만), 식품표시광고법 제8조제1항",
    },
    {
        "type_name": "유전자변형(GMO) 관련 허위 이미지",
        "sub_items": (
            "GMO 원재료가 함유된 제품에 Non-GMO·GMO-Free 배지·아이콘 허위 사용,"
            "유전자변형 표시 의무 원재료를 사용했음에도 자연·유기농 이미지만 강조하여 무함유 오인 유도,"
            "비GMO 인증을 받지 않았음에도 관련 심볼(나뭇잎+체크마크·씨앗 이미지 등) 사용,"
            "자연 그대로 등 문구와 자연 이미지 결합으로 GMO 미사용 착각 유도"
        ),
        "default_severity": "must_fix",
        "severity_condition": "",
        "law_ref": "식품위생법 제12조의2, 농림축산식품부 유전자변형식품 표시기준 제4조",
    },
    {
        "type_name": "기능성 인정 범위 초과 이미지",
        "sub_items": (
            "건강기능식품으로 허가받은 기능(예: 기억력 개선)을 넘어서는 효능을 이미지로 암시"
            " (예: 기억력 개선 허가 제품에 치매 예방·뇌 질환 치료 암시 그림),"
            "허가된 기능성 등급·문구 범위를 초과하는 효능 인포그래픽,"
            "허가받은 원료의 기능성 외 다른 효과를 이미지로 연상하게 하는 구성,"
            "기능성 허가 제품임을 표시했지만 실제 허가 내용과 다른 이미지로 소비자 오인 유도"
        ),
        "default_severity": "must_fix",
        "severity_condition": "",
        "law_ref": (
            "건강기능식품법 제18조,"
            "부당한 표시·광고로 보지 아니하는 기능성 표시·광고에 관한 규정"
            " (제2024-62호) 제3조 (허가 범위 내에서만 허용)"
        ),
    },
    {
        "type_name": "주류 라벨 음주 조장·미화 이미지",
        "sub_items": (
            "음주가 건강·체력·활력에 도움이 된다는 것을 암시하는 이미지,"
            "청소년이 음주하거나 즐거워하는 장면·캐릭터 사용,"
            "음주운전·과음을 미화하거나 문제없는 것처럼 표현한 이미지,"
            "주류임을 인식하기 어렵게 탄산음료·주스로 오인하게 하는 음료 이미지,"
            "알코올 도수나 음주 경고 문구를 시각적 요소로 가리거나 축소시키는 디자인"
        ),
        "default_severity": "must_fix",
        "severity_condition": "",
        "law_ref": (
            "국민건강증진법 제8조 (절주 조장 이미지 금지),"
            "청소년 보호법 제26조,"
            "식품표시광고법 제8조제1항"
        ),
    },
    {
        "type_name": "조제분유·영유아식품 모유 대체 오인 이미지",
        "sub_items": (
            "조제분유·조제식(영아용·성장기용)이 모유와 동등하거나 우월하다고 암시하는 이미지,"
            "수유 중인 모습이나 아기의 건강·성장을 분유와 직접 연결하는 그림,"
            "모유수유를 불편하거나 열등한 것처럼 표현하는 이미지,"
            "특수의료용도식품(환자식·고령친화식품 등)이 일반 식품과 같이 자유롭게 섭취 가능한"
            " 것처럼 오인하게 하는 이미지 (의사 상담 없이 사용 가능한 것처럼 암시)"
        ),
        "default_severity": "must_fix",
        "severity_condition": "",
        "law_ref": (
            "모유대체식품의 판매촉진 등의 규제에 관한 법률 제4조,"
            "식품의 기준 및 규격 (영유아식 표시기준),"
            "식품표시광고법 제8조제1항"
        ),
    },
]


# =============================================================
# 삽입 로직
# =============================================================

def seed(supabase) -> dict:
    inserted = 0
    skipped  = 0

    for item in SEED_TYPES:
        # 중복 확인
        existing = (
            supabase.table("f4_image_violation_types")
            .select("id")
            .eq("type_name", item["type_name"])
            .execute()
        )
        if existing.data:
            print(f"  [스킵] 이미 존재: {item['type_name']}")
            skipped += 1
            continue

        supabase.table("f4_image_violation_types").insert({
            **item,
            "source":      "seed",
            "is_active":   True,
            "review_note": "전문가 검토 완료 — 초기 시드 데이터",
        }).execute()
        print(f"  [삽입] {item['type_name']}")
        inserted += 1

    return {"inserted": inserted, "skipped": skipped}


def main():
    supabase_url = os.getenv("SUPABASE_URL")
    supabase_key = os.getenv("SUPABASE_SERVICE_KEY")
    if not supabase_url or not supabase_key:
        print("오류: SUPABASE_URL 또는 SUPABASE_SERVICE_KEY 환경변수가 설정되지 않았습니다.")
        sys.exit(1)

    supabase = create_client(supabase_url, supabase_key)

    print(f"이미지 위반 유형 시드 삽입 시작 ({len(SEED_TYPES)}개)...")
    result = seed(supabase)
    print(
        f"\n완료 — 삽입: {result['inserted']}개 | 스킵(이미 존재): {result['skipped']}개"
    )


if __name__ == "__main__":
    main()
