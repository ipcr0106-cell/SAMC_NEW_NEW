"""
SAMC 수입식품 검역 AI 플랫폼 — FastAPI 메인 진입점

실행:
    cd backend && uvicorn main:app --reload --port 8000
"""

from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

load_dotenv(Path(__file__).parent / ".env")

from routers.upload import router as upload_router
from routers.cases import router as cases_router
from routers.feature4 import router as feature4_router
from routers.admin_laws import router as admin_laws_router
from routers.admin_law_update import router as admin_law_update_router
from routers.feature1 import router as feature1_router
from routers.db_manager import router as db_manager_router
from routers.feature2 import router as feature2_router
from routers.feature3 import router as feature3_router
from routers.feature5 import router as feature5_router
from routers.dummy_seed import router as dummy_seed_router
from middleware.error_handler import register_error_handlers


app = FastAPI(
    title="SAMC 수입식품 검역 AI",
    description="수입식품 검역 자동화 파이프라인 API",
    version="0.1.0",
)

# CORS — 프론트엔드(localhost:3000, Vercel 배포 URL) 허용
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# F1 파이프라인 에러 핸들러 등록 (08_에러_처리_설계.md §4)
register_error_handlers(app)

# 라우터 등록
app.include_router(upload_router)
app.include_router(cases_router)
app.include_router(feature4_router)         # F4: 수출국 표시사항 검토
app.include_router(admin_laws_router)       # F4: 법령 관리 어드민
app.include_router(admin_law_update_router) # 통합 법령 업데이트
app.include_router(feature1_router)         # F1: 수입 가능 판정
app.include_router(db_manager_router)       # F1: DB 관리 CRUD
app.include_router(feature2_router, prefix="/api/v1")   # F2: 식품유형 분류
app.include_router(feature3_router, prefix="/api/v1")   # F3: 수입 필요서류 안내
app.include_router(feature5_router, prefix="/api/v1")   # F5: 한글표시사항 시안
app.include_router(dummy_seed_router, prefix="/api/v1") # DEV: 더미 데이터 시드


@app.get("/health", tags=["system"])
async def health_check():
    return {"status": "ok", "service": "samc-backend"}
