/**
 * GreenPulse 메인 앱 — 로그인 + 분석 대시보드
 *
 * 레이아웃:
 * ┌──────────────────────────────────────────────┐
 * │  헤더 (로고 + 사용자 정보 + 로그아웃)           │
 * ├──────────────────────────────────────────────┤
 * │  코드 입력 영역 (textarea + 분석 버튼)          │
 * ├───────────────┬──────────────────────────────┤
 * │  ScoreGauge   │  AxisBreakdown               │
 * │  (SCI 게이지)  │  (3축 상세)                   │
 * ├───────────────┴──────────────────────────────┤
 * │  CodeDiff (Before/After 코드 비교)             │
 * ├──────────────────────────────────────────────┤
 * │  TrendChart (분석 이력 트렌드)                  │
 * └──────────────────────────────────────────────┘
 */
import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import useAnalysisStore from './store/analysisStore';
import { login as apiLogin, analyzeCode, getHistory } from './api/client';
import ScoreGauge from './components/ScoreGauge';
import AxisBreakdown from './components/AxisBreakdown';
import CodeDiff from './components/CodeDiff';
import TrendChart from './components/TrendChart';

// 샘플 bad 코드 — 기본값
const SAMPLE_BAD = `import sqlite3
import requests

def find_duplicates(items: list) -> list:
    duplicates = []
    for i in range(len(items)):
        for j in range(i + 1, len(items)):
            if items[i] == items[j]:
                if items[i] not in duplicates:
                    duplicates.append(items[i])
    return duplicates

def get_user_orders(user_ids: list) -> dict:
    conn = sqlite3.connect("shop.db")
    cursor = conn.cursor()
    result = {}
    for user_id in user_ids:
        cursor.execute("SELECT * FROM orders WHERE user_id = ?", (user_id,))
        orders = cursor.fetchall()
    conn.close()
    return result

def generate_summary(text: str) -> str:
    response = requests.post(
        "https://api.anthropic.com/v1/messages",
        json={"model": "claude-sonnet-4-20250514", "messages": [{"role": "user", "content": text}]},
    )
    return response.json()`;

