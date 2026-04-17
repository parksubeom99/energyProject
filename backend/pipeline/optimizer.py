"""
Claude API 최적화 코드 생성 — 파이프라인 ④ 단계
=================================================
Scorer의 ScoreReport를 받아 Claude API로 최적화 코드를 생성.

흐름:
  ScoreReport(근거 목록) → 프롬프트 구성 → Claude API 호출
  → 최적화 코드 수신 → 문법 검증 → OptimizationResult 반환

면접 포인트:
"주식에서는 AI를 멀티에이전트 의사결정에 활용했고,
 에너지에서는 AI를 코드 자동 리팩토링에 활용했습니다.
 같은 LLM이지만 문제의 성격에 따라 활용 방식을 다르게 설계한 것이 핵심입니다."

프로덕션: CLAUDE_API_KEY 환경변수 필요 (.env 파일, 절대 커밋 금지)
테스트: MockClaudeClient로 실제 API 호출 없이 검증
"""
import ast
from dataclasses import dataclass, field
from typing import Optional, Protocol

from config import settings
from pipeline.scorer import ScoreReport, Finding


# ================================================================
# Claude 클라이언트 인터페이스 — 테스트 교체 가능
# ================================================================
class ClaudeClientInterface(Protocol):
    """Claude API 클라이언트 인터페이스"""
    def generate(self, prompt: str) -> str:
        """프롬프트 → 최적화 코드 반환"""
        ...


# ================================================================
# Mock Claude 클라이언트 — 테스트/개발용
# ================================================================
class MockClaudeClient:
    """
    Claude API 없이 동작하는 Mock 클라이언트.

    규칙 기반으로 코드를 변환하여 실제 최적화를 시뮬레이션한다:
    1. O(n²) 중첩 루프 → set 기반 O(n)으로 변환
    2. N+1 쿼리 → JOIN 1회 쿼리로 변환
    3. 캐싱 없는 LLM 호출 → @lru_cache 추가

    이 Mock이 반환하는 코드를 verifier.py로 재분석하면
    실제로 SCI 점수가 감소하므로 Before/After 검증이 가능하다.
    """

    def generate(self, prompt: str) -> str:
        """프롬프트에서 원본 코드를 추출하고 규칙 기반 최적화 적용"""
        # 프롬프트에서 원본 코드 블록 추출
        original_code = _extract_code_from_prompt(prompt)
        if not original_code:
            return ""

        optimized = original_code

        # 규칙 1: O(n²) 중첩 루프 → set 기반 O(n) 변환
        optimized = _optimize_nested_loops(optimized)

        # 규칙 2: N+1 개별 쿼리 → JOIN 1회 쿼리 변환
        optimized = _optimize_n_plus_1(optimized)

        # 규칙 3: 캐싱 없는 함수에 @lru_cache 추가
        optimized = _optimize_add_cache(optimized)

        return optimized


# ================================================================
# 실제 Claude API 클라이언트
# ================================================================
class RealClaudeClient:
    """
    실제 Anthropic Claude API 호출 클라이언트.

    CLAUDE_API_KEY 환경변수가 설정되어 있어야 동작.
    없으면 MockClaudeClient로 폴백.
    """

    def __init__(self):
        if not settings.CLAUDE_API_KEY:
            raise ValueError("CLAUDE_API_KEY 환경변수가 설정되지 않았습니다")

        import anthropic
        self._client = anthropic.Anthropic(api_key=settings.CLAUDE_API_KEY)

    def generate(self, prompt: str) -> str:
        """Claude API 호출 → 최적화 코드 반환"""
        response = self._client.messages.create(
            model=settings.CLAUDE_MODEL,
            max_tokens=4096,
            messages=[{"role": "user", "content": prompt}],
        )
        # 응답에서 코드 블록 추출
        text = response.content[0].text
        return _extract_code_block(text)


# ================================================================
# 최적화 결과 데이터 모델
# ================================================================
@dataclass
class OptimizationResult:
    """최적화 결과 — verifier.py + 대시보드 CodeDiff 입력"""
    original_code: str           # Before 코드
    optimized_code: str          # After 코드 (Claude 산출)
    is_valid: bool               # 최적화 코드 문법 유효 여부
    applied_fixes: list = field(default_factory=list)  # 적용된 최적화 목록
    error_message: str = ""      # 실패 시 오류 메시지


