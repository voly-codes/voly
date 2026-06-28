"""
DSPy Signatures for CodeOps agents.

Each Signature is a typed contract: InputField(s) → OutputField(s).
DSPy uses these to generate prompts and validate structured outputs.

Design choices:
  - All signatures are pure dataclasses, no dspy import at module level.
    This allows importing signatures.py without dspy installed.
  - The actual dspy.Signature subclasses are constructed lazily via
    build_*() factory functions that guard with _require_dspy().
"""

from __future__ import annotations

_DSPY_AVAILABLE = False
try:
    import dspy  # noqa: F401
    _DSPY_AVAILABLE = True
except ImportError:
    pass


def _require_dspy() -> None:
    if not _DSPY_AVAILABLE:
        raise ImportError("DSPy is not installed. Run: pip install codeops[dspy]")


# ---------------------------------------------------------------------------
# 1. Task Routing
# ---------------------------------------------------------------------------

def build_route_task_signature() -> type:
    """DSPy Signature: route a developer task to the best CodeOps agent."""
    _require_dspy()
    import dspy

    class RouteTask(dspy.Signature):
        """Route a developer task to the best CodeOps agent, model and tools.

        Consider the task description and project context carefully.
        Return the most appropriate agent role and complexity assessment.
        """

        task: str = dspy.InputField(desc="The developer task description")
        project_context: str = dspy.InputField(
            desc="Brief context about the project (language, framework, etc.)"
        )

        agent: str = dspy.OutputField(
            desc=(
                "Best agent for this task: "
                "architect | developer | reviewer | tester | security | "
                "devops | documenter | product | bugfixer"
            )
        )
        complexity: str = dspy.OutputField(desc="Task complexity: low | medium | high")
        tools: list[str] = dspy.OutputField(
            desc="List of tools needed (e.g. github, temporal, wiki). Empty list if none."
        )
        confidence: float = dspy.OutputField(
            desc="Routing confidence score between 0.0 and 1.0"
        )
        reason: str = dspy.OutputField(
            desc="One-sentence explanation for the routing decision"
        )

    return RouteTask


# ---------------------------------------------------------------------------
# 2. Code Review
# ---------------------------------------------------------------------------

def build_review_code_signature() -> type:
    """DSPy Signature: structured code review of a diff."""
    _require_dspy()
    import dspy

    class ReviewCode(dspy.Signature):
        """Review code changes and return structured findings.

        Analyze the diff thoroughly. Identify bugs, security issues, and risks.
        Suggest a patch only when the fix is clear and unambiguous.
        """

        task: str = dspy.InputField(desc="The review task or PR description")
        diff: str = dspy.InputField(desc="The git diff or code changes to review")
        project_context: str = dspy.InputField(
            desc="Project context: language, framework, coding standards"
        )

        summary: str = dspy.OutputField(
            desc="Short summary of what the change does and overall quality"
        )
        risks: list[str] = dspy.OutputField(
            desc="List of risks or concerns (performance, maintainability, etc.)"
        )
        bugs: list[str] = dspy.OutputField(
            desc="List of actual bugs found with file:line references where possible"
        )
        security_issues: list[str] = dspy.OutputField(
            desc="List of security vulnerabilities (OWASP, secrets, injections, etc.)"
        )
        suggested_patch: str = dspy.OutputField(
            desc=(
                "Unified diff patch for fixes, or empty string if no clear fix. "
                "Format: --- a/file\\n+++ b/file\\n@@ ... @@"
            )
        )

    return ReviewCode


# ---------------------------------------------------------------------------
# 3. Architecture Analysis
# ---------------------------------------------------------------------------

def build_architecture_analysis_signature() -> type:
    """DSPy Signature: analyze repository architecture and propose changes."""
    _require_dspy()
    import dspy

    class ArchitectureAnalysis(dspy.Signature):
        """Analyze a repository architecture and propose safe, incremental changes.

        Be conservative — prefer additive changes over breaking refactors.
        Migration plan steps must be independently deployable.
        """

        task: str = dspy.InputField(desc="The architecture task or question")
        files_summary: str = dspy.InputField(
            desc="Summary of key files and their roles in the repository"
        )
        current_architecture: str = dspy.InputField(
            desc="Current architecture description or ADR"
        )

        diagnosis: str = dspy.OutputField(
            desc="Diagnosis of current architecture: strengths and pain points"
        )
        proposed_design: str = dspy.OutputField(
            desc="Proposed new design with rationale"
        )
        migration_plan: list[str] = dspy.OutputField(
            desc="Ordered list of migration steps, each independently deployable"
        )
        risks: list[str] = dspy.OutputField(
            desc="Risks and mitigations for the proposed change"
        )

    return ArchitectureAnalysis


# ---------------------------------------------------------------------------
# 4. Documentation Generation
# ---------------------------------------------------------------------------

def build_generate_docs_signature() -> type:
    """DSPy Signature: generate technical documentation from source."""
    _require_dspy()
    import dspy

    class GenerateDocs(dspy.Signature):
        """Generate clear technical documentation from source code and architecture notes.

        Write for developers who are onboarding to the project.
        Be concise. Avoid repeating what is obvious from the code.
        """

        task: str = dspy.InputField(desc="Documentation task description")
        source_context: str = dspy.InputField(
            desc="Relevant source code snippets and architecture notes"
        )

        title: str = dspy.OutputField(desc="Document title")
        overview: str = dspy.OutputField(
            desc="1-3 sentence overview of what this component does"
        )
        architecture: str = dspy.OutputField(
            desc="Architecture description: key components and their relationships"
        )
        usage: str = dspy.OutputField(
            desc="Usage examples with code snippets"
        )
        limitations: str = dspy.OutputField(
            desc="Known limitations, caveats, or gotchas"
        )

    return GenerateDocs


# ---------------------------------------------------------------------------
# 5. Bug Analysis
# ---------------------------------------------------------------------------

def build_analyze_bug_signature() -> type:
    """DSPy Signature: analyze a bug report and propose a fix."""
    _require_dspy()
    import dspy

    class AnalyzeBug(dspy.Signature):
        """Analyze a bug report and produce a targeted fix.

        Prefer minimal, surgical fixes. Do not refactor unrelated code.
        Root cause must be specific — not 'null pointer' but which exact variable.
        """

        task: str = dspy.InputField(desc="Bug description or error message")
        code_context: str = dspy.InputField(
            desc="Relevant source code around the bug location"
        )
        stack_trace: str = dspy.InputField(
            desc="Stack trace or error log if available, else empty string"
        )

        root_cause: str = dspy.OutputField(
            desc="Precise root cause of the bug"
        )
        fix_description: str = dspy.OutputField(
            desc="Plain-language description of the fix"
        )
        patch: str = dspy.OutputField(
            desc="Unified diff patch implementing the fix"
        )
        test_suggestion: str = dspy.OutputField(
            desc="Suggested test case to prevent regression"
        )

    return AnalyzeBug


# Registry: agent name → signature factory
AGENT_SIGNATURES: dict[str, callable] = {
    "reviewer": build_review_code_signature,
    "architect": build_architecture_analysis_signature,
    "documenter": build_generate_docs_signature,
    "bugfixer": build_analyze_bug_signature,
}

ROUTING_SIGNATURE = build_route_task_signature
