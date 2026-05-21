
from enum import Enum

class RunStatus(str, Enum):
    PENDING   = "pending"
    RUNNING   = "running"
    COMPLETED = "completed"
    FAILED    = "failed"
    CANCELLED = "cancelled"

class CheckStatus(str, Enum):
    PENDING  = "pending"
    RUNNING  = "running"
    PASS     = "pass"
    FAIL     = "fail"
    ERROR    = "error"
    SKIPPED  = "skipped"


class AgentName(str, Enum):
    ORCHESTRATOR = "orchestrator"
    RENDER       = "render"
    VISUAL       = "visual"
    ISI          = "isi"
    INTERACTION  = "interaction"
    PERFORMANCE  = "performance"


class CheckID(str, Enum):
    BANNER_VISIBLE          = "banner_visible"
    BORDER_DETECTED         = "border_detected"
    COPY_SELECTION_DISABLED = "copy_selection_disabled"
    ISI_AUTO_SCROLL         = "isi_auto_scroll"
    ISI_TEXT_LAYOUT         = "isi_text_layout"
    ISI_WHEEL_SCROLL        = "isi_wheel_scroll"
    BANNER_LOAD_TIME        = "banner_load_time"


CHECK_AGENT_MAP: dict[CheckID, AgentName] = {
    CheckID.BANNER_VISIBLE:          AgentName.RENDER,
    CheckID.BORDER_DETECTED:         AgentName.VISUAL,
    CheckID.COPY_SELECTION_DISABLED: AgentName.INTERACTION,
    CheckID.ISI_AUTO_SCROLL:         AgentName.ISI,
    CheckID.ISI_TEXT_LAYOUT:         AgentName.ISI,
    CheckID.ISI_WHEEL_SCROLL:        AgentName.ISI,
    CheckID.BANNER_LOAD_TIME:        AgentName.PERFORMANCE,
}

CHECK_LABELS: dict[CheckID, str] = {
    CheckID.BANNER_VISIBLE:          "Banner Visible",
    CheckID.BORDER_DETECTED:         "Border Detected",
    CheckID.COPY_SELECTION_DISABLED: "Copy Selection Disabled",
    CheckID.ISI_AUTO_SCROLL:         "ISI Auto-Scroll",
    CheckID.ISI_TEXT_LAYOUT:         "ISI Text Layout",
    CheckID.ISI_WHEEL_SCROLL:        "ISI Wheel Scroll & Isolation",
    CheckID.BANNER_LOAD_TIME:        "Banner Load Time",
}
