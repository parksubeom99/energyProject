/**
 * 분석 이력 트렌드 차트 컴포넌트
 *
 * 시간 순서로 SCI 점수 추이를 시각화.
 * Recharts 라이브러리 사용 (React 생태계 표준).
 *
 * Props:
 *   history: Array<{analysis_id, sci_score, grade, total_lines, analyzed_at}>
 */
import {
  LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip,
  ResponsiveContainer, ReferenceLine
} from 'recharts';

const GRADE_THRESHOLDS = [
  { y: 10, label: 'A', color: '#22c55e' },
  { y: 25, label: 'B', color: '#84cc16' },
  { y: 50, label: 'C', color: '#eab308' },
  { y: 100, label: 'D', color: '#f97316' },
];

export default function TrendChart({ history = [] }) {
  if (history.length === 0) {
    return (
      <div className="bg-white rounded-2xl shadow-lg p-6 text-center text-gray-400">
        <p>분석 이력이 쌓이면 SCI 추이 차트가 여기에 표시됩니다.</p>
      </div>
    );
  }

  // 시간순 정렬 + 차트 데이터 변환
  const chartData = [...history]
    .sort((a, b) => a.analyzed_at.localeCompare(b.analyzed_at))
    .map((item, idx) => ({
      name: `#${idx + 1}`,
      sci: item.sci_score,
      grade: item.grade,
      lines: item.total_lines,
      time: new Date(item.analyzed_at).toLocaleString('ko-KR', {
        month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit',
      }),
    }));

  return (
    <div className="bg-white rounded-2xl shadow-lg p-6">
      <h2 className="text-lg font-semibold text-gray-700 mb-4">
        분석 이력 트렌드 ({history.length}건)
      </h2>

      <ResponsiveContainer width="100%" height={280}>
        <LineChart data={chartData} margin={{ top: 5, right: 20, bottom: 5, left: 0 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
          <XAxis dataKey="name" tick={{ fontSize: 12 }} />
          <YAxis tick={{ fontSize: 12 }} />
          <Tooltip
            content={({ active, payload }) => {
              if (!active || !payload?.length) return null;
              const d = payload[0].payload;
              return (
                <div className="bg-white border rounded-lg shadow-lg p-3 text-sm">
                  <p className="font-bold">SCI: {d.sci.toFixed(1)} ({d.grade})</p>
                  <p className="text-gray-500">{d.lines}줄 | {d.time}</p>
                </div>
              );
            }}
          />
          {/* 등급 기준선 */}
          {GRADE_THRESHOLDS.map((t) => (
            <ReferenceLine key={t.label} y={t.y} stroke={t.color}
                           strokeDasharray="5 5" strokeOpacity={0.5}
                           label={{ value: t.label, fontSize: 10, fill: t.color }} />
          ))}
          <Line type="monotone" dataKey="sci" stroke="#3b82f6"
                strokeWidth={2} dot={{ r: 4 }} activeDot={{ r: 6 }} />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}
