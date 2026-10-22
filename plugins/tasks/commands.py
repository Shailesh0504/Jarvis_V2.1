# plugins/tasks/commands.py
"""Command actions supported by Tasks Plugin."""

from plugins.manifest import PluginAction, PluginParameter
from core.permissions import PermissionLevel, PluginCapability

ACTIONS = [
    # Existing Actions
    PluginAction(
        name="add_task",
        description="Creates a new task or todo item in Jarvis task list",
        keywords=["add task", "todo banao", "task note karo", "kaam likho", "new task"],
        parameters=[
            PluginParameter(name="title", type="string", description="Task description or title", required=True),
            PluginParameter(name="priority", type="string", description="Priority (low, normal, high, urgent)", required=False, default="normal"),
            PluginParameter(name="due_date", type="string", description="Optional due date (YYYY-MM-DD)", required=False, default="")
        ],
        required_permission=PermissionLevel.WRITE,
        required_capability=PluginCapability.OFFICE.value
    ),
    PluginAction(
        name="list_tasks",
        description="Lists all active and pending tasks",
        keywords=["list tasks", "show todos", "mere tasks dikhao", "pending kaam", "tasks list"],
        parameters=[
            PluginParameter(name="status", type="string", description="Status filter (pending, completed, all)", required=False, default="pending"),
            PluginParameter(name="limit", type="integer", description="Maximum tasks to return", required=False, default=15)
        ],
        required_permission=PermissionLevel.READ,
        required_capability=PluginCapability.OFFICE.value
    ),
    PluginAction(
        name="complete_task",
        description="Marks a task as completed",
        keywords=["complete task", "task complete karo", "kaam ho gaya", "done task", "mark task done"],
        parameters=[
            PluginParameter(name="task_id", type="integer", description="Task ID number", required=False, default=-1),
            PluginParameter(name="title", type="string", description="Task title keyword", required=False, default="")
        ],
        required_permission=PermissionLevel.WRITE,
        required_capability=PluginCapability.OFFICE.value
    ),

    # 10 New Actions
    PluginAction(
        name="delete_task",
        description="Permanently deletes a task from the list",
        keywords=["delete task", "remove task", "task hatao", "task delete karo"],
        parameters=[
            PluginParameter(name="task_id", type="integer", description="Task ID number", required=False, default=-1),
            PluginParameter(name="title", type="string", description="Task title keyword", required=False, default="")
        ],
        required_permission=PermissionLevel.WRITE,
        required_capability=PluginCapability.OFFICE.value
    ),
    PluginAction(
        name="update_task_title",
        description="Updates the title or description of an existing task",
        keywords=["update task", "edit task", "task badlo", "task change karo"],
        parameters=[
            PluginParameter(name="task_id", type="integer", description="Task ID number", required=True),
            PluginParameter(name="new_title", type="string", description="New task title", required=True)
        ],
        required_permission=PermissionLevel.WRITE,
        required_capability=PluginCapability.OFFICE.value
    ),
    PluginAction(
        name="set_task_priority",
        description="Sets or changes priority level of a task (low, normal, high, urgent)",
        keywords=["set task priority", "task priority badlo", "urgent task", "high priority task"],
        parameters=[
            PluginParameter(name="task_id", type="integer", description="Task ID number", required=True),
            PluginParameter(name="priority", type="string", description="Priority (low, normal, high, urgent)", required=True)
        ],
        required_permission=PermissionLevel.WRITE,
        required_capability=PluginCapability.OFFICE.value
    ),
    PluginAction(
        name="filter_tasks_by_priority",
        description="Filters and displays tasks by priority level",
        keywords=["filter tasks priority", "urgent tasks dikhao", "high priority tasks", "priority tasks"],
        parameters=[
            PluginParameter(name="priority", type="string", description="Priority level to filter", required=True)
        ],
        required_permission=PermissionLevel.READ,
        required_capability=PluginCapability.OFFICE.value
    ),
    PluginAction(
        name="clear_completed_tasks",
        description="Removes all completed tasks from the database",
        keywords=["clear completed tasks", "purge done tasks", "completed tasks hatao"],
        parameters=[],
        required_permission=PermissionLevel.WRITE,
        required_capability=PluginCapability.OFFICE.value
    ),
    PluginAction(
        name="set_task_due_date",
        description="Assigns or updates a due deadline date for a task",
        keywords=["set due date", "task deadline", "due date lagao", "task date"],
        parameters=[
            PluginParameter(name="task_id", type="integer", description="Task ID number", required=True),
            PluginParameter(name="due_date", type="string", description="Due date (YYYY-MM-DD)", required=True)
        ],
        required_permission=PermissionLevel.WRITE,
        required_capability=PluginCapability.OFFICE.value
    ),
    PluginAction(
        name="get_overdue_tasks",
        description="Lists all pending tasks whose deadline has passed",
        keywords=["overdue tasks", "late tasks", "overdue kaam", "missed deadline tasks"],
        parameters=[],
        required_permission=PermissionLevel.READ,
        required_capability=PluginCapability.OFFICE.value
    ),
    PluginAction(
        name="export_tasks_to_markdown",
        description="Exports tasks to a clean Markdown checklist (.md) file",
        keywords=["export tasks markdown", "tasks to md", "todo markdown export", "export todos"],
        parameters=[
            PluginParameter(name="output_path", type="string", description="Output .md file path", required=True)
        ],
        required_permission=PermissionLevel.WRITE,
        required_capability=PluginCapability.FILESYSTEM.value
    ),
    PluginAction(
        name="get_task_metrics",
        description="Calculates productivity metrics (total tasks, completion rate, overdue count)",
        keywords=["task metrics", "productivity stats", "task completion rate", "task stats"],
        parameters=[],
        required_permission=PermissionLevel.READ,
        required_capability=PluginCapability.OFFICE.value
    ),
    PluginAction(
        name="init_persistent_storage",
        description="Initializes or checks the persistent SQLite task database",
        keywords=["init tasks db", "check tasks storage", "tasks database status"],
        parameters=[],
        required_permission=PermissionLevel.READ,
        required_capability=PluginCapability.FILESYSTEM.value
    )
]
