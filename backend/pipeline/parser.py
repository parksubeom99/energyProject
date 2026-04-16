"""
코드 파서 — Python AST 기반 정적 분석
========================================
파이프라인 ① 단계: 코드 문자열 → 구조화된 분석 데이터

Python ast 모듈로 코드를 파싱하여 에너지 관련 패턴을 추출한다:
- 함수 정의 (복잡도 측정 대상)
- 루프 구조 (중첩 깊이 → Compute Energy)
- DB 호출 (execute, fetchall 등 → Data Energy)
- HTTP/API 호출 (requests.post/get 등 → Data Energy)
- LLM 호출 (anthropic, openai 등 → Token Energy)

이 파서의 출력이 analyzer.py의 입력이 된다.
"""
import ast
from dataclasses import dataclass, field


@dataclass
class FunctionInfo:
    """함수 단위 분석 정보"""
    name: str                          # 함수명
    lineno: int                        # 시작 줄 번호
    end_lineno: int                    # 끝 줄 번호
    line_count: int                    # 코드 줄 수
    loop_count: int = 0               # 루프 개수 (for/while)
    nested_loop_depth: int = 0        # 최대 중첩 루프 깊이
    branch_count: int = 0            # 분기 개수 (if/elif/else)
    cyclomatic_complexity: int = 1    # 순환 복잡도 (McCabe)
    has_cache_decorator: bool = False  # @lru_cache/@cache 데코레이터 여부
    db_calls: list = field(default_factory=list)      # DB 호출 목록
    api_calls: list = field(default_factory=list)     # HTTP API 호출 목록
    llm_calls: list = field(default_factory=list)     # LLM API 호출 목록


@dataclass
class ParseResult:
    """전체 코드 파싱 결과 — analyzer.py의 입력"""
    functions: list                    # FunctionInfo 리스트
    total_lines: int                   # 전체 줄 수
    import_count: int                  # import 수
    global_db_calls: list = field(default_factory=list)   # 함수 밖 DB 호출
    global_api_calls: list = field(default_factory=list)  # 함수 밖 API 호출
    global_llm_calls: list = field(default_factory=list)  # 함수 밖 LLM 호출
    errors: list = field(default_factory=list)             # 파싱 오류


# ================================================================
# DB 호출 패턴 — SQL 실행 메서드명
# ================================================================
DB_CALL_PATTERNS = {
    "execute", "executemany", "fetchone", "fetchall", "fetchmany",
    "commit", "rollback", "cursor",
}

# ================================================================
# HTTP/API 호출 패턴 — requests/httpx/aiohttp 메서드명
# ================================================================
API_CALL_PATTERNS = {
    "get", "post", "put", "delete", "patch", "head", "options",
    "request", "send",
}
# 이 모듈들의 메서드만 API 호출로 간주
API_MODULES = {"requests", "httpx", "aiohttp", "urllib"}

# ================================================================
# LLM 호출 패턴 — anthropic/openai SDK 메서드명
# ================================================================
LLM_CALL_PATTERNS = {
    "create", "complete", "chat", "generate", "messages",
}
LLM_MODULES = {"anthropic", "openai", "langchain", "litellm"}

# ================================================================
# URL 기반 LLM 재분류 — requests.post("https://api.anthropic.com/...") 탐지
# ================================================================
# requests.post로 LLM API를 직접 호출하는 경우, method가 "post"이므로
# API 호출로 분류됨. URL 인자에 아래 도메인이 포함되면 LLM 호출로 재분류.
LLM_API_DOMAINS = {
    "anthropic.com",
    "openai.com",
    "api.cohere.ai",
    "generativelanguage.googleapis.com",
}


def parse_code(source_code: str) -> ParseResult:
    """
    Python 코드 문자열을 파싱하여 에너지 분석에 필요한 정보를 추출

    파이프라인: 코드 문자열 → AST → ParseResult → analyzer.py

    Args:
        source_code: Python 소스 코드 문자열

    Returns:
        ParseResult — 함수별 분석 정보, DB/API/LLM 호출 목록
    """
    try:
        tree = ast.parse(source_code)
    except SyntaxError as e:
        return ParseResult(
            functions=[],
            total_lines=len(source_code.splitlines()),
            import_count=0,
            errors=[f"SyntaxError: {e}"],
        )

    # 전체 줄 수
    total_lines = len(source_code.splitlines())

    # import 개수
    import_count = sum(
        1 for node in ast.walk(tree)
        if isinstance(node, (ast.Import, ast.ImportFrom))
    )

    # 함수 단위 분석
    functions = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            func_info = _analyze_function(node)
            functions.append(func_info)

    # 전역 스코프(함수 밖) 호출 분석
    global_db, global_api, global_llm = _analyze_global_calls(tree)

    return ParseResult(
        functions=functions,
        total_lines=total_lines,
        import_count=import_count,
        global_db_calls=global_db,
        global_api_calls=global_api,
        global_llm_calls=global_llm,
    )


