# E2E 픽스처 문서

E-01 시나리오에 사용되는 샘플 문서 4종.

| 파일명 | 용도 | 형식 |
|--------|------|------|
| `sample_ingredient_spec.pdf` | 원재료 명세서 (F0 OCR 대상) | PDF |
| `sample_analysis_report.pdf` | 성분 분석표 (F0 OCR 대상) | PDF |
| `sample_label.jpg` | 라벨 이미지 (F4 라벨 검토용) | JPG |
| `sample_certificate.pdf` | 위생 증명서 (F0 OCR 대상) | PDF |

## 실제 파일 준비

실 E2E 실행 전 아래 중 하나를 선택:

1. **실제 문서 사용**: 테스트용 무해한 원재료(예: 쌀, 우유) 함유 문서를 이 디렉토리에 배치
2. **mock API 경로**: `E2E_MOCK_API=1` 환경변수 설정 시 서버가 OCR을 모킹하여 F0 픽스처를 직접 주입

## 주의

- 이 디렉토리의 파일은 git에 커밋하지 않음 (`.gitignore` 등록 권장)
- 실제 제품 문서를 사용할 경우 개인정보/영업비밀 포함 여부 확인
