"""
LLM prompt templates for toxic combination justifications.
"""
from pathlib import Path
from src.models import UserViolationProfile


def load_prompt_template() -> str:
    """
    Load the advanced SoD remediation prompt template from markdown file.
    
    Returns:
        str: The complete prompt template with placeholders
    """
    template_path = Path(__file__).parent / "sod_remediation_prompt.md"
    
    try:
        with open(template_path, 'r', encoding='utf-8') as f:
            return f.read()
    except FileNotFoundError:
        raise FileNotFoundError(
            f"Prompt template not found at: {template_path}. "
            "Please ensure 'sod_remediation_prompt.md' is in the same directory."
        )


def build_smart_remediation_prompt(
    profile: UserViolationProfile
) -> str:
    """
    Builds a "smart" prompt for the LLM to analyze *all* of a
    user's violations and find the optimal remediation.
    This version uses the advanced markdown template.
    
    Args:
        profile: UserViolationProfile containing user info and violations
        
    Returns:
        str: Complete formatted prompt ready for LLM
    """
    # Load the base template from .md file
    base_template = load_prompt_template()
    
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
    prompt = base_template.replace("{{DEPARTMENT}}", profile.user.department)
    prompt = prompt.replace("{{ROLES_LIST}}", all_roles_str)
    prompt = prompt.replace("{{VIOLATIONS_LIST}}", violations_str)
    
    return prompt
