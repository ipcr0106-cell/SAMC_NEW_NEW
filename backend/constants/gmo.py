"""GMO 위험 원료 상수.

출처:
    - newsamc src/lib/judgment/m4-1/post-processing.ts
    - 계획/기능1_참고자료/06_초기시드_데이터.md §5

용도:
    기능1 내부 판정용 상수. 서류 필요 힌트 생성에 사용.
    라벨 문구 생성(기능5)은 세연 담당의 gmo_ingredients DB 테이블 사용.
"""

# GMO 고위험 원료 7종 (서류 필요)
GMO_HIGH_RISK: list[str] = [
    "대두",
    "옥수수",
    "카놀라",
    "면실",
    "사탕무",
    "알팔파",
    "파파야",
]

# GMO 중위험 원료 3종 (표시 검토)
GMO_MEDIUM_RISK: list[str] = [
    "감자",
    "사과",
    "연어",
]
