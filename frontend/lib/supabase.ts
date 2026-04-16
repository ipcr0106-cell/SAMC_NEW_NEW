import { createClient, SupabaseClient } from "@supabase/supabase-js";

const supabaseUrl = process.env.NEXT_PUBLIC_SUPABASE_URL || "";
const supabaseAnonKey = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY || "";

// Supabase 키가 미설정이면 더미 클라이언트 생성 방지
let supabase: SupabaseClient;

if (supabaseUrl && supabaseAnonKey && supabaseUrl.startsWith("http")) {
  supabase = createClient(supabaseUrl, supabaseAnonKey);
} else {
  // 개발 중 키 미설정 시 — createClient에 placeholder URL 전달
  // 실제 auth 호출 시 에러가 나지만 페이지 렌더링은 가능
  supabase = createClient(
    "https://placeholder.supabase.co",
    "placeholder-key"
  );
  if (typeof window !== "undefined") {
    console.warn(
      "[SAMC] NEXT_PUBLIC_SUPABASE_URL 또는 NEXT_PUBLIC_SUPABASE_ANON_KEY가 설정되지 않았습니다. .env.local 파일을 확인하세요."
    );
  }
}

export { supabase };
