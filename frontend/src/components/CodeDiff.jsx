/**
 * Before/After 코드 비교 컴포넌트
 *
 * Optimizer가 산출한 최적화 코드와 원본을 나란히 비교.
 * SCI 점수 변화(Before→After)와 적용된 수정 목록을 표시.
 *
 * Props:
 *   beforeCode: string     — 원본 코드
 *   afterCode: string      — 최적화 코드
 *   beforeSci: number      — Before SCI 점수
 *   afterSci: number       — After SCI 점수
 *   reductionPct: number   — 감소율 (%)
 *   appliedFixes: string[] — 적용된 수정 목록
 */
export default function CodeDiff({
  beforeCode = '',
  afterCode = '',
  beforeSci = 0,
  afterSci = 0,
  reductionPct = 0,
  appliedFixes = [],
}) {
  if (!beforeCode && !afterCode) {
    return (
      <div className="bg-white rounded-2xl shadow-lg p-6 text-center text-gray-400">
        <p>코드를 분석하면 Before/After 비교가 여기에 표시됩니다.</p>
      </div>
    );
  }

  return (
    <div className="bg-white rounded-2xl shadow-lg p-6">
      <h2 className="text-lg font-semibold text-gray-700 mb-4">Before / After 코드 비교</h2>

      {/* SCI 비교 헤더 */}
      <div className="flex items-center justify-between bg-gray-50 rounded-lg p-4 mb-4">
        <div className="text-center">
          <div className="text-xs text-gray-500 mb-1">Before</div>
          <div className="text-2xl font-bold text-red-500">{beforeSci.toFixed(1)}</div>
          <div className="text-xs text-gray-400">gCO₂eq/R</div>
        </div>
        <div className="text-center">
          <div className="text-3xl text-gray-300">→</div>
        </div>
        <div className="text-center">
          <div className="text-xs text-gray-500 mb-1">After</div>
          <div className="text-2xl font-bold text-green-500">{afterSci.toFixed(1)}</div>
          <div className="text-xs text-gray-400">gCO₂eq/R</div>
        </div>
        <div className="text-center bg-green-50 rounded-lg px-4 py-2">
          <div className="text-xl font-bold text-green-600">-{reductionPct.toFixed(1)}%</div>
          <div className="text-xs text-green-500">SCI 감소</div>
        </div>
      </div>

      {/* 적용된 수정 목록 */}
      {appliedFixes.length > 0 && (
        <div className="mb-4">
          <h3 className="text-sm font-semibold text-gray-600 mb-2">적용된 최적화</h3>
          <ul className="space-y-1">
            {appliedFixes.map((fix, i) => (
              <li key={i} className="text-sm text-green-700 flex items-center gap-1">
                <span className="text-green-500">✓</span> {fix}
              </li>
            ))}
          </ul>
        </div>
      )}

      {/* 코드 비교 */}
      <div className="grid grid-cols-2 gap-4">
        {/* Before */}
        <div>
          <div className="flex items-center gap-2 mb-2">
            <span className="text-xs font-medium text-red-600 bg-red-50 px-2 py-0.5 rounded">BEFORE</span>
            <span className="text-xs text-gray-400">원본 코드</span>
          </div>
          <pre className="bg-gray-900 text-gray-100 p-4 rounded-lg text-xs overflow-x-auto max-h-96 overflow-y-auto">
            <code>{beforeCode}</code>
          </pre>
        </div>
        {/* After */}
        <div>
          <div className="flex items-center gap-2 mb-2">
            <span className="text-xs font-medium text-green-600 bg-green-50 px-2 py-0.5 rounded">AFTER</span>
            <span className="text-xs text-gray-400">최적화 코드</span>
          </div>
          <pre className="bg-gray-900 text-green-100 p-4 rounded-lg text-xs overflow-x-auto max-h-96 overflow-y-auto">
            <code>{afterCode}</code>
          </pre>
        </div>
      </div>
    </div>
  );
}
