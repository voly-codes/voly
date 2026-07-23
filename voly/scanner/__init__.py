"""
Project Scanner — автоматическое определение контекста проекта.

Определяет:
    - Язык программирования
    - Фреймворк
    - Архитектуру
    - Зависимости
    - CI/CD систему
    - Инфраструктуру
    - Кодовые соглашения

Формирует project profile, который становится project skills.

Запуск:
    voly scan
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

_PYPROJECT_TOML = "pyproject.toml"
_PACKAGE_JSON = "package.json"
_CSPROJ_GLOB = "*.csproj"
_CARGO_TOML = "Cargo.toml"
_GO_MOD = "go.mod"
_YAML_GLOB = "*.yaml"


@dataclass
class LanguageInfo:
    name: str
    version: str | None = None
    confidence: float = 1.0
    files: int = 0


@dataclass
class FrameworkInfo:
    name: str
    version: str | None = None
    confidence: float = 1.0


@dataclass
class CIInfo:
    provider: str
    config_file: str = ""
    pipeline_count: int = 0


@dataclass
class InfraInfo:
    docker: bool = False
    kubernetes: bool = False
    cloud_providers: list[str] = field(default_factory=list)
    databases: list[str] = field(default_factory=list)


@dataclass
class ProjectProfile:
    name: str
    path: str
    languages: list[LanguageInfo] = field(default_factory=list)
    frameworks: list[FrameworkInfo] = field(default_factory=list)
    package_managers: list[str] = field(default_factory=list)
    architecture: str = "unknown"
    ci: list[CIInfo] = field(default_factory=list)
    infrastructure: InfraInfo = field(default_factory=InfraInfo)
    test_frameworks: list[str] = field(default_factory=list)
    linter_tools: list[str] = field(default_factory=list)
    coding_conventions: list[str] = field(default_factory=list)
    detected_at: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "path": self.path,
            "languages": [{"name": l.name, "version": l.version, "confidence": l.confidence} for l in self.languages],
            "frameworks": [{"name": f.name, "version": f.version, "confidence": f.confidence} for f in self.frameworks],
            "package_managers": self.package_managers,
            "architecture": self.architecture,
            "ci": [{"provider": c.provider, "config_file": c.config_file, "pipelines": c.pipeline_count} for c in self.ci],
            "infrastructure": {
                "docker": self.infrastructure.docker,
                "kubernetes": self.infrastructure.kubernetes,
                "cloud_providers": self.infrastructure.cloud_providers,
                "databases": self.infrastructure.databases,
            },
            "test_frameworks": self.test_frameworks,
            "linter_tools": self.linter_tools,
            "coding_conventions": self.coding_conventions,
        }


LANGUAGE_DETECTORS: dict[str, dict[str, Any]] = {
    "python": {"files": [_PYPROJECT_TOML, "setup.py", "requirements.txt", "Pipfile"], "exts": [".py"], "pkg_mgr": "pip"},
    "typescript": {"files": ["tsconfig.json", "next.config.ts"], "exts": [".ts", ".tsx"], "pkg_mgr": "npm"},
    "javascript": {"files": [_PACKAGE_JSON], "exts": [".js", ".jsx", ".mjs"], "pkg_mgr": "npm"},
    "csharp": {"files": [_CSPROJ_GLOB, "*.sln"], "exts": [".cs"], "pkg_mgr": "dotnet"},
    "rust": {"files": [_CARGO_TOML], "exts": [".rs"], "pkg_mgr": "cargo"},
    "go": {"files": [_GO_MOD], "exts": [".go"], "pkg_mgr": "go"},
    "java": {"files": ["pom.xml", "build.gradle", "build.gradle.kts"], "exts": [".java"], "pkg_mgr": "maven"},
    "ruby": {"files": ["Gemfile"], "exts": [".rb"], "pkg_mgr": "bundler"},
}

FRAMEWORK_DETECTORS: dict[str, dict[str, Any]] = {
    "nextjs": {"files": ["next.config.ts", "next.config.js", "next.config.mjs"], "deps": ["next"], "langs": ["typescript", "javascript"]},
    "react": {"deps": ["react", "react-dom"], "langs": ["typescript", "javascript"]},
    "vue": {"deps": ["vue"], "langs": ["typescript", "javascript"]},
    "dotnet": {"files": [_CSPROJ_GLOB], "langs": ["csharp"]},
    "aspnet": {"files": ["Program.cs", "Startup.cs"], "langs": ["csharp"]},
    "django": {"deps": ["django"], "langs": ["python"]},
    "fastapi": {"deps": ["fastapi"], "langs": ["python"]},
    "flask": {"deps": ["flask"], "langs": ["python"]},
    "spring": {"deps": ["spring-boot"], "langs": ["java"]},
    "actix": {"deps": ["actix-web"], "langs": ["rust"]},
    "axum": {"deps": ["axum"], "langs": ["rust"]},
}

CI_DETECTORS: dict[str, list[str]] = {
    "github-actions": [".github/workflows"],
    "gitlab-ci": [".gitlab-ci.yml"],
    "jenkins": ["Jenkinsfile"],
    "circleci": [".circleci"],
    "azure-pipelines": ["azure-pipelines.yml"],
}

DB_DETECTORS: dict[str, list[str]] = {
    "postgresql": ["psycopg2", "asyncpg", "pg", "postgres", "npgsql", "diesel"],
    "mysql": ["mysql", "mysql2", "pymysql", "mysql-connector"],
    "sqlite": ["sqlite", "sqlite3", "better-sqlite3"],
    "mongodb": ["mongodb", "mongoose", "pymongo"],
    "redis": ["redis", "ioredis", "redis-py"],
    "elasticsearch": ["elasticsearch", "@elastic/elasticsearch"],
}

TEST_DETECTORS: dict[str, list[str]] = {
    "pytest": ["pytest", "conftest.py"],
    "jest": ["jest"],
    "vitest": ["vitest"],
    "xunit": ["xunit"],
    "nunit": ["nunit"],
    "rspec": ["rspec"],
    "gotest": ["testing (go)"],
}

LINTER_DETECTORS: dict[str, list[str]] = {
    "ruff": ["ruff"],
    "eslint": ["eslint"],
    "prettier": ["prettier"],
    "mypy": ["mypy"],
    "clippy": ["clippy"],
    "golangci-lint": ["golangci-lint"],
    "rubocop": ["rubocop"],
}


class ProjectScanner:
    def __init__(self, project_path: str | Path = "."):
        self.project_path = Path(project_path).resolve()
        self._file_cache: dict[str, bool] = {}
        self._content_cache: dict[str, str] = {}

    def scan(self) -> ProjectProfile:
        import time

        profile = ProjectProfile(
            name=self.project_path.name,
            path=str(self.project_path),
            detected_at=time.time(),
        )

        profile.languages = self._detect_languages()
        profile.package_managers = self._detect_package_managers()
        profile.frameworks = self._detect_frameworks(profile.languages)
        profile.ci = self._detect_ci()
        profile.infrastructure = self._detect_infrastructure()
        profile.test_frameworks = self._detect_test_frameworks()
        profile.linter_tools = self._detect_linter_tools()
        profile.architecture = self._detect_architecture(profile.languages, profile.frameworks)

        return profile

    def _file_exists(self, pattern: str) -> bool:
        if pattern in self._file_cache:
            return self._file_cache[pattern]

        if "*" in pattern:
            matches = list(self.project_path.glob(pattern))
            result = len(matches) > 0
        else:
            result = (self.project_path / pattern).exists()

        self._file_cache[pattern] = result
        return result

    def _read_file(self, path: str) -> str | None:
        if path in self._content_cache:
            return self._content_cache[path]
        full_path = self.project_path / path
        if full_path.exists():
            content = full_path.read_text()
            self._content_cache[path] = content
            return content
        return None

    def _detect_languages(self) -> list[LanguageInfo]:
        detected: list[LanguageInfo] = []
        for lang, spec in LANGUAGE_DETECTORS.items():
            score = 0
            for f in spec.get("files", []):
                if self._file_exists(f):
                    score += 2

            exts = spec.get("exts", [])
            ext_count = 0
            for ext in exts:
                count = len(list(self.project_path.rglob(f"*{ext}")))
                ext_count += count
            if ext_count > 0:
                score += min(ext_count, 10)

            if score > 0:
                info = LanguageInfo(name=lang, confidence=min(score / 10, 1.0), files=ext_count)
                version = self._detect_lang_version(lang)
                if version:
                    info.version = version
                detected.append(info)

        detected.sort(key=lambda x: x.confidence, reverse=True)
        return detected

    def _detect_lang_version(self, lang: str) -> str | None:
        version_markers: dict[str, tuple[str, str]] = {
            "python": (_PYPROJECT_TOML, r'requires-python\s*=\s*">=([\d.]+)"'),
            "rust": (_CARGO_TOML, r'edition\s*=\s*"(\d+)"'),
            "csharp": (_CSPROJ_GLOB, r'TargetFramework[^>]*>net([\d.]+)<'),
            "go": (_GO_MOD, r'go\s+([\d.]+)'),
        }
        if lang in version_markers:
            marker_file, pattern = version_markers[lang]
            content = self._read_file(marker_file)
            if content:
                import re
                match = re.search(pattern, content)
                if match:
                    return match.group(1)
        return None

    def _detect_package_managers(self) -> list[str]:
        managers = []
        pm_markers = {
            "npm": [_PACKAGE_JSON],
            "pnpm": ["pnpm-lock.yaml"],
            "yarn": ["yarn.lock"],
            "pip": ["requirements.txt", "setup.py"],
            "uv": ["uv.lock"],
            "poetry": ["pyproject.toml:poetry"],
            "cargo": [_CARGO_TOML],
            "dotnet": [_CSPROJ_GLOB],
            "maven": ["pom.xml"],
            "gradle": ["build.gradle", "build.gradle.kts"],
            "bundler": ["Gemfile"],
            "go": [_GO_MOD],
        }

        pyproject = self._read_file(_PYPROJECT_TOML)
        if pyproject:
            if "poetry" in pyproject:
                managers.append("poetry")
            if "setuptools" in pyproject or "hatchling" in pyproject or "flit" in pyproject:
                if "pip" not in managers:
                    managers.append("pip")
            if "[tool.uv" in pyproject:
                if "uv" not in managers:
                    managers.append("uv")

        for pm, markers in pm_markers.items():
            for marker in markers:
                if ":" in marker:
                    continue
                if self._file_exists(marker):
                    if pm not in managers:
                        managers.append(pm)
                    break
        return managers

    def _detect_frameworks(self, languages: list[LanguageInfo]) -> list[FrameworkInfo]:
        detected: list[FrameworkInfo] = []
        for fw, spec in FRAMEWORK_DETECTORS.items():
            score = 0
            for f in spec.get("files", []):
                if self._file_exists(f):
                    score += 3
            for dep in spec.get("deps", []):
                content = self._read_file(_PACKAGE_JSON) or self._read_file(_PYPROJECT_TOML) or ""
                if dep in content:
                    score += 2
            lang_names = {l.name for l in languages}
            req_langs = set(spec.get("langs", []))
            if not req_langs or (req_langs & lang_names):
                score += 1

            if score > 1:
                detected.append(FrameworkInfo(name=fw, confidence=min(score / 6, 1.0)))

        detected.sort(key=lambda x: x.confidence, reverse=True)
        return detected

    def _detect_ci(self) -> list[CIInfo]:
        ci_list = []
        for provider, markers in CI_DETECTORS.items():
            for marker in markers:
                if self._file_exists(marker):
                    count = 0
                    if provider == "github-actions":
                        wf_dir = self.project_path / ".github" / "workflows"
                        if wf_dir.exists():
                            count = len(list(wf_dir.glob("*.yml"))) + len(list(wf_dir.glob(_YAML_GLOB)))
                    ci_list.append(CIInfo(provider=provider, config_file=marker, pipeline_count=count))
                    break
        return ci_list

    def _detect_infrastructure(self) -> InfraInfo:
        infra = InfraInfo()
        if self._file_exists("Dockerfile"):
            infra.docker = True
        if self._file_exists("docker-compose.yml") or self._file_exists("docker-compose.yaml"):
            infra.docker = True
        if self._file_exists("k8s") or list(self.project_path.glob(_YAML_GLOB)):
            infra.kubernetes = any(
                content and "kind:" in content
                for path in self.project_path.rglob(_YAML_GLOB)
                for content in [self._read_file(str(path.relative_to(self.project_path)))]
            )

        cloud_markers = {
            "aws": ["serverless.yml", "template.yaml"],
            "gcp": ["app.yaml", "cloudbuild.yaml"],
            "azure": ["azure-pipelines.yml"],
            "cloudflare": ["wrangler.toml"],
            "vercel": ["vercel.json"],
        }
        for cloud, markers in cloud_markers.items():
            for marker in markers:
                if self._file_exists(marker):
                    infra.cloud_providers.append(cloud)
                    break

        for db, deps in DB_DETECTORS.items():
            for dep in deps:
                for manifest in [_PACKAGE_JSON, _PYPROJECT_TOML, _CARGO_TOML, "Gemfile", _GO_MOD]:
                    content = self._read_file(manifest)
                    if content and dep.lower() in content.lower():
                        if db not in infra.databases:
                            infra.databases.append(db)

        return infra

    def _detect_test_frameworks(self) -> list[str]:
        detected = []
        for tfw, markers in TEST_DETECTORS.items():
            for marker in markers:
                for manifest in [_PACKAGE_JSON, _PYPROJECT_TOML, _CARGO_TOML, "Gemfile", _GO_MOD]:
                    content = self._read_file(manifest)
                    if content and marker.lower() in content.lower():
                        if tfw not in detected:
                            detected.append(tfw)
        return detected

    def _detect_linter_tools(self) -> list[str]:
        detected = []
        for linter, markers in LINTER_DETECTORS.items():
            for marker in markers:
                for manifest in [_PACKAGE_JSON, _PYPROJECT_TOML, _CARGO_TOML]:
                    content = self._read_file(manifest)
                    if content and marker.lower() in content.lower():
                        if linter not in detected:
                            detected.append(linter)
        return detected

    def _detect_architecture(
        self, languages: list[LanguageInfo], frameworks: list[FrameworkInfo]
    ) -> str:
        fw_names = {f.name for f in frameworks}
        if "nextjs" in fw_names:
            return "fullstack-ssr"
        if "react" in fw_names or "vue" in fw_names:
            return "spa-backend"
        if "fastapi" in fw_names or "django" in fw_names or "flask" in fw_names:
            return "api-backend"
        if "aspnet" in fw_names or "spring" in fw_names:
            return "enterprise-backend"
        if self._file_exists("docker-compose.yml"):
            return "microservices"
        if len(languages) >= 3:
            return "polyglot"
        return "monolith"


def generate_project_skills(profile: ProjectProfile) -> list[dict[str, Any]]:
    import time
    import hashlib

    skills = []

    skills.append({
        "id": f"proj-arch-{hashlib.sha256(profile.name.encode()).hexdigest()[:8]}",
        "name": f"Project Architecture: {profile.name}",
        "description": f"Архитектура проекта: {profile.architecture}",
        "source": "project",
        "tags": ["project", "architecture", profile.architecture],
        "capabilities": ["architecture", "system-design"],
        "content": f"Проект {profile.name}: {profile.architecture}. Языки: {', '.join(l.name for l in profile.languages)}.",
    })

    for lang in profile.languages:
        skills.append({
            "id": f"proj-lang-{lang.name}-{hashlib.sha256(profile.name.encode()).hexdigest()[:8]}",
            "name": f"Language: {lang.name}",
            "description": f"Проект использует {lang.name}" + (f" {lang.version}" if lang.version else ""),
            "source": "project",
            "tags": ["project", "language", lang.name],
            "compatible_languages": [lang.name],
            "content": f"Язык проекта: {lang.name}. Конвенции и паттерны соответствуют стандартам {lang.name}.",
        })

    for fw in profile.frameworks:
        skills.append({
            "id": f"proj-fw-{fw.name}-{hashlib.sha256(profile.name.encode()).hexdigest()[:8]}",
            "name": f"Framework: {fw.name}",
            "description": f"Проект использует {fw.name}",
            "source": "project",
            "tags": ["project", "framework", fw.name],
            "compatible_frameworks": [fw.name],
            "content": f"Фреймворк проекта: {fw.name}. Следуй best practices {fw.name}.",
        })

    for con in profile.coding_conventions:
        skills.append({
            "id": f"proj-conv-{hashlib.sha256(con.encode()).hexdigest()[:8]}",
            "name": f"Convention: {con}",
            "description": f"Кодовое соглашение: {con}",
            "source": "project",
            "tags": ["project", "convention", con],
            "content": f"Соглашение проекта: {con}",
        })

    return skills