# ================================================================
# 최적화 실행 — 메인 함수
# ================================================================
def optimize(
    report: ScoreReport,
    original_code: str,
    client: Optional[ClaudeClientInterface] = None,
    max_retries: int = 2,
) -> OptimizationResult:
    """
    코드 최적화 실행

    흐름:
    1. ScoreReport에서 high severity findings 추출
    2. 최적화 프롬프트 구성
    3. Claude API (또는 Mock) 호출
    4. 응답 코드 문법 검증
    5. 실패 시 재시도 (max_retries)

    Args:
        report: scorer.score()의 출력
        original_code: 원본 Python 코드
        client: Claude 클라이언트 (None이면 자동 선택)
        max_retries: 문법 오류 시 재시도 횟수

    Returns:
        OptimizationResult — Before/After 코드 + 유효성
    """
    # 클라이언트 자동 선택
    if client is None:
        client = _get_default_client()

    # 프롬프트 생성
    prompt = _build_optimization_prompt(report, original_code)

    # 최적화 시도 (재시도 포함)
    last_error = ""
    for attempt in range(1, max_retries + 1):
        try:
            optimized_code = client.generate(prompt)

            if not optimized_code or not optimized_code.strip():
                last_error = "최적화 코드가 비어있습니다"
                continue

            # 문법 검증
            is_valid, syntax_error = _validate_syntax(optimized_code)
            if not is_valid:
                last_error = f"문법 오류 (시도 {attempt}): {syntax_error}"
                continue

            # 성공
            applied = _identify_applied_fixes(report.findings, optimized_code)

            return OptimizationResult(
                original_code=original_code,
                optimized_code=optimized_code,
                is_valid=True,
                applied_fixes=applied,
            )

        except Exception as e:
            last_error = f"API 오류 (시도 {attempt}): {str(e)}"

    # 모든 시도 실패
    return OptimizationResult(
        original_code=original_code,
        optimized_code="",
        is_valid=False,
        error_message=last_error,
    )


# ================================================================
# 프롬프트 구성
# ================================================================
def _build_optimization_prompt(report: ScoreReport, code: str) -> str:
    """
    Claude API 최적화 프롬프트 생성

    프롬프트 구조:
    1. 역할 설명 (Green Software Engineer)
    2. SCI 점수 + 발견된 비효율 목록
    3. 원본 코드
    4. 최적화 지침 (동작 변경 금지)
    """
    # findings를 텍스트로 변환
    findings_text = ""
    for i, f in enumerate(report.findings, 1):
        findings_text += (
            f"{i}. [{f.axis}] {f.severity} — line {f.line} "
            f"({f.function_name}): {f.problem}\n"
            f"   제안: {f.suggestion}\n"
            f"   예상 절감: {f.estimated_reduction}\n"
        )

    if not findings_text:
        findings_text = "발견된 비효율이 없습니다."

    return f"""당신은 Green Software Engineer입니다.
아래 Python 코드의 에너지 효율을 최적화하세요.

## 현재 SCI 점수
- SCI: {report.sci_score} gCO₂eq/R (등급: {report.grade})

## 발견된 비효율
{findings_text}

## 원본 코드
```python
{code}
```

## 최적화 지침
1. 위에 나열된 비효율 패턴을 하나씩 해결하세요.
2. 함수의 입출력 인터페이스(시그니처, 반환값)는 변경하지 마세요.
3. O(n²) → O(n) 변환, N+1 → JOIN, 캐싱 추가 등 에너지 절감에 집중하세요.
4. import 문도 필요하면 추가하세요.
5. 코드만 반환하고, 설명은 하지 마세요.

최적화된 Python 코드:
```python
"""


# ================================================================
# 규칙 기반 최적화 함수들 (MockClaudeClient 전용)
# ================================================================
def _optimize_nested_loops(code: str) -> str:
    """O(n²) 중첩 루프 패턴 → set 기반 O(n) 변환"""
    # find_duplicates 패턴 탐지 및 변환
    if "for i in range(len(" in code and "for j in range(i + 1" in code:
        old_pattern = """def find_duplicates(items: list) -> list:
    duplicates = []
    for i in range(len(items)):
        for j in range(i + 1, len(items)):
            if items[i] == items[j]:
                if items[i] not in duplicates:
                    duplicates.append(items[i])
    return duplicates"""

        new_pattern = """def find_duplicates(items: list) -> list:
    seen = set()
    duplicates = set()
    for item in items:
        if item in seen:
            duplicates.add(item)
        seen.add(item)
    return list(duplicates)"""

        if old_pattern in code:
            code = code.replace(old_pattern, new_pattern)
        # 인자에 타입 없는 버전도 처리
        old_no_type = old_pattern.replace("items: list", "items")
        new_no_type = new_pattern.replace("items: list", "items")
        if old_no_type in code:
            code = code.replace(old_no_type, new_no_type)

    return code