def _analyze_function(node: ast.FunctionDef) -> FunctionInfo:
    """
    단일 함수 노드를 분석하여 FunctionInfo 생성

    측정 항목:
    1. 루프 개수 + 최대 중첩 깊이 → Compute Energy
    2. 분기 개수 → 순환 복잡도 (CC)
    3. DB/API/LLM 호출 → Data/Token Energy
    """
    end_lineno = getattr(node, "end_lineno", node.lineno)

    info = FunctionInfo(
        name=node.name,
        lineno=node.lineno,
        end_lineno=end_lineno,
        line_count=end_lineno - node.lineno + 1,
    )

    # 캐시 데코레이터 탐지 (@lru_cache, @cache, @cached 등)
    # 캐싱이 있으면 반복 호출 시 실제 실행 없이 캐시 반환 → 에너지 절감
    info.has_cache_decorator = _has_cache_decorator(node)

    # 루프 분석 (중첩 깊이 포함)
    info.loop_count, info.nested_loop_depth = _count_loops(node)

    # 분기 분석 → 순환 복잡도
    info.branch_count = _count_branches(node)
    info.cyclomatic_complexity = 1 + info.branch_count + info.loop_count

    # DB/API/LLM 호출 분석
    info.db_calls = _find_calls(node, DB_CALL_PATTERNS, None)
    info.api_calls = _find_calls(node, API_CALL_PATTERNS, API_MODULES)
    info.llm_calls = _find_calls(node, LLM_CALL_PATTERNS, LLM_MODULES)

    # URL 기반 LLM 재분류:
    # requests.post("https://api.anthropic.com/...") 같은 호출은
    # method="post"이므로 api_calls에 들어감. URL에 LLM 도메인이 있으면 재분류.
    info.api_calls, reclassified = _reclassify_llm_by_url(
        node, info.api_calls
    )
    info.llm_calls.extend(reclassified)

    return info


def _has_cache_decorator(node: ast.FunctionDef) -> bool:
    """
    @lru_cache, @cache, @cached 등 캐시 데코레이터 탐지

    캐싱이 있으면 동일 인자 호출 시 실제 함수 실행 없이 캐시 반환.
    이는 특히 LLM API 호출에서 막대한 Token Energy 절감 효과.
    """
    cache_patterns = {"lru_cache", "cache", "cached", "memoize", "ttl_cache"}
    for decorator in node.decorator_list:
        # @lru_cache 또는 @lru_cache(maxsize=256)
        if isinstance(decorator, ast.Name) and decorator.id in cache_patterns:
            return True
        if isinstance(decorator, ast.Call):
            if isinstance(decorator.func, ast.Name) and decorator.func.id in cache_patterns:
                return True
            # @functools.lru_cache
            if isinstance(decorator.func, ast.Attribute) and \
               decorator.func.attr in cache_patterns:
                return True
    return False


def _count_loops(node: ast.AST) -> tuple[int, int]:
    """
    루프 개수 + 최대 중첩 깊이 계산

    O(n²) 중첩 루프 = depth 2 → Compute Energy 증가의 핵심 지표
    """
    loop_types = (ast.For, ast.While, ast.AsyncFor)
    total_loops = 0
    max_depth = 0

    def _walk_depth(n: ast.AST, current_depth: int):
        nonlocal total_loops, max_depth
        for child in ast.iter_child_nodes(n):
            if isinstance(child, loop_types):
                total_loops += 1
                new_depth = current_depth + 1
                if new_depth > max_depth:
                    max_depth = new_depth
                _walk_depth(child, new_depth)
            else:
                _walk_depth(child, current_depth)

    _walk_depth(node, 0)
    return total_loops, max_depth


def _count_branches(node: ast.AST) -> int:
    """
    분기(if/elif) 개수 → 순환 복잡도(CC) 산출에 사용

    CC = 1 + 분기 수 + 루프 수
    """
    branch_count = 0
    for child in ast.walk(node):
        if isinstance(child, ast.If):
            branch_count += 1
        elif isinstance(child, (ast.And, ast.Or)):
            # 복합 조건 (a and b) → 분기 +1
            branch_count += 1
    return branch_count