export default function App() {
  const {
    isLoggedIn, username, role,
    setAuth, clearAuth,
    sourceCode, setSourceCode,
    currentResult, setCurrentResult,
    region, setRegion,
    isAnalyzing, setIsAnalyzing,
  } = useAnalysisStore();

  const [loginForm, setLoginForm] = useState({ username: 'admin', password: 'greenpulse' });
  const [error, setError] = useState('');

  // 덩어리 2 보완: 월간 실행 횟수 — 1회·월·년 3단 스케일 환산용 (프론트 곱셈)
  const [monthlyExecutions, setMonthlyExecutions] = useState(1_000_000);

  // 분석 이력 (React Query — 서버 상태)
  const { data: history = [] } = useQuery({
    queryKey: ['history'],
    queryFn: getHistory,
    enabled: isLoggedIn,
    refetchInterval: 10_000,
  });

  // ===== 로그인 =====
  const handleLogin = async (e) => {
    e.preventDefault();
    setError('');
    try {
      const data = await apiLogin(loginForm.username, loginForm.password);
      setAuth(loginForm.username, data.role);
    } catch (err) {
      setError(err.message);
    }
  };

  // ===== 분석 실행 =====
  const handleAnalyze = async () => {
    if (!sourceCode.trim()) return;
    setIsAnalyzing(true);
    setError('');
    try {
      const result = await analyzeCode(sourceCode, region);
      setCurrentResult(result);
    } catch (err) {
      setError(err.message);
    } finally {
      setIsAnalyzing(false);
    }
  };

  // ===== 로그인 화면 =====
  if (!isLoggedIn) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-gradient-to-br from-green-50 to-blue-50">
        <div className="bg-white rounded-2xl shadow-xl p-8 w-96">
          <div className="text-center mb-6">
            <h1 className="text-3xl font-bold text-green-600">GreenPulse</h1>
            <p className="text-sm text-gray-500 mt-1">
              ISO/IEC 21031:2024 SCI 기반 코드 에너지 분석
            </p>
          </div>

          <form onSubmit={handleLogin} className="space-y-4">
            <div>
              <label className="block text-sm text-gray-600 mb-1">Username</label>
              <input type="text" className="w-full border rounded-lg px-3 py-2 text-sm"
                     value={loginForm.username}
                     onChange={(e) => setLoginForm({ ...loginForm, username: e.target.value })} />
            </div>
            <div>
              <label className="block text-sm text-gray-600 mb-1">Password</label>
              <input type="password" className="w-full border rounded-lg px-3 py-2 text-sm"
                     value={loginForm.password}
                     onChange={(e) => setLoginForm({ ...loginForm, password: e.target.value })} />
            </div>
            {error && <p className="text-red-500 text-sm">{error}</p>}
            <button type="submit"
                    className="w-full bg-green-600 text-white rounded-lg py-2 font-medium hover:bg-green-700 transition">
              로그인
            </button>
          </form>

          <p className="text-xs text-gray-400 mt-4 text-center">
            데모: admin / greenpulse (관리자) | user / greenpulse (무료)
          </p>
        </div>
      </div>
    );
  }

  // ===== 대시보드 =====
  const r = currentResult;

  return (
    <div className="min-h-screen bg-gray-50">
      {/* 헤더 */}
      <header className="bg-white shadow-sm border-b">
        <div className="max-w-7xl mx-auto px-4 py-3 flex items-center justify-between">
          <h1 className="text-xl font-bold text-green-600">GreenPulse</h1>
          <div className="flex items-center gap-4">
            <span className="text-sm text-gray-500">
              {username} <span className="text-xs bg-gray-100 px-2 py-0.5 rounded">{role}</span>
            </span>
            <select value={region} onChange={(e) => setRegion(e.target.value)}
                    className="text-sm border rounded px-2 py-1">
              <option value="KR">🇰🇷 한국 (450)</option>
              <option value="US">🇺🇸 미국 (380)</option>
              <option value="FR">🇫🇷 프랑스 (60)</option>
              <option value="NO">🇳🇴 노르웨이 (20)</option>
            </select>
            <button onClick={clearAuth}
                    className="text-sm text-gray-400 hover:text-red-500 transition">
              로그아웃
            </button>
          </div>
        </div>
      </header>

      <main className="max-w-7xl mx-auto px-4 py-6 space-y-6">
        {/* 코드 입력 */}
        <div className="bg-white rounded-2xl shadow-lg p-6">
          <div className="flex items-center justify-between mb-3">
            <h2 className="text-lg font-semibold text-gray-700">Python 코드 분석</h2>
            <div className="flex gap-2">
              <button onClick={() => setSourceCode(SAMPLE_BAD)}
                      className="text-xs bg-gray-100 hover:bg-gray-200 px-3 py-1 rounded transition">
                샘플 코드 불러오기
              </button>
              <button onClick={handleAnalyze} disabled={isAnalyzing || !sourceCode.trim()}
                      className="bg-green-600 text-white px-4 py-1.5 rounded-lg text-sm font-medium
                                 hover:bg-green-700 disabled:opacity-50 disabled:cursor-not-allowed transition">
                {isAnalyzing ? '분석 중...' : '🔍 분석 시작'}
              </button>
            </div>
          </div>
          <textarea value={sourceCode} onChange={(e) => setSourceCode(e.target.value)}
                    placeholder="분석할 Python 코드를 붙여넣으세요..."
                    className="w-full h-48 font-mono text-sm border rounded-lg p-3 bg-gray-50
                               focus:ring-2 focus:ring-green-300 focus:border-green-400 outline-none"
                    spellCheck={false} />
          {error && <p className="text-red-500 text-sm mt-2">{error}</p>}
        </div>

        {/* 분석 결과 */}
        {r && (
          <>
            {/* 1행: ScoreGauge + AxisBreakdown */}
            <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
              <div className="lg:col-span-1">
                <ScoreGauge
                  sciScore={r.sci_score}
                  grade={r.grade}
                  gradeLabel={r.grade_label}
                  gradeColor={r.grade_color}
                  summaryText={r.summary_text}
                  energyKwh={r.total_energy_kwh}
                  estimatedCost={r.estimated_cost}
                  costCurrency={r.cost_currency}
                  monthlyExecutions={monthlyExecutions}
                  onMonthlyExecutionsChange={setMonthlyExecutions}
                />
              </div>
              <div className="lg:col-span-2">
                <AxisBreakdown
                  axisSummaries={r.axis_summaries}
                  findings={r.findings}
                />
              </div>
            </div>

            {/* 2행: CodeDiff (Before/After) — 덩어리 3에서 /optimize 연결 시 복구 예정 */}
            {/* <CodeDiff
              beforeCode={sourceCode}
              afterCode=""
              beforeSci={r.sci_score}
              afterSci={0}
              reductionPct={0}
              appliedFixes={[]}
            /> */}
          </>
        )}

        {/* 3행: TrendChart (분석 이력) */}
        <TrendChart history={history} />
      </main>
    </div>
  );
}