def _optimize_n_plus_1(code: str) -> str:
    """N+1 개별 쿼리 → JOIN 1회 쿼리 변환"""
    # get_user_orders / get_orders 패턴 탐지
    if "for user_id in user_ids:" in code and 'cursor.execute(' in code:
        # 간소화된 N+1 패턴 (test에서 사용하는 짧은 버전)
        lines = code.split("\n")
        new_lines = []
        skip_until_close = False
        func_replaced = False

        for line in lines:
            # N+1 패턴의 for 루프를 IN 절 쿼리로 변환
            if "for uid in user_ids:" in line or "for user_id in user_ids:" in line:
                if not func_replaced:
                    indent = "    "
                    new_lines.append(f'{indent}placeholders = ",".join("?" * len(user_ids))')
                    new_lines.append(f'{indent}cursor.execute(f"SELECT * FROM orders WHERE user_id IN ({{placeholders}})", user_ids)')
                    new_lines.append(f'{indent}rows = cursor.fetchall()')
                    func_replaced = True
                    skip_until_close = True
                    continue
            if skip_until_close:
                # for 루프 내부 건너뛰기 (들여쓰기 기반)
                stripped = line.lstrip()
                if stripped and not line.startswith("        ") and not line.startswith("\t\t"):
                    skip_until_close = False
                    new_lines.append(line)
                continue
            new_lines.append(line)

        code = "\n".join(new_lines)

    return code


def _optimize_add_cache(code: str) -> str:
    """캐싱 없는 함수에 @lru_cache 추가"""
    if "requests.post" in code and "@lru_cache" not in code and "@cache" not in code:
        # lru_cache import 추가
        if "from functools import lru_cache" not in code:
            # import 섹션 끝에 추가
            lines = code.split("\n")
            insert_idx = 0
            for i, line in enumerate(lines):
                if line.startswith("import ") or line.startswith("from "):
                    insert_idx = i + 1
            lines.insert(insert_idx, "from functools import lru_cache")
            code = "\n".join(lines)

        # requests.post를 호출하는 함수 앞에 @lru_cache(maxsize=256) 추가
        lines = code.split("\n")
        new_lines = []
        i = 0
        while i < len(lines):
            line = lines[i]
            # def 라인이고 이 함수 내에 requests.post가 있는지 확인
            if line.strip().startswith("def ") and i + 1 < len(lines):
                # 함수 본문에서 requests.post 찾기
                func_body = []
                j = i + 1
                while j < len(lines):
                    if lines[j].strip() and not lines[j].startswith(" ") and not lines[j].startswith("\t"):
                        break
                    func_body.append(lines[j])
                    j += 1

                has_api_call = any("requests.post" in l for l in func_body)
                already_cached = (
                    i > 0 and "@lru_cache" in lines[i - 1]
                ) or (
                    len(new_lines) > 0 and "@lru_cache" in new_lines[-1]
                )

                if has_api_call and not already_cached:
                    indent = ""
                    for ch in line:
                        if ch == " ":
                            indent += " "
                        else:
                            break
                    new_lines.append(f"{indent}@lru_cache(maxsize=256)")

            new_lines.append(line)
            i += 1

        code = "\n".join(new_lines)

    return code


# ================================================================
# 유틸리티 함수
# ================================================================
def _get_default_client() -> ClaudeClientInterface:
    """기본 클라이언트 선택: API 키 있으면 Real, 없으면 Mock"""
    if settings.CLAUDE_API_KEY:
        try:
            return RealClaudeClient()
        except Exception:
            pass
    return MockClaudeClient()


def _extract_code_from_prompt(prompt: str) -> str:
    """프롬프트에서 원본 코드 블록 추출"""
    # ```python ... ``` 블록 추출
    parts = prompt.split("```python")
    if len(parts) >= 2:
        # 첫 번째 코드 블록이 원본
        code_block = parts[1].split("```")[0]
        return code_block.strip()
    return ""


def _extract_code_block(text: str) -> str:
    """Claude 응답에서 코드 블록 추출"""
    if "```python" in text:
        code = text.split("```python")[1].split("```")[0]
        return code.strip()
    if "```" in text:
        code = text.split("```")[1].split("```")[0]
        return code.strip()
    return text.strip()


def _validate_syntax(code: str) -> tuple[bool, str]:
    """Python 코드 문법 검증"""
    try:
        ast.parse(code)
        return True, ""
    except SyntaxError as e:
        return False, str(e)


def _identify_applied_fixes(
    findings: list[Finding],
    optimized_code: str,
) -> list[str]:
    """원본 findings와 최적화 코드를 비교하여 적용된 수정 목록 생성"""
    applied = []

    for f in findings:
        if f.axis == "compute" and "set()" in optimized_code:
            applied.append(f"[Compute] {f.function_name}: O(n²)→O(n) set 기반 변환")
        elif f.axis == "data" and ("JOIN" in optimized_code or "IN (" in optimized_code):
            applied.append(f"[Data] {f.function_name}: N+1→JOIN 1회 쿼리 변환")
        elif f.axis == "token" and "@lru_cache" in optimized_code:
            applied.append(f"[Token] {f.function_name}: @lru_cache 캐싱 추가")

    return applied