def _find_calls(
    node: ast.AST,
    method_patterns: set,
    module_filter: set | None,
) -> list[dict]:
    """
    AST에서 특정 패턴의 함수/메서드 호출을 찾기

    DB 호출: cursor.execute("SELECT ...") → {"method": "execute", "line": 45}
    API 호출: requests.post("http://...") → {"method": "post", "line": 67}
    LLM 호출: client.messages.create(...) → {"method": "create", "line": 92}
    """
    calls = []
    for child in ast.walk(node):
        if not isinstance(child, ast.Call):
            continue

        method_name = None
        module_hint = None

        # 패턴 1: obj.method() — cursor.execute(), requests.post()
        if isinstance(child.func, ast.Attribute):
            method_name = child.func.attr

            # 모듈 힌트 추출 (requests.post → "requests")
            if isinstance(child.func.value, ast.Name):
                module_hint = child.func.value.id
            elif isinstance(child.func.value, ast.Attribute):
                # 체이닝: client.messages.create → "messages"
                module_hint = child.func.value.attr

        # 패턴 2: function() — 단독 함수 호출
        elif isinstance(child.func, ast.Name):
            method_name = child.func.id

        if method_name and method_name in method_patterns:
            # 모듈 필터가 있으면 해당 모듈만 허용
            if module_filter and module_hint and module_hint not in module_filter:
                continue

            calls.append({
                "method": method_name,
                "line": getattr(child, "lineno", 0),
                "module_hint": module_hint,
            })

    return calls


def _reclassify_llm_by_url(
    node: ast.AST,
    api_calls: list[dict],
) -> tuple[list[dict], list[dict]]:
    """
    API 호출 중 URL에 LLM 도메인이 포함된 것을 LLM 호출로 재분류

    예: requests.post("https://api.anthropic.com/v1/messages", ...)
        → method="post"로 api_calls에 들어가지만
        → URL에 "anthropic.com" → LLM 호출로 재분류

    Returns:
        (남은 api_calls, 재분류된 llm_calls)
    """
    if not api_calls:
        return api_calls, []

    # AST에서 모든 Call 노드의 첫 번째 문자열 인자(URL) 수집
    url_by_line = {}
    for child in ast.walk(node):
        if not isinstance(child, ast.Call):
            continue
        lineno = getattr(child, "lineno", 0)
        # 첫 번째 위치 인자가 문자열이면 URL 후보
        if child.args and isinstance(child.args[0], ast.Constant):
            val = child.args[0].value
            if isinstance(val, str):
                url_by_line[lineno] = val

    remaining_api = []
    reclassified_llm = []

    for call in api_calls:
        url = url_by_line.get(call["line"], "")
        is_llm = any(domain in url for domain in LLM_API_DOMAINS)

        if is_llm:
            reclassified_llm.append({
                "method": call["method"],
                "line": call["line"],
                "module_hint": call["module_hint"],
                "url_hint": url,
                "reclassified": True,
            })
        else:
            remaining_api.append(call)

    return remaining_api, reclassified_llm


def _analyze_global_calls(tree: ast.Module) -> tuple[list, list, list]:
    """함수 밖 전역 스코프의 DB/API/LLM 호출 분석"""
    # 함수 내부 노드를 제외한 전역 스코프 노드만 추출
    func_types = (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)

    global_db = []
    global_api = []
    global_llm = []

    for node in ast.iter_child_nodes(tree):
        if isinstance(node, func_types):
            continue  # 함수/클래스 내부는 건너뛰기

        # 전역 스코프 노드에서 호출 패턴 탐지
        for child in ast.walk(node):
            if not isinstance(child, ast.Call):
                continue

            method_name = None
            module_hint = None

            if isinstance(child.func, ast.Attribute):
                method_name = child.func.attr
                if isinstance(child.func.value, ast.Name):
                    module_hint = child.func.value.id

            if method_name:
                call_info = {
                    "method": method_name,
                    "line": getattr(child, "lineno", 0),
                    "module_hint": module_hint,
                }
                if method_name in DB_CALL_PATTERNS:
                    global_db.append(call_info)
                if method_name in API_CALL_PATTERNS and module_hint in API_MODULES:
                    global_api.append(call_info)
                if method_name in LLM_CALL_PATTERNS and module_hint in LLM_MODULES:
                    global_llm.append(call_info)

    # 전역 API 호출에도 URL 기반 LLM 재분류 적용
    global_api, reclassified = _reclassify_llm_by_url(tree, global_api)
    global_llm.extend(reclassified)

    return global_db, global_api, global_llm
