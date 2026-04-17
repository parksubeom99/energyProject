/**
 * SCI 점수 게이지 컴포넌트
 *
 * SCI 점수를 원형 게이지로 시각화.
 * 등급(A~F)에 따라 색상이 변하고, 점수/등급/설명을 표시.
 *
 * Props:
 *   sciScore: number  — SCI 점수 (gCO2eq/R)
 *   grade: string     — 등급 (A~F)
 *   gradeLabel: string — "매우 효율적" 등
 *   gradeColor: string — "#22c55e" 등 (scorer.py GRADE_INFO에서)
 *   summaryText: string — 종합 요약 텍스트
 */
export default function ScoreGauge({
  sciScore = 0,
  grade = 'A',
  gradeLabel = '',
  gradeColor = '#22c55e',
  summaryText = '',
}) {
  // 게이지 각도 계산: 0~500+ → 0~180도
  const maxScore = 500;
  const clampedScore = Math.min(sciScore, maxScore);
  const angle = (clampedScore / maxScore) * 180;
  const rotation = angle - 90; // -90도가 시작점

  return (
    <div className="bg-white rounded-2xl shadow-lg p-6 text-center">
      <h2 className="text-lg font-semibold text-gray-700 mb-4">SCI Score</h2>

      {/* 게이지 영역 */}
      <div className="relative w-48 h-24 mx-auto mb-4 overflow-hidden">
        {/* 배경 반원 */}
        <div className="absolute w-48 h-48 rounded-full border-[16px] border-gray-200"
             style={{ top: 0, clipPath: 'inset(0 0 50% 0)' }} />
        {/* 점수 반원 */}
        <div className="absolute w-48 h-48 rounded-full border-[16px]"
             style={{
               borderColor: gradeColor,
               top: 0,
               clipPath: 'inset(0 0 50% 0)',
               transform: `rotate(${rotation}deg)`,
               transformOrigin: 'center center',
               transition: 'transform 0.8s ease-out',
             }} />
        {/* 중앙 점수 표시 */}
        <div className="absolute bottom-0 left-1/2 -translate-x-1/2 text-center">
          <span className="text-3xl font-bold" style={{ color: gradeColor }}>
            {sciScore.toFixed(1)}
          </span>
          <span className="text-sm text-gray-500 ml-1">gCO₂eq/R</span>
        </div>
      </div>

      {/* 등급 배지 */}
      <div className="inline-flex items-center gap-2 px-4 py-2 rounded-full mb-3"
           style={{ backgroundColor: `${gradeColor}15`, color: gradeColor }}>
        <span className="text-2xl font-bold">{grade}</span>
        <span className="text-sm font-medium">{gradeLabel}</span>
      </div>

      {/* 요약 텍스트 */}
      {summaryText && (
        <p className="text-xs text-gray-500 mt-3 whitespace-pre-line leading-relaxed">
          {summaryText}
        </p>
      )}
    </div>
  );
}
