"""
F3 법령 자동 업데이트 전처리 패키지.

검역관 UI 에서 법령 파일 업로드 시,
  1. dispatcher.run_f3_preprocess(law_name, file_path) — 파싱만, DB 건드리지 않음 (Preview)
  2. snapshot.apply_with_snapshot(...) — 검역관 확정 시 백업 + 교체
  3. snapshot.rollback(version) — 이전 상태 복원

법령별 파서는 각 submodule 에 격리:
  - excel_required_docs — Excel 수입신고 구비서류 목록
  - rule_pdf            — 시행규칙 PDF
  - guide_pdf           — OEM + 동등성인정 PDF
  - foodcode_hwpx       — 식품공전 / 식품첨가물공전 HWPX
"""
