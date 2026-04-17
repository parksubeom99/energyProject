/**
 * 3축 에너지 상세 분석 컴포넌트
 *
 * Compute / Data / Token 3축의 에너지 비율과 상태를 시각화.
 * status(good/warning/critical)에 따라 색상 바인딩.
 *
 * Props:
 *   axisSummaries: Array<{axis, energy_kwh, energy_gco2, percentage, finding_count, status}>
 *   findings: Array<{axis, severity, line, function_name, problem, suggestion, estimated_reduction}>
 */

const AXIS_LABELS = {
  compute: { name: 'Compute', icon: '🖥️', desc: 'CPU 연산 에너지' },
  data: { name: 'Data', icon: '🗄️', desc: 'DB/네트워크 IO 에너지' },
  token: { name: 'Token', icon: '🤖', desc: 'LLM API 토큰 에너지' },
};

const STATUS_COLORS = {
  good: { bg: 'bg-green-50', text: 'text-green-700', bar: 'bg-green-500', badge: 'bg-green-100' },
  warning: { bg: 'bg-yellow-50', text: 'text-yellow-700', bar: 'bg-yellow-500', badge: 'bg-yellow-100' },
  critical: { bg: 'bg-red-50', text: 'text-red-700', bar: 'bg-red-500', badge: 'bg-red-100' },
};

const SEVERITY_COLORS = {
  high: 'bg-red-100 text-red-800',
  medium: 'bg-yellow-100 text-yellow-800',
  low: 'bg-blue-100 text-blue-800',
  info: 'bg-gray-100 text-gray-600',
};

export default function AxisBreakdown({ axisSummaries = [], findings = [] }) {
  return (
    <div className="bg-white rounded-2xl shadow-lg p-6">
      <h2 className="text-lg font-semibold text-gray-700 mb-4">3축 에너지 분석</h2>

      {/* 축별 요약 바 */}
      <div className="space-y-4 mb-6">
        {axisSummaries.map((axis) => {
          const label = AXIS_LABELS[axis.axis] || { name: axis.axis, icon: '📊' };
          const colors = STATUS_COLORS[axis.status] || STATUS_COLORS.good;

          return (
            <div key={axis.axis} className={`p-3 rounded-lg ${colors.bg}`}>
              <div className="flex items-center justify-between mb-1">
                <span className="font-medium text-sm">
                  {label.icon} {label.name}
                </span>
                <div className="flex items-center gap-2">
                  <span className={`text-xs px-2 py-0.5 rounded-full ${colors.badge} ${colors.text}`}>
                    {axis.status}
                  </span>
                  <span className="text-sm font-bold">{axis.percentage.toFixed(1)}%</span>
                </div>
              </div>
              {/* 비율 바 */}
              <div className="w-full h-2 bg-gray-200 rounded-full overflow-hidden">
                <div className={`h-full rounded-full transition-all duration-700 ${colors.bar}`}
                     style={{ width: `${Math.max(axis.percentage, 1)}%` }} />
              </div>
              <div className="flex justify-between mt-1">
                <span className="text-xs text-gray-500">{label.desc}</span>
                <span className="text-xs text-gray-500">
                  {axis.energy_gco2.toFixed(4)} gCO₂
                </span>
              </div>
            </div>
          );
        })}
      </div>

      {/* 발견 사항 목록 */}
      {findings.length > 0 && (
        <>
          <h3 className="text-sm font-semibold text-gray-600 mb-2">
            발견 사항 ({findings.length}건)
          </h3>
          <div className="space-y-2">
            {findings.map((f, i) => (
              <div key={i} className="border border-gray-100 rounded-lg p-3 text-sm">
                <div className="flex items-center gap-2 mb-1">
                  <span className={`text-xs px-1.5 py-0.5 rounded ${SEVERITY_COLORS[f.severity]}`}>
                    {f.severity}
                  </span>
                  <span className="text-xs text-gray-400">
                    {AXIS_LABELS[f.axis]?.icon} {f.function_name}() — line {f.line}
                  </span>
                </div>
                <p className="text-gray-700 font-medium">{f.problem}</p>
                <p className="text-gray-500 text-xs mt-1">
                  💡 {f.suggestion}
                </p>
                <p className="text-green-600 text-xs mt-0.5">
                  📉 {f.estimated_reduction}
                </p>
              </div>
            ))}
          </div>
        </>
      )}
    </div>
  );
}
