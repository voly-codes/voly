"""Shared paths and template tokens for Smarty VOLY missions and tasks."""
from __future__ import annotations

import os

SMARTY_PROJECT = os.environ.get(
    "SMARTY_CRM_PATH",
    "/home/user1/smarty/smarty-crm-next",
)
SMARTY_REPORTS = f"{SMARTY_PROJECT}/docs/reports"
SMARTY_CLAUDE = f"{SMARTY_PROJECT}/CLAUDE.md"
PLANE_REF = f"{SMARTY_PROJECT}/rep/plane"
TRACKER_API = f"{SMARTY_PROJECT}/smarty-backend-stable/smarty-tracker/routes/index.js"
TRACKER_MODELS = f"{SMARTY_PROJECT}/smarty-backend-stable/smarty-tracker/models"
STICKIES_API = f"{SMARTY_PROJECT}/smarty-backend-stable/smarty-stickies/routes/index.js"
STICKIES_REF = f"{PLANE_REF}/apps/web/core/components/stickies"
HOME_REF = f"{PLANE_REF}/apps/web/core/components/home"
ANALYTICS_REF = f"{PLANE_REF}/apps/web/core/components/analytics"
PROFILE_SETTINGS_REF = f"{PLANE_REF}/apps/web/core/components/settings/profile"
AUTH_API = f"{SMARTY_PROJECT}/smarty-backend-stable/smarty-auth/docs/API.md"
NOTIF_API = f"{SMARTY_PROJECT}/smarty-backend-stable/smarty-notification/docs/API.md"
MEDIA_API = f"{SMARTY_PROJECT}/smarty-backend-stable/smarty-media/docs/API.md"
WORKSPACE_SETTINGS_SPEC = f"{SMARTY_PROJECT}/docs/specs/workspace-settings-integrations.md"
MEMBERS_PROVISIONING_SPEC = f"{SMARTY_PROJECT}/docs/specs/workspace-members-provisioning.md"
AI_ASSISTANT_SPEC = f"{SMARTY_PROJECT}/docs/specs/smarty-ai-assistant.md"
CONSULTANT_API = f"{SMARTY_PROJECT}/smarty-backend-stable/api-rest/routes/workspace/consultant.js"
BOT_HELPERS_API = f"{SMARTY_PROJECT}/smarty-backend-stable/api-rest/routes/workspace/bot-helpers.js"
PLANE_PI_CHAT_NAV = f"{PLANE_REF}/apps/web/core/components/workspace/sidebar/user-menu.tsx"
PLANE_PI_CHAT_NAV_ITEM = f"{PLANE_REF}/apps/web/core/components/workspace/sidebar/user-menu-item.tsx"
PLANE_GPT_ASSISTANT = f"{PLANE_REF}/apps/web/core/components/core/modals/gpt-assistant-popover.tsx"
PLANE_PI_CHAT_ICON = f"{PLANE_REF}/packages/propel/src/icons/sub-brand/pi-chat.tsx"
PLANE_AI_PATHS = f"{PLANE_REF}/apps/web/core/hooks/use-workspace-paths.ts"
PLANE_WORKSPACE_SHELL = f"{PLANE_REF}/apps/web/ce/components/workspace/content-wrapper.tsx"
PLANE_PI_CHAT_REFS = (
    "PLANE pi-chat / ai-chat (rep/plane — style only, never paste AGPL code):\n"
    f"  Sidebar nav: {PLANE_PI_CHAT_NAV}, {PLANE_PI_CHAT_NAV_ITEM}\n"
    f"  Composer UX: {PLANE_GPT_ASSISTANT} — rounded panel, text-13, AlertCircle disclaimer, primary action\n"
    f"  Icon: {PLANE_PI_CHAT_ICON} → src/components/icons/PiChatIcon.tsx (original SVG)\n"
    f"  Full-page layout hint: {PLANE_AI_PATHS} isAiPath — pi-chat route = minimal chrome, full-bleed thread\n"
    f"  Workspace shell: {PLANE_WORKSPACE_SHELL} — canvas bg, padded content area\n"
    "  PRODUCT REF (Plane AI chat screenshot — EE /pi-chat page, not in OSS repo):\n"
    "    TWO-PANE inside /assistant (NOT main CRM sidebar):\n"
    "    LEFT (~240–280px, bg-surface-0/1, border-r):\n"
    "      - Title row: «Plane AI» → Smarty: «AI-помощник Smarty» + PiChatIcon\n"
    "      - Primary «New chat» pill button (full width) + search icon button on right\n"
    "      - Section «Recents» label (text-xs muted)\n"
    "      - Thread list OR empty «No threads available»\n"
    "      - v1 Smarty: single consultant thread — show one active item or empty state\n"
    "    RIGHT (flex-1, centered content when empty):\n"
    "      - Top bar: model selector «Plane AI (GPT-3.5)» chevron → Smarty: read-only bot model/disclaimer\n"
    "      - Admin ⚙ links stay top-right (settings + usage)\n"
    "      - EMPTY: large heading «What can I do for you?» centered\n"
    "      - HERO COMPOSER: wide rounded-2xl card (~max-w-3xl), NOT bottom sticky when empty:\n"
    "          · context chip top-left (workspace name badge, like CODEOPS chip in Plane)\n"
    "          · placeholder «How can I help you today?»\n"
    "          · bottom toolbar: + attach stub, «Build» stub P2 disabled, mic stub P3\n"
    "          · blue square Send button (arrow up icon) bottom-right\n"
    "      - SUGGESTIONS below composer: label + rows with ↩ icon + full sentence prompts\n"
    "      - Footer disclaimer centered: «Plane AI can make mistakes…» → assistant.disclaimer\n"
    "    ACTIVE THREAD (messages exist):\n"
    "      - Messages scroll in main pane; composer moves to bottom sticky (same card style)\n"
    "  Tailwind tokens: rep/plane/packages/tailwind-config/variables.css\n"
)
PLANE_AI_UX = (
    "PLANE TRANSFER (style/patterns from rep/plane — never paste AGPL code):\n"
    f"  Nav: {PLANE_PI_CHAT_NAV} — pi-chat in user-menu strip (Home + Pi Chat), not CRM section\n"
    f"  Icon: {PLANE_PI_CHAT_ICON} — create src/components/icons/PiChatIcon.tsx (original SVG, same visual idea)\n"
    f"  Composer UX: {PLANE_GPT_ASSISTANT} — rounded-xl panel, text-13, disclaimer row, primary action\n"
    "  Tokens: surface-0/1 thread, border-subtle, brand accent, compact spacing (Plane dark-first)\n"
    "  Route: /assistant (+ App.tsx redirect /pi-chat → /assistant)\n"
    "  i18n: nav.piChat en+ru\n"
)
PLANE_PROJECTS_CARD = f"{PLANE_REF}/apps/web/core/components/project/card.tsx"
PLANE_PROJECTS_LIST = f"{PLANE_REF}/apps/web/app/(all)/[workspaceSlug]/(projects)/projects/(list)/"
PLANE_PROJECTS_HEADER = f"{PLANE_REF}/apps/web/ce/components/projects/header.tsx"
PLANE_PROJECTS_SIDEBAR = f"{PLANE_REF}/apps/web/core/components/workspace/sidebar/projects-list.tsx"
PLANE_WORKSPACE_MENU = f"{PLANE_REF}/apps/web/core/components/workspace/sidebar/workspace-menu.tsx"
PLANE_ACTIVE_CYCLES = f"{PLANE_REF}/apps/web/core/components/cycles/active-cycle/"
PLANE_ACTIVE_CYCLES_PAGE = f"{PLANE_REF}/apps/web/app/(all)/[workspaceSlug]/(projects)/active-cycles/"
PLANE_ALL_ISSUES = f"{PLANE_REF}/apps/web/core/components/issues/issue-layouts/roots/all-issue-layout-root.tsx"
PLANE_ANALYTICS_OVERVIEW = f"{ANALYTICS_REF}/overview/root.tsx"
PLANE_ANALYTICS_INSIGHT = f"{ANALYTICS_REF}/insight-card.tsx"
PLANE_ANALYTICS_TREND = f"{ANALYTICS_REF}/trend-piece.tsx"
PLANE_ANALYTICS_TOTAL = f"{ANALYTICS_REF}/total-insights.tsx"
PLANE_ANALYTICS_WORK_ITEMS = f"{ANALYTICS_REF}/work-items/"
PLANE_PROJECTS_UX = (
    "PLANE Projects → Smarty Tracker /tracker (style only, no AGPL copy):\n"
    f"  Project card grid: {PLANE_PROJECTS_CARD}\n"
    f"  List page layout: {PLANE_PROJECTS_LIST}, {PLANE_PROJECTS_HEADER}\n"
    f"  Sidebar projects strip: {PLANE_PROJECTS_SIDEBAR}\n"
    "  Smarty mapping: tracker_project = Plane project; route /tracker = projects hub\n"
)
PLANE_DASHBOARD_CHARTS_UX = (
    "PLANE workspace views → Smarty Dashboard widgets:\n"
    f"  active-cycles → Active sprints widget: {PLANE_ACTIVE_CYCLES} (progress, productivity, stats charts)\n"
    f"  active-cycles page: {PLANE_ACTIVE_CYCLES_PAGE}\n"
    f"  all-issues → All issues widget: {PLANE_ALL_ISSUES}, nav {PLANE_WORKSPACE_MENU}\n"
    "  Smarty backend: tracker sprints API (state=active), useAllTrackerIssues — NO Plane cycles API\n"
    f"  Chart styling: {PLANE_ANALYTICS_INSIGHT}, {PLANE_ANALYTICS_TREND}, {HOME_REF}/widgets/\n"
)
PLANE_ANALYTICS_UX = (
    "PLANE analytics/overview → Smarty /analytics (rename nav «Отчёты» → «Аналитика»):\n"
    f"  Overview layout: {PLANE_ANALYTICS_OVERVIEW} — TotalInsights + ProjectInsights grid\n"
    f"  Cards/trends: {PLANE_ANALYTICS_TOTAL}, {PLANE_ANALYTICS_TREND}, {PLANE_ANALYTICS_INSIGHT}\n"
    f"  Work-items charts: {PLANE_ANALYTICS_WORK_ITEMS} — priority-chart, created-vs-resolved\n"
    f"  Route: /analytics/overview default tab; /reports → redirect\n"
)
MARKET_API = f"{SMARTY_PROJECT}/smarty-backend-stable/api-rest/docs/API.md"
LEGACY_FRONTEND = f"{SMARTY_PROJECT}/smarty-crm-frontend"
LEGACY_FRONTEND_ROUTES = f"{LEGACY_FRONTEND}/src/js/components/Router/routesData.js"
LEGACY_FRONTEND_DOCS = f"{SMARTY_PROJECT}/docs/legacy-frontend"
LEGACY_GAP_AUDIT = f"{SMARTY_REPORTS}/legacy-gap-audit.md"
LEGACY_GAP_REF = (
    f"Gap audit: {LEGACY_GAP_AUDIT} §3–5. "
    f"Legacy ref: {LEGACY_FRONTEND}/src/, {LEGACY_FRONTEND_DOCS}/. "
    "Real API only, i18n en+ru, Plane dark-first."
)
LEGACY_MESSAGES_API = f"{LEGACY_FRONTEND}/src/js/actions/requests/messages.js"
LEGACY_EXTCHATS_API = f"{LEGACY_FRONTEND}/src/js/actions/requests/extchats.js"
LEGACY_EXTMESSAGES_API = f"{LEGACY_FRONTEND}/src/js/actions/requests/extmessages.js"
LEGACY_GROUP_SETTINGS = f"{LEGACY_FRONTEND}/src/js/components/GroupSettings"
LEGACY_BILLS = f"{LEGACY_FRONTEND}/src/js/components/Bill"
LEGACY_GROUPS_API = f"{LEGACY_FRONTEND_DOCS}/API.md"
GROUP_SETTINGS_SECTIONS = (
    "contacts → /contacts, projects/deals → /deals, assignments → /assignments, "
    "requisitions → /requisitions (legacy also notes/goals/service_notes — defer if no list page yet)."
)
BILLS_HOST_ENTITIES = (
    "contacts + projects (deals) first; assignments second; nested under EntityDetailTabs."
)
COMMS_PRODUCT_SPLIT = (
    "Product split in new app: /inbox «Входящие» = legacy /dialogs "
    "(internal team chats, wsApi dialogs + messages). "
    "/messages «Сообщения» = legacy /extchats "
    "(Telegram/WhatsApp/site widget via bots, wsApi extchats + extmessages). "
    "Legacy used one nav item (messagesTitle) for both — keep two routes but share UI primitives."
)
EMPLOYEES_API = f"{SMARTY_PROJECT}/smarty-backend-stable/api-rest/routes/workspace/employees.js"
ZITADEL_AUTH = f"{SMARTY_PROJECT}/smarty-backend-stable/smarty-auth/routes/zitadelAuth.js"

SMARTY_SYSTEM = f"""You are implementing Smarty CRM Next frontend.
Read {SMARTY_CLAUDE} first. Rules: React 19, Tailwind v4 dark-first, TanStack Query v5,
session cookies (withCredentials), workspace API via wsApi(wsId), i18n en+ru, named exports, cn() utility.
No mock data in production paths."""


def mission_context() -> dict[str, str]:
    """All {{VAR}} placeholders available in missions/*.yaml task bodies."""
    return {
        k: v
        for k, v in globals().items()
        if k.isupper() and isinstance(v, str)
    }
