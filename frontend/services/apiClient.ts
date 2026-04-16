/**
 * 공통 API 클라이언트
 * ──────────────────────────────
 * 이 파일은 공통 파일입니다. 수정 시 전원 합의 필수.
 * 각 기능의 API 함수는 이 클라이언트를 import해서 사용하세요.
 */

import axios from "axios";

const BASE_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000/api/v1";

export const apiClient = axios.create({
  baseURL: BASE_URL,
  timeout: 60000,  // SSE 스트림 외 일반 요청 60초 타임아웃
});

// 요청 인터셉터: Supabase JWT 토큰 자동 첨부
apiClient.interceptors.request.use((config) => {
  if (typeof window !== "undefined") {
    const token = localStorage.getItem("supabase_token");
    if (token) {
      config.headers["Authorization"] = `Bearer ${token}`;
    }
  }
  return config;
});

// 응답 인터셉터: 공통 에러 처리
apiClient.interceptors.response.use(
  (response) => response,
  (error) => {
    // 401: 세션 만료 → 로그인 페이지로
    if (error.response?.status === 401 && typeof window !== "undefined") {
      window.location.href = "/auth/login";
    }
    return Promise.reject(error);
  }
);
