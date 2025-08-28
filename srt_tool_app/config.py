"""
Application Configuration and Policy Definitions
"""

# This file is currently a placeholder for potential future configurations.
# The main application logic for policies is now handled by selecting
# different prompt files from the `prompts` directory.

# The only application-level policy that is not part of the prompt
# is the multi-line splitting feature. Its default is set in the GUI.
APP_LOGIC_DEFAULTS = {
    "split_multi_line": True
}
