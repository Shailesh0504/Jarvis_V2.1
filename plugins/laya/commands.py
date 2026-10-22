# plugins/laya/commands.py
"""Command actions supported by Laya plugin (voice + GUI share same manager)."""

from plugins.manifest import PluginAction, PluginParameter
from core.permissions import PermissionLevel, PluginCapability

ACTIONS = [
    PluginAction(
        name="laya_download",
        description="Download Laya System-1 model checkpoint (english/multilingual/typed-decisions)",
        keywords=[
            "laya download karo", "laya model download karo", "laya download",
            "download laya", "download laya model", "laya model le aao",
        ],
        parameters=[
            PluginParameter(name="checkpoint", type="string", description="english | multilingual | typed-decisions", required=False, default="multilingual")
        ],
        required_permission=PermissionLevel.EXECUTE,
        required_capability=PluginCapability.SYSTEM_CONTROL.value,
    ),
    PluginAction(
        name="laya_status",
        description="Report Laya model download / ready status",
        keywords=[
            "laya status", "laya model status", "laya ready hai",
            "laya downloaded hai", "laya ka status batao", "laya hai kya",
        ],
        parameters=[],
        required_permission=PermissionLevel.READ,
        required_capability=PluginCapability.SYSTEM_CONTROL.value,
    ),
    PluginAction(
        name="laya_test",
        description="Quick advisory decision test on given text (choice intent + guardrail screen)",
        keywords=[
            "laya test karo", "laya check karo", "laya kaam kar raha",
            "test laya", "laya decision test",
        ],
        parameters=[
            PluginParameter(name="text", type="string", description="Text to classify", required=False, default="chrome kholo")
        ],
        required_permission=PermissionLevel.READ,
        required_capability=PluginCapability.SYSTEM_CONTROL.value,
    ),
]
