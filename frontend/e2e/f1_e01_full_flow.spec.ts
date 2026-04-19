/**
 * E-01: F1 전체 플로우 E2E 스모크 테스트
 *
 * 시나리오 (05번 HITL 플로우 §E-01):
 *   문서 4종 업로드
 *   → F0 파싱 (OCR)
 *   → HITL-0 승인
 *   → F2 자동 실행 (식품유형 분류)
 *   → F1 실행 (Step A/B/C/D)
 *   → HITL-1 불확실 원재료 검토
 *   → HITL-2 최종 판정 확정
 *   → 결과 PDF 다운로드
 *
 * 실행:
 *   npx playwright test e2e/f1_e01_full_flow.spec.ts
 *
 * 환경변수:
 *   E2E_BASE_URL      기본: http://localhost:3000
 *   E2E_MOCK_API=1    data.go.kr 실 API 대신 mock 사용
 *   E2E_USER_EMAIL    테스트 계정 이메일
 *   E2E_USER_PASSWORD 테스트 계정 비밀번호
 *
 * 픽스처 문서 (frontend/e2e/fixtures/):
 *   sample_ingredient_spec.pdf   — 원재료 명세서
 *   sample_analysis_report.pdf   — 성분 분석표
 *   sample_label.jpg             — 라벨 이미지
 *   sample_certificate.pdf       — 위생 증명서
 *
 * 주의:
 *   - 실제 OCR·API 환경 없이는 F0 파싱 이후 단계가 실패할 수 있습니다.
 *   - E2E_MOCK_API=1 설정 시 API mock 미들웨어가 활성화됩니다 (서버 설정 필요).
 *   - 스켈레톤 단계: 각 step의 page 선택자는 실제 컴포넌트 구현 후 확정합니다.
 */

import { test, expect, Page } from "@playwright/test";
import path from "path";

// ──────────────────────────────────────────────────────────────────
// 상수
// ──────────────────────────────────────────────────────────────────

const BASE_URL = process.env.E2E_BASE_URL ?? "http://localhost:3000";
const USE_MOCK = process.env.E2E_MOCK_API === "1";

const FIXTURES_DIR = path.join(__dirname, "fixtures");

const SAMPLE_DOCS = [
  path.join(FIXTURES_DIR, "sample_ingredient_spec.pdf"),
  path.join(FIXTURES_DIR, "sample_analysis_report.pdf"),
  path.join(FIXTURES_DIR, "sample_label.jpg"),
  path.join(FIXTURES_DIR, "sample_certificate.pdf"),
];

// 각 단계 최대 대기 시간 (ms)
const TIMEOUT = {
  upload: 30_000,
  ocr: 120_000,   // OCR은 오래 걸릴 수 있음
  f1_run: 90_000,
  hitl: 30_000,
  pdf: 30_000,
};

// ──────────────────────────────────────────────────────────────────
// 헬퍼
// ──────────────────────────────────────────────────────────────────

async function login(page: Page): Promise<void> {
  const email = process.env.E2E_USER_EMAIL ?? "test@samc.kr";
  const password = process.env.E2E_USER_PASSWORD ?? "test-password";

  await page.goto(`${BASE_URL}/login`);
  await page.fill('[data-testid="email-input"]', email);
  await page.fill('[data-testid="password-input"]', password);
  await page.click('[data-testid="login-submit"]');
  await page.waitForURL(`${BASE_URL}/cases**`, { timeout: 10_000 });
}

