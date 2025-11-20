from pathlib import Path


class PromptManager:
    def __init__(self, prompt_dir: str = "src/prompts/versions"):
        self.prompt_dir = Path(prompt_dir)
        # Create directory if it doesn't exist (for safety)
        self.prompt_dir.mkdir(parents=True, exist_ok=True)

    def load_template(self, version: str) -> str:
        """Load a specific prompt version (e.g., 'v1_basic')."""
        path = self.prompt_dir / f"{version}.md"
        if not path.exists():
            raise FileNotFoundError(f"Prompt version {version} not found at {path}")

        with open(path, "r", encoding="utf-8") as f:
            return f.read()

    def build_prompt(self, version: str, profile) -> str:
        template = self.load_template(version)
        return self._inject_context(template, profile)

    def _inject_context(self, template: str, profile) -> str:
        # Format the user's active roles with metadata
        all_roles_str = "\n".join(
            f"- '{role.role}' (from '{role.source_system}', granted: {role.granted_at.date().isoformat()})"
            for role in profile.user.active_roles.values()
        )

        # Format the list of policies they violated
        violations_str = "\n".join(
            f"- Policy {p.policy_id} ({p.description}): Requires roles [{', '.join(p.roles)}]"
            for p in profile.violated_policies
        )

        # Replace placeholders in the template
        prompt = template.replace("{{DEPARTMENT}}", profile.user.department)
        prompt = prompt.replace("{{ROLES_LIST}}", all_roles_str)
        prompt = prompt.replace("{{VIOLATIONS_LIST}}", violations_str)

        return prompt
