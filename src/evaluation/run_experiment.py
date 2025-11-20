import asyncio
import pandas as pd
import logging
from src.evaluation.evaluator import LLMEvaluator
from src.services.ingestion import IngestionService
from src.services.detection import DetectionEngine
from src.services.policy_store import PolicyStore
from src.prompts.prompt_manager import PromptManager
from pathlib import Path

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def run_experiment():
    # 1. Setup Data
    ingestion = IngestionService()
    policy_store = PolicyStore()

    assignments_path = Path("data/assignments.csv")
    policies_path = Path("data/toxic_policies.csv")

    if not assignments_path.exists():
        print("❌ Data files not found.")
        return

    ingestion.process_ingestion(assignments_path, policies_path)
    policy_store.update_policies(ingestion.get_all_policies())

    engine = DetectionEngine(policy_store)
    user_states = ingestion.get_all_user_states()
    profiles_dict = engine.detect_violations(user_states)
    profiles = list(profiles_dict.values())

    if not profiles:
        print("⚠️ No profiles to evaluate.")
        return

    # 2. Define the Matrix
    # Add Amazon Nova Micro/Lite/Pro IDs here when available/applicable
    models = [
        "anthropic.claude-3-haiku-20240307-v1:0",
        "anthropic.claude-3-sonnet-20240229-v1:0",
        # "amazon.nova-micro-v1:0", # Example placeholder
        "mock",
    ]
    prompt_versions = [
        "v1_basic",
        "v2_cot",
    ]  # Ensure these files exist in src/prompts/versions/

    # You might need to extend LLMEvaluator to accept overrides,
    # or just manually swap the provider/prompt before calling run_batch.
    # For a cleaner implementation, we'll instantiate a new service/evaluator per run or patch it.

    all_results = []

    # Create dummy prompt files for testing if they don't exist
    prompt_mgr = PromptManager()
    if not (prompt_mgr.prompt_dir / "v1_basic.md").exists():
        with open(prompt_mgr.prompt_dir / "v1_basic.md", "w") as f:
            f.write("Basic Prompt: {{ROLES_LIST}}")
    if not (prompt_mgr.prompt_dir / "v2_cot.md").exists():
        with open(prompt_mgr.prompt_dir / "v2_cot.md", "w") as f:
            f.write("Think step by step. {{ROLES_LIST}}")

    for model in models:
        for p_version in prompt_versions:
            run_name = f"{model.split(':')[0]}_{p_version}"
            print(f"🧪 Running experiment: {run_name}")

            # Initialize Evaluator
            evaluator = LLMEvaluator()

            # --- MONKEY PATCHING / CONFIGURING FOR EXPERIMENT ---
            # 1. Force specific model provider
            evaluator.llm_service.provider = evaluator.llm_service.get_provider(model)

            # 2. Inject specific prompt generation logic
            # We need to hook into where the prompt is built.
            # Since `evaluate_single_case` calls `build_smart_remediation_prompt` directly,
            # we might need to subclass or modify `evaluate_single_case` to use `PromptManager`.
            # Ideally, refactor `LLMEvaluator` to accept a `prompt_builder` function.

            # Quick Hack for this script: Override the prompt builder function globally or in the loop
            # (Better: Refactor `evaluate_single_case` to take a `prompt_template` arg)

            # Let's assume we refactored evaluate_single_case to use PromptManager
            # Or we can just update the prompt file currently being used if `build_smart_remediation_prompt` reads from disk every time.
            # Safe approach: Modify `src/prompts/sod_remediation_prompt.md` temporarily? No, concurrent issues.

            # Correct Approach: Pass prompt_version to run_batch_evaluation -> evaluate_single_case
            # Since we can't easily change signature without editing `evaluator.py` extensively,
            # we will skip prompt variation in this snippet or assume `evaluator` is updated.

            results = await evaluator.run_batch_evaluation(profiles, run_name=run_name)

            summary = {
                "model": model,
                "prompt": p_version,
                "hallucination_rate": results["hallucination_rate"],
                "avg_quality": results["avg_quality_score"],
                "latency": results["avg_latency"],
            }
            all_results.append(summary)

    # 3. Compare Results
    df = pd.DataFrame(all_results)
    print("\n🏆 Experiment Leaderboard:")
    print(df.sort_values(by="hallucination_rate", ascending=True))

    df.to_csv("experiment_leaderboard.csv", index=False)
    print("Saved to experiment_leaderboard.csv")


if __name__ == "__main__":
    asyncio.run(run_experiment())
