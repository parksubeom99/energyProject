/**
 * GreenPulse API 클라이언트 — JWT 인증 + API 호출
 *
 * 모든 API 호출은 이 모듈을 통해 이루어진다.
 * JWT 토큰은 localStorage에 저장하고, 만료 시 자동 갱신(RTR).
 *
 * 엔드포인트:
 * - POST /auth/token     → login()
 * - POST /auth/refresh   → refreshToken()
 * - POST /analyze/sync   → analyzeCode()
 * - POST /analyze        → analyzeAsync()
 * - GET  /analyze/{id}   → getAnalysis()
 * - GET  /history        → getHistory()
 */

const API_BASE = '/api';

// ================================================================
// 토큰 관리
// ================================================================
export function getAccessToken() {
  return localStorage.getItem('gp_access_token');
}

export function getRefreshTokenValue() {
  return localStorage.getItem('gp_refresh_token');
}

function saveTokens(accessToken, refreshToken) {
  localStorage.setItem('gp_access_token', accessToken);
  localStorage.setItem('gp_refresh_token', refreshToken);
}

export function clearTokens() {
  localStorage.removeItem('gp_access_token');
  localStorage.removeItem('gp_refresh_token');
  localStorage.removeItem('gp_user_role');
}

// ================================================================
// 인증된 fetch — JWT 헤더 자동 추가
// ================================================================
async function authFetch(url, options = {}) {
  const token = getAccessToken();
  const headers = {
    'Content-Type': 'application/json',
    ...options.headers,
  };
  if (token) {
    headers['Authorization'] = `Bearer ${token}`;
  }

  const resp = await fetch(`${API_BASE}${url}`, { ...options, headers });

  // 401 → 토큰 갱신 시도
  if (resp.status === 401) {
    const refreshed = await refreshToken();
    if (refreshed) {
      headers['Authorization'] = `Bearer ${getAccessToken()}`;
      return fetch(`${API_BASE}${url}`, { ...options, headers });
    }
  }

  return resp;
}

// ================================================================
// 인증 API
// ================================================================
export async function login(username, password) {
  const resp = await fetch(`${API_BASE}/auth/token`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ username, password }),
  });

  if (!resp.ok) {
    const err = await resp.json();
    throw new Error(err.detail || '로그인 실패');
  }

  const data = await resp.json();
  saveTokens(data.access_token, data.refresh_token);
  localStorage.setItem('gp_user_role', data.role);
  return data;
}

export async function refreshToken() {
  const token = getRefreshTokenValue();
  if (!token) return false;

  try {
    const resp = await fetch(`${API_BASE}/auth/refresh`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ refresh_token: token }),
    });

    if (!resp.ok) return false;

    const data = await resp.json();
    saveTokens(data.access_token, data.refresh_token);
    return true;
  } catch {
    return false;
  }
}

// ================================================================
// 분석 API
// ================================================================
/** 동기 분석 — 즉시 결과 반환 */
export async function analyzeCode(sourceCode, region = 'KR') {
  const resp = await authFetch('/analyze/sync', {
    method: 'POST',
    body: JSON.stringify({ source_code: sourceCode, region }),
  });

  if (!resp.ok) {
    const err = await resp.json();
    throw new Error(err.detail?.error || err.detail || '분석 실패');
  }

  return resp.json();
}

/** 비동기 분석 — 202 즉시 반환 + 폴링 */
export async function analyzeAsync(sourceCode, region = 'KR') {
  const resp = await authFetch('/analyze', {
    method: 'POST',
    body: JSON.stringify({ source_code: sourceCode, region }),
  });

  if (!resp.ok) {
    const err = await resp.json();
    throw new Error(err.detail?.error || err.detail || '분석 요청 실패');
  }

  return resp.json();
}

/** 분석 결과 조회 (폴링) */
export async function getAnalysis(analysisId) {
  const resp = await authFetch(`/analyze/${analysisId}`);
  if (!resp.ok) throw new Error('결과 조회 실패');
  return resp.json();
}

/** 분석 이력 */
export async function getHistory() {
  const resp = await authFetch('/history');
  if (!resp.ok) throw new Error('이력 조회 실패');
  return resp.json();
}
