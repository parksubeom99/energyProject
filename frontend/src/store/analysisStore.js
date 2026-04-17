/**
 * Zustand 상태 관리 — 클라이언트 상태
 *
 * Zustand = 클라이언트 상태 (인증, UI 상태, 분석 설정)
 * React Query = 서버 상태 (분석 결과, 이력 — 캐싱 + 재검증)
 *
 * 면접 포인트:
 * "병원 MSA와 동일하게 Zustand + React Query 조합을 사용했습니다.
 *  클라이언트 상태와 서버 상태를 분리하여 각각의 라이프사이클을 독립 관리합니다."
 */
import { create } from 'zustand';

const useAnalysisStore = create((set) => ({
  // ===== 인증 상태 =====
  isLoggedIn: !!localStorage.getItem('gp_access_token'),
  username: '',
  role: localStorage.getItem('gp_user_role') || '',

  setAuth: (username, role) =>
    set({ isLoggedIn: true, username, role }),

  clearAuth: () => {
    localStorage.removeItem('gp_access_token');
    localStorage.removeItem('gp_refresh_token');
    localStorage.removeItem('gp_user_role');
    set({ isLoggedIn: false, username: '', role: '' });
  },

  // ===== 분석 설정 =====
  region: 'KR',
  setRegion: (region) => set({ region }),

  // ===== 현재 분석 결과 (UI 표시용) =====
  currentResult: null,
  setCurrentResult: (result) => set({ currentResult: result }),

  // ===== 코드 입력 =====
  sourceCode: '',
  setSourceCode: (code) => set({ sourceCode: code }),

  // ===== 분석 진행 상태 =====
  isAnalyzing: false,
  setIsAnalyzing: (v) => set({ isAnalyzing: v }),
}));

export default useAnalysisStore;
