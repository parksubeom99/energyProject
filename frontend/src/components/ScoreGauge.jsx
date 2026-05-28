/**
 * 전력·비용 게이지 컴포넌트 (덩어리 2 보완 — 1회/월/년 3단 스케일)
 *
 * 위계:
 *   - 월 (×monthly_executions)           : 1급 (큰 글씨) — 시연 임팩트 최적점
 *   - 1회 / 년                            : 보조 (작은 글씨)
 *   - 탄소 SCI + 등급                    : 보조 (배지)
 *
 * 재계산:
 *   백엔드 무재호출. cost.py 로직과 동치인 단순 곱셈을 프론트에서 수행:
 *     monthly = estimated × n
 *     yearly  = monthly × 12
 *
 * Props:
 *   sciScore, grade, gradeLabel, gradeColor, summaryText  — 등급 보조 표시
 *   energyKwh: 1회당 에너지 (kWh)
 *   estimatedCost: 1회당 전기요금
 *   costCurrency: 통화 코드 (예 "USD")
 *   monthlyExecutions: 월간 실행 횟수 (상위에서 state 관리)
 *   onMonthlyExecutionsChange: 입력 변경 핸들러
 */

// 입력 가드 상수
const MAX_MONTHLY_EXECUTIONS = 10_000_000_000;

/**
 * 스케일별 표시 포맷:
 *   - 1회(매우 작은 값): toFixed(6)
 *   - 월/년: 1000 미만 toFixed(2), 1000+ toLocaleString (천 단위 콤마)
 */
function formatScale(value, isMicro) {
  if (isMicro) return value.toFixed(6);
  if (value >= 1000) {
    return value.toLocaleString('en-US', {
      minimumFractionDigits: 2,
      maximumFractionDigits: 2,
    });
  }
  return value.toFixed(2);
}

export default function ScoreGauge({
  sciScore = 0,
  grade = 'A',
  gradeLabel = '',
  gradeColor = '#22c55e',
  summaryText = '',
  energyKwh = 0,
  estimatedCost = 0,
  costCurrency = 'USD',
  monthlyExecutions = 1_000_000,
  onMonthlyExecutionsChange = () => {},
}) {
  // === 게이지 각도 (등급 색상 신호) ===
  const maxScore = 500;
  const clampedScore = Math.min(sciScore, maxScore);
  const angle = (clampedScore / maxScore) * 180;
  const rotation = angle - 90;

  // === 월/년 환산 (cost.py와 동치 곱셈) ===
  const monthlyKwh = energyKwh * monthlyExecutions;
  const monthlyCost = estimatedCost * monthlyExecutions;
  const yearlyKwh = monthlyKwh * 12;
  const yearlyCost = monthlyCost * 12;

  // === 화폐 기호 ===
  const currencySymbol = costCurrency === 'USD' ? '$' : '';

  // === 입력 검증 ===
  const handleMonthlyChange = (e) => {
    const raw = Number(e.target.value) || 0;
    const clamped = Math.max(
      0,
      Math.min(MAX_MONTHLY_EXECUTIONS, Math.floor(raw))
    );
    onMonthlyExecutionsChange(clamped);
  };

  return (
    <div className="bg-white rounded-2xl shadow-lg p-6 text-center">
      <h2 className="text-lg font-semibold text-gray-700 mb-3">전력 · 비용</h2>

      {/* === 월간 실행 횟수 입력 === */}
      <div className="mb-4 text-left">
        <label className="block text-xs text-gray-600 mb-1">
          월간 실행 횟수 (예: 1,000,000)
        </label>
        <input
          type="number"
          min={0}
          max={MAX_MONTHLY_EXECUTIONS}
          step={1}
          value={monthlyExecutions}
          onChange={handleMonthlyChange}
          className="w-full border rounded-lg px-3 py-1.5 text-sm
                     focus:ring-2 focus:ring-green-300 focus:border-green-400 outline-none"
        />
      </div>

      {/* === 3단 세로 레이아웃: 1회 → 월(1급) → 년 === */}
      <div className="space-y-3 mb-4">
        {/* 1회 — 보조 */}
        <div className="text-xs text-gray-500">
          <span className="font-medium">1회</span>
          <span className="mx-2">·</span>
          <span>{formatScale(energyKwh, true)} kWh</span>
          <span className="mx-2">·</span>
          <span>{currencySymbol}{formatScale(estimatedCost, true)}</span>
        </div>

        {/* 월 — 1급 (큰 글씨) */}
        <div className="bg-green-50 rounded-xl py-3 px-2 border border-green-100">
          <div className="text-xs font-medium text-green-700 mb-1">월</div>
          <div className="flex items-baseline justify-center gap-2">
            <span className="text-3xl font-bold text-green-600">
              {formatScale(monthlyKwh, false)}
            </span>
            <span className="text-sm text-gray-500">kWh</span>
          </div>
          <div className="flex items-baseline justify-center gap-2 mt-1">
            <span className="text-3xl font-bold text-blue-600">
              {currencySymbol}{formatScale(monthlyCost, false)}
            </span>
            <span className="text-sm text-gray-500">{costCurrency}</span>
          </div>
        </div>

        {/* 년 — 보조 */}
        <div className="text-xs text-gray-500">
          <span className="font-medium">년</span>
          <span className="mx-2">·</span>
          <span>{formatScale(yearlyKwh, false)} kWh</span>
          <span className="mx-2">·</span>
          <span>{currencySymbol}{formatScale(yearlyCost, false)}</span>
        </div>
      </div>

      {/* === 게이지 영역 (등급 색상 신호) === */}
      <div className="relative w-40 h-20 mx-auto mb-3 overflow-hidden">
        <div className="absolute w-40 h-40 rounded-full border-[12px] border-gray-200"
             style={{ top: 0, clipPath: 'inset(0 0 50% 0)' }} />
        <div className="absolute w-40 h-40 rounded-full border-[12px]"
             style={{
               borderColor: gradeColor,
               top: 0,
               clipPath: 'inset(0 0 50% 0)',
               transform: `rotate(${rotation}deg)`,
               transformOrigin: 'center center',
               transition: 'transform 0.8s ease-out',
             }} />
      </div>

      {/* === 보조: SCI 점수 + 등급 배지 (작은 글씨) === */}
      <div className="flex items-center justify-center gap-2 mb-2 text-sm">
        <span className="text-gray-600">
          탄소 {sciScore.toFixed(1)}
          <span className="text-xs text-gray-400 ml-1">gCO₂eq/R</span>
        </span>
        <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs"
              style={{ backgroundColor: `${gradeColor}15`, color: gradeColor }}>
          <span className="font-bold">{grade}</span>
          <span>{gradeLabel}</span>
        </span>
      </div>

      {summaryText && (
        <p className="text-xs text-gray-500 mt-2 whitespace-pre-line leading-relaxed">
          {summaryText}
        </p>
      )}
    </div>
  );
}
