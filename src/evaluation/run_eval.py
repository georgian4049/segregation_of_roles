import asyncio
import logging
import sys
from pathlib import Path
from src.services.ingestion import IngestionService
from src.services.detection import DetectionEngine
from src.services.policy_store import PolicyStore
from src.evaluation.evaluator import LLMEvaluator
from src.config import settings

# Configure simple logging for the script
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)


async def main():
    print("🚀 Starting LLM Evaluation Framework...")

    # 1. Setup Data
    # We rely on your existing logic to load the "Small" or "Seed" dataset
    ingestion = IngestionService()
    policy_store = PolicyStore()

    # Use the files already in your 'data' folder
    assignments_path = Path("data/assignments.csv")
    policies_path = Path("data/toxic_policies.csv")

    if not assignments_path.exists() or not policies_path.exists():
        print("❌ Error: data/assignments.csv or data/toxic_policies.csv not found.")
        sys.exit(1)

    print(f"📂 Loading data from {assignments_path}")
    ingestion.process_ingestion(assignments_path, policies_path)
    policy_store.update_policies(ingestion.get_all_policies())

    # 2. Generate Test Cases (User Profiles)
    engine = DetectionEngine(policy_store)
    user_states = ingestion.get_all_user_states()
    profiles_dict = engine.detect_violations(user_states)
    profiles = list(profiles_dict.values())

    if not profiles:
        print("⚠️ No violations found in dataset. Cannot run evaluation.")
        sys.exit(0)

    print(f"✅ Generated {len(profiles)} test cases (violation profiles).")

    # 3. Run Evaluation
    evaluator = LLMEvaluator()

    # IMPORTANT: Ensure we are using the right LLM setting
    print(f"🤖 Evaluating using provider: {settings.llm_provider}")
    if settings.use_mock_llm:
        print("   (Using MOCK mode - results check logic, not model intelligence)")

    await evaluator.run_batch_evaluation(profiles, run_name="ci_test_run")


if __name__ == "__main__":
    asyncio.run(main())
