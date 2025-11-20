import json
import logging
from datetime import datetime
from pathlib import Path
from typing import List, Dict

# Ensure opensearchpy is installed
from opensearchpy import OpenSearch

import pandas as pd
from tqdm.asyncio import tqdm_asyncio

from src.models import UserViolationProfile
from src.services.llm_service import get_llm_service
from src.evaluation.metrics import (
    EvalMetric,
    JsonComplianceMetric,
    HallucinationMetric,
    RiskKeywordMetric,
)
from src.prompts.prompts import build_smart_remediation_prompt

logger = logging.getLogger(__name__)


class LLMEvaluator:
    def __init__(self, results_dir: str = "evaluation_results"):
        self.llm_service = get_llm_service()
        self.results_dir = Path(results_dir)
        self.results_dir.mkdir(exist_ok=True)

        # Register metrics
        self.metrics: List[EvalMetric] = [
            JsonComplianceMetric(),
            HallucinationMetric(),
            RiskKeywordMetric(),
        ]

    def _get_opensearch_client(self):
        host = "localhost"
        return OpenSearch(
            hosts=[{"host": host, "port": 9200}], http_compress=True, use_ssl=False
        )

    async def evaluate_single_case(self, profile: UserViolationProfile) -> Dict:
        """Runs LLM generation and then scores it."""
        start_time = datetime.now()
        try:
            prompt = build_smart_remediation_prompt(profile)

            response_text = await self.llm_service.provider.generate(
                prompt=prompt, max_tokens=300, profile=profile
            )
            latency = (datetime.now() - start_time).total_seconds()

            result = {
                "user_id": profile.user.user_id,
                "department": profile.user.department,
                "response_text": response_text,
                "latency_seconds": latency,
                "timestamp": datetime.now().isoformat(),
                "error": None,
            }

            total_score = 0
            for metric in self.metrics:
                eval_res = metric.evaluate(response_text, profile)
                result[f"metric_{metric.name}_score"] = eval_res["score"]
                result[f"metric_{metric.name}_reason"] = eval_res["reason"]
                total_score += eval_res["score"]

            result["average_score"] = total_score / len(self.metrics)
            return result

        except Exception as e:
            logger.error(f"Eval failed for {profile.user.user_id}: {e}")

            return {
                "user_id": profile.user.user_id,
                "error": str(e),
                "average_score": 0.0,
                "latency_seconds": 0.0,
                "metric_json_compliance_score": 0.0,
                "metric_hallucination_check_score": 0.0,
                "metric_risk_content_score": 0.0,
                "timestamp": datetime.now().isoformat(),
            }

    async def run_batch_evaluation(
        self, profiles: List[UserViolationProfile], run_name: str = "manual_run"
    ):
        """Runs evaluation over a list of profiles."""
        logger.info(
            f"Starting evaluation run '{run_name}' with {len(profiles)} cases..."
        )

        tasks = [self.evaluate_single_case(p) for p in profiles]
        results = await tqdm_asyncio.gather(*tasks, desc="Evaluating")

        df = pd.DataFrame(results)

        valid_df = df[df["error"].isnull()]

        if not valid_df.empty:
            avg_latency = valid_df["latency_seconds"].mean()
            avg_quality = valid_df["average_score"].mean()
            compliance_rate = valid_df["metric_json_compliance_score"].mean()
            hallucination_rate = (
                1.0 - valid_df["metric_hallucination_check_score"].mean()
            )
        else:
            avg_latency = 0.0
            avg_quality = 0.0
            compliance_rate = 0.0
            hallucination_rate = 0.0

        summary = {
            "run_name": run_name,
            "total_cases": len(results),
            "successful_cases": len(valid_df),
            "avg_latency": avg_latency,
            "avg_quality_score": avg_quality,
            "compliance_rate": compliance_rate,
            "hallucination_rate": hallucination_rate,
        }

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = self.results_dir / f"eval_{run_name}_{timestamp}.csv"
        summary_filename = self.results_dir / f"summary_{run_name}_{timestamp}.json"

        df.to_csv(filename, index=False)
        with open(summary_filename, "w") as f:
            json.dump(summary, f, indent=2)

        logger.info(f"Evaluation complete. Results saved to {filename}")
        print("\n=== Evaluation Summary ===")
        print(json.dumps(summary, indent=2))

        # Pushing to OpenSearch
        try:
            client = self._get_opensearch_client()
            index_name = "sod-eval-metrics"

            if not client.indices.exists(index=index_name):
                client.indices.create(
                    index=index_name,
                    body={
                        "mappings": {
                            "properties": {
                                "run_name": {"type": "keyword"},
                                "timestamp": {"type": "date"},
                                "avg_quality_score": {"type": "float"},
                                "hallucination_rate": {"type": "float"},
                                "compliance_rate": {"type": "float"},
                            }
                        }
                    },
                )

            # Index the summary document
            doc = summary.copy()
            doc["timestamp"] = datetime.now().isoformat()
            client.index(index=index_name, body=doc)
            logger.info(
                f"✅ Evaluation metrics pushed to OpenSearch index '{index_name}'"
            )

        except Exception as e:
            # Don't fail the whole eval if OpenSearch is down (e.g. in CI environment without it)
            logger.warning(f"⚠️ Could not push to OpenSearch: {e}")

        return summary