async function createNewCase(page: Page): Promise<string> {
  await page.click('[data-testid="new-case-btn"]');
  await page.waitForURL(`${BASE_URL}/cases/*/upload**`, { timeout: 10_000 });
  // URL에서 case_id 추출
  const url = page.url();
  const match = url.match(/\/cases\/([^/]+)\//);
  return match?.[1] ?? "";
}

// ──────────────────────────────────────────────────────────────────
// 메인 테스트 스위트
// ──────────────────────────────────────────────────────────────────

test.describe("E-01: F1 전체 플로우 스모크", () => {
  test.setTimeout(10 * 60 * 1000); // 10분 전체 타임아웃

  let caseId: string;

  // ── Step 1: 로그인 ──────────────────────────────────────────────
  test("1-1. 로그인 성공", async ({ page }) => {
    await login(page);
    await expect(page).toHaveURL(/\/cases/);
  });

  // ── Step 2: 문서 4종 업로드 ────────────────────────────────────
  test("2-1. 케이스 생성 및 문서 업로드", async ({ page }) => {
    await login(page);
    caseId = await createNewCase(page);
    expect(caseId).not.toBe("");

    // 파일 업로드 input
    const fileInput = page.locator('[data-testid="file-upload-input"]');
    await fileInput.setInputFiles(SAMPLE_DOCS);

    // 업로드 진행 표시 대기
    await expect(
      page.locator('[data-testid="upload-progress"]')
    ).toBeVisible({ timeout: TIMEOUT.upload });

    // 업로드 완료 확인
    await expect(
      page.locator('[data-testid="upload-complete-badge"]')
    ).toBeVisible({ timeout: TIMEOUT.upload });

    // 4개 파일이 모두 업로드됨을 확인
    const uploadedFiles = page.locator('[data-testid="uploaded-file-item"]');
    await expect(uploadedFiles).toHaveCount(4, { timeout: TIMEOUT.upload });
  });

  // ── Step 3: F0 파싱 (OCR) ──────────────────────────────────────
  test("3-1. F0 파싱 실행 및 완료 대기", async ({ page }) => {
    await login(page);
    await page.goto(`${BASE_URL}/cases/${caseId}/pipeline`);

    // F0 파싱 시작 버튼 클릭
    const parseBtn = page.locator('[data-testid="f0-parse-btn"]');
    if (await parseBtn.isVisible()) {
      await parseBtn.click();
    }

    // F0 완료 상태 대기
    await expect(
      page.locator('[data-testid="f0-status-badge"][data-status="completed"]')
    ).toBeVisible({ timeout: TIMEOUT.ocr });

    // 원재료 목록 표시 확인
    await expect(
      page.locator('[data-testid="f0-ingredient-list"]')
    ).toBeVisible();
  });

  // ── Step 4: HITL-0 승인 ────────────────────────────────────────
  test("4-1. HITL-0: F0 결과 확인 및 승인", async ({ page }) => {
    await login(page);
    await page.goto(`${BASE_URL}/cases/${caseId}/pipeline/hitl0`);

    // F0ApprovalPanel 표시 확인
    await expect(
      page.locator('[data-testid="f0-approval-panel"]')
    ).toBeVisible({ timeout: TIMEOUT.hitl });

    // 기본정보 섹션 확인
    await expect(
      page.locator('[data-testid="f0-product-name"]')
    ).toBeVisible();

    // 원재료 목록 섹션 확인
    await expect(
      page.locator('[data-testid="f0-ingredient-table"]')
    ).toBeVisible();

    // 승인 버튼 클릭
    await page.click('[data-testid="f0-approve-btn"]');

    // 승인 확인 모달
    await page.click('[data-testid="confirm-approve-btn"]');

    // 승인 상태 확인
    await expect(
      page.locator('[data-testid="f0-status-badge"][data-status="approved"]')
    ).toBeVisible({ timeout: TIMEOUT.hitl });
  });

  // ── Step 5: F2 자동 실행 ───────────────────────────────────────
  test("5-1. F2 식품유형 분류 자동 실행", async ({ page }) => {
    await login(page);
    await page.goto(`${BASE_URL}/cases/${caseId}/pipeline`);

    // F2 실행 대기 (F0 승인 후 자동 실행)
    await expect(
      page.locator('[data-testid="f2-status-badge"][data-status="completed"]')
    ).toBeVisible({ timeout: 60_000 });

    // 식품유형 확정 결과 표시 확인
    await expect(
      page.locator('[data-testid="f2-food-type-result"]')
    ).toBeVisible();
  });

  // ── Step 6: F1 실행 ────────────────────────────────────────────
  test("6-1. F1 수입판정 실행", async ({ page }) => {
    await login(page);
    await page.goto(`${BASE_URL}/cases/${caseId}/pipeline`);

    // F1 실행 버튼 (수동 또는 자동)
    const f1RunBtn = page.locator('[data-testid="f1-run-btn"]');
    if (await f1RunBtn.isVisible()) {
      await f1RunBtn.click();
    }

    // F1 실행 중 스피너 확인
    await expect(
      page.locator('[data-testid="f1-running-spinner"]')
    ).toBeVisible({ timeout: 10_000 });

    // F1 완료 대기
    await expect(
      page.locator('[data-testid="f1-status-badge"]').filter({
        hasText: /completed|waiting_review/i,
      })
    ).toBeVisible({ timeout: TIMEOUT.f1_run });
  });

  test("6-2. F1 Step A/B/C/D 결과 패널 표시", async ({ page }) => {
    await login(page);
    await page.goto(`${BASE_URL}/cases/${caseId}/pipeline/f1`);

    // Step A 금지원료 결과
    await expect(
      page.locator('[data-testid="step-a-result-panel"]')
    ).toBeVisible({ timeout: TIMEOUT.hitl });

    // Step B 원재료 판정 결과
    await expect(
      page.locator('[data-testid="step-b-result-panel"]')
    ).toBeVisible();

    // Step D 법령 인용 패널
    await expect(
      page.locator('[data-testid="step-d-law-citations"]')
    ).toBeVisible();
  });

  // ── Step 7: HITL-1 불확실 원재료 검토 ─────────────────────────
  test("7-1. HITL-1: 불확실 원재료 검토 패널 표시", async ({ page }) => {
    await login(page);
    await page.goto(`${BASE_URL}/cases/${caseId}/pipeline/hitl1`);

    // HITL-1 트리거 여부 확인 (unidentified 또는 restricted 있는 경우)
    const hitl1Panel = page.locator('[data-testid="hitl1-panel"]');

    if (await hitl1Panel.isVisible({ timeout: 5_000 }).catch(() => false)) {
      // 미확인 원재료 섹션
      const unidentifiedSection = page.locator(
        '[data-testid="unidentified-ingredient-review"]'
      );

      if (
        await unidentifiedSection
          .isVisible({ timeout: 3_000 })
          .catch(() => false)
      ) {
        // 첫 번째 미확인 원재료에 대해 허용 결정
        await page
          .locator('[data-testid="hitl1-decision-allow"]')
          .first()
          .click();
      }

      // HITL-1 제출
      const submitBtn = page.locator('[data-testid="hitl1-submit-btn"]');
      if (await submitBtn.isEnabled()) {
        await submitBtn.click();
      }

      // 제출 완료 확인
      await expect(
        page.locator('[data-testid="hitl1-submitted-badge"]')
      ).toBeVisible({ timeout: TIMEOUT.hitl });
    } else {
      // HITL-1 불필요 케이스 (모두 판정 완료)
      test.info().annotations.push({
        type: "info",
        description: "HITL-1 패널 없음 — 모든 원재료 자동 판정 완료",
      });
    }
  });

  // ── Step 8: HITL-2 최종 판정 확정 ─────────────────────────────
  test("8-1. HITL-2: 최종 판정 패널 표시 및 확정", async ({ page }) => {
    await login(page);
    await page.goto(`${BASE_URL}/cases/${caseId}/pipeline/hitl2`);

    // VerdictPanel 표시 확인
    await expect(
      page.locator('[data-testid="verdict-panel"]')
    ).toBeVisible({ timeout: TIMEOUT.hitl });

    // AI 추천 판정 표시 확인
    await expect(
      page.locator('[data-testid="ai-recommended-verdict"]')
    ).toBeVisible();

    // 법령 인용 체크박스 확인 (LawRefCheckbox)
    await expect(
      page.locator('[data-testid="law-ref-checkbox-list"]')
    ).toBeVisible();

    // 최종 판정 확정 버튼 클릭
    await page.click('[data-testid="hitl2-confirm-btn"]');

    // 확정 확인 모달
    await page.click('[data-testid="confirm-verdict-btn"]');

    // 확정 상태 확인 — Wave 3: 'confirmed' 또는 'locked' 모두 허용
    // (code-review HIGH-1: unlock 정책이 Wave 4 에서 확정될 때까지 두 값 공존)
    const badge = page.locator('[data-testid="f1-status-badge"]');
    await expect(badge).toBeVisible({ timeout: TIMEOUT.hitl });
    const status = await badge.getAttribute("data-status");
    expect(["confirmed", "locked"]).toContain(status);
  });

  test("8-2. HITL-2 확정 후 수정 시도 → 잠금 안내 표시", async ({ page }) => {
    await login(page);
    await page.goto(`${BASE_URL}/cases/${caseId}/pipeline/hitl2`);

    // 확정 후 편집 버튼이 비활성화되거나 잠금 안내가 표시되어야 함
    const lockedBanner = page.locator('[data-testid="locked-banner"]');
    const editDisabled = page.locator(
      '[data-testid="hitl2-confirm-btn"][disabled]'
    );

    const isLocked =
      (await lockedBanner.isVisible().catch(() => false)) ||
      (await editDisabled.isVisible().catch(() => false));

    expect(isLocked).toBe(true);
  });

  // ── Step 9: 결과 PDF 다운로드 ──────────────────────────────────
  test("9-1. 결과 PDF 다운로드", async ({ page }) => {
    await login(page);
    await page.goto(`${BASE_URL}/cases/${caseId}/result`);

    // PDF 다운로드 버튼 표시 확인
    await expect(
      page.locator('[data-testid="download-pdf-btn"]')
    ).toBeVisible({ timeout: TIMEOUT.pdf });

    // 다운로드 이벤트 캡처
    const [download] = await Promise.all([
      page.waitForEvent("download", { timeout: TIMEOUT.pdf }),
      page.click('[data-testid="download-pdf-btn"]'),
    ]);

    // 파일명 확인
    const filename = download.suggestedFilename();
    expect(filename).toMatch(/\.pdf$/i);

    // 파일 크기 확인 (최소 1KB)
    const stream = await download.createReadStream();
    let size = 0;
    for await (const chunk of stream) {
      size += chunk.length;
    }
    expect(size).toBeGreaterThan(1024);
  });
});

// ──────────────────────────────────────────────────────────────────
// 보조 테스트: E-02, E-03 스텁 (골격만)
// ──────────────────────────────────────────────────────────────────

test.describe("E-02: HITL-0 편집 후 재승인 (스텁)", () => {
  test("2-1. F0 결과 편집 → 재승인 필요 상태 확인", async ({ page }) => {
    // TODO: Wave 3 W3-FE F0ApprovalPanel 구현 완료 후 실 시나리오 작성
    test.skip(true, "W3-FE F0ApprovalPanel 구현 후 활성화");
  });
});

test.describe("E-03: HITL-2 확정 후 수정 시도 → 잠금 (스텁)", () => {
  test("3-1. 잠금 상태에서 재편집 시도 → 403 또는 잠금 UI", async ({
    page,
  }) => {
    // TODO: Wave 3 W3-BE locked 상태 엔드포인트 구현 후 활성화
    test.skip(true, "W3-BE locked 엔드포인트 구현 후 활성화");
  });
});
