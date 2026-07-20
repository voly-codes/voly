"""Central registry of local multi-agent role definitions."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

RoleMode = Literal["chat", "executor"]

_FILE_LINE_POLICY = (
    "File size policy: every created/modified file must stay within 300 lines of code. "
    "Up to 500 lines is allowed only when the architect explicitly approved it in the plan "
    "with two separate lines: `FILE_LINE_LIMIT: 500` and `FILE_LINE_LIMIT_REASON: <rationale>`."
)


@dataclass
class RoleDefinition:
    id: str
    tier: str                          # premium | standard | cheap
    mode: RoleMode                     # chat | executor
    system_prompt: str
    default_executor: str = ""
    provider_offset: int = 0
    inject_prior_context: bool = False
    decomposer_signals: list[str] = field(default_factory=list)
    capability_requirements: dict[str, str] = field(default_factory=dict)


ROLE_REGISTRY: dict[str, RoleDefinition] = {
    "architect": RoleDefinition(
        id="architect",
        tier="standard",
        mode="chat",
        system_prompt=(
            "You are a senior software architect. Design the architecture: modules, interfaces, "
            "data flow, key decisions, and risks. Plan only — NO full code "
            "(no ``` blocks and no file content listings). "
            f"{_FILE_LINE_POLICY}"
        ),
        provider_offset=0,
    ),
    "developer": RoleDefinition(
        id="developer",
        tier="standard",
        mode="executor",
        system_prompt=(
            "You are a senior developer. Implement the solution in the project files following "
            "the architecture plan. Do not paste the full code into your reply — give a brief "
            f"summary of the changes. {_FILE_LINE_POLICY}"
        ),
        default_executor="cursor",
        provider_offset=1,
    ),
    "tester": RoleDefinition(
        id="tester",
        tier="standard",
        mode="executor",
        system_prompt=(
            "You are a QA engineer. Write tests (pytest if Python) covering happy-path, "
            f"boundary, and negative cases. {_FILE_LINE_POLICY}"
        ),
        default_executor="cursor",
        provider_offset=2,
    ),
    "reviewer": RoleDefinition(
        id="reviewer",
        tier="premium",
        mode="chat",
        system_prompt=(
            "You are a code reviewer. Assess the code and tests: bugs, security, "
            "readability, performance. Give concrete remarks and a verdict."
        ),
        provider_offset=1,
    ),
    "devops": RoleDefinition(
        id="devops",
        tier="cheap",
        mode="executor",
        system_prompt=(
            "You are a DevOps engineer. Prepare the deployment: Dockerfile/compose, "
            "CI steps, environment variables, release checklist."
        ),
        default_executor="cursor",
        provider_offset=0,
    ),
    "security": RoleDefinition(
        id="security",
        tier="premium",
        mode="chat",
        system_prompt=(
            "You are an application security engineer. Find vulnerabilities in the code "
            "and propose fixes."
        ),
        provider_offset=0,
    ),
    "bugfixer": RoleDefinition(
        id="bugfixer",
        tier="standard",
        mode="executor",
        system_prompt=(
            "You are a specialist engineer. Complete the assigned sub-task with quality and brevity."
        ),
        default_executor="deepseek",
        provider_offset=2,
    ),
    "ui_architect": RoleDefinition(
        id="ui_architect",
        tier="standard",
        mode="chat",
        system_prompt=(
            "You are a senior UI architect. Design component structure, state management, "
            "routing, and visual hierarchy. Plan only — no full code implementations. "
            + _FILE_LINE_POLICY
        ),
        provider_offset=0,
        decomposer_signals=[
            "ui", "component", "svelte", "react", "frontend", "design system", "layout",
        ],
        capability_requirements={"frontend": ">= 0.70"},
    ),
    "visual_reviewer": RoleDefinition(
        id="visual_reviewer",
        tier="premium",
        mode="chat",
        system_prompt=(
            "You are a visual design reviewer. Review UI components for: pixel accuracy, "
            "accessibility (WCAG 2.1 AA), responsive behavior, and design system consistency. "
            "Provide concrete, actionable feedback."
        ),
        provider_offset=1,
        inject_prior_context=True,
        decomposer_signals=[
            "screenshot", "visual", "design", "figma", "ui review",
            "accessibility", "pixel",
        ],
        capability_requirements={"frontend": ">= 0.75", "image_input": "true"},
    ),
    "browser_tester": RoleDefinition(
        id="browser_tester",
        tier="standard",
        mode="executor",
        system_prompt=(
            "You are a browser testing engineer. Write end-to-end tests using Playwright "
            "or Cypress. Test user flows, visual regressions, and cross-browser compatibility. "
            + _FILE_LINE_POLICY
        ),
        default_executor="cursor",
        provider_offset=2,
        decomposer_signals=[
            "e2e", "playwright", "cypress", "browser test", "visual regression", "ui test",
        ],
        capability_requirements={"frontend": ">= 0.70", "browser_tools": "true"},
    ),
    "ux_reviewer": RoleDefinition(
        id="ux_reviewer",
        tier="cheap",
        mode="chat",
        system_prompt=(
            "You are a UX reviewer. Evaluate user flows, information architecture, "
            "and interaction patterns. Focus on usability, learnability, and friction points."
        ),
        provider_offset=0,
        inject_prior_context=True,
        decomposer_signals=[
            "ux", "user experience", "usability", "user flow", "interaction", "onboarding",
        ],
        capability_requirements={"frontend": ">= 0.55"},
    ),
}
