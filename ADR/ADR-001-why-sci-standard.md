# ADR-001: ISO/IEC 21031:2024 SCI 표준 채택

## 상태: 채택됨
## 날짜: 2026-04-15

## 맥락
에너지 프로젝트의 핵심 점수 체계를 자체 개발할지, 국제 표준을 채택할지 결정해야 한다.

## 후보
1. **자체 점수 체계** — 토큰/복잡도/IO 가중 합산
2. **SCI (Software Carbon Intensity)** — ISO/IEC 21031:2024
3. **CodeCarbon 방식** — 런타임 전력 직접 측정

## 결정
**SCI 채택.** 공식: `SCI = ((E × I) + M) / R`

## 근거
- SCI는 2024년 ISO 국제 표준이 됨 → "우리 자체 점수"보다 100배 신뢰도 높음
- Green Software Foundation에 Google, Microsoft, Accenture, NTT DATA 등 참여 → 업계 합의
- SCI for AI 스펙이 2025년 비준 → LLM 토큰 에너지도 공식 방법론 존재
- 면접에서 "왜 이 점수냐?"에 "ISO 국제 표준입니다"로 답변 가능
- 자체 점수 체계는 "그거 검증됐냐?" 질문에 약함

## 트레이드오프
- SCI의 E(에너지) 산출이 정적 분석만으로는 추정치 → Pearson r > 0.7 검증으로 보완
- M(내재 탄소)는 하드웨어 정보 필요 → 클라우드 인스턴스 타입별 기본값 제공
- I(탄소 강도)는 지역별 → Electricity Maps API 연동 또는 기본값(한국: 450 gCO₂/kWh)

## 참고
- https://sci.greensoftware.foundation/
- https://github.com/Green-Software-Foundation/sci
- ISO/IEC 21031:2024
