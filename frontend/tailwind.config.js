/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,jsx}'],
  theme: {
    extend: {
      colors: {
        // SCI 등급별 색상 — scorer.py GRADE_INFO와 동기화
        'grade-a': '#22c55e',
        'grade-b': '#84cc16',
        'grade-c': '#eab308',
        'grade-d': '#f97316',
        'grade-f': '#ef4444',
      },
    },
  },
  plugins: [],
};
