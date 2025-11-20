import json
import sys
from pathlib import Path
import pandas as pd


def generate_html_report(json_file_path: str):
    path = Path(json_file_path)
    if not path.exists():
        print("File not found.")
        return

    with open(path, "r") as f:
        data = json.load(f)

    # Convert list of dicts to HTML table
    df = pd.DataFrame(data)

    # Select interesting columns
    cols = [
        "user_id",
        "average_score",
        "metric_hallucination_check_score",
        "response_text",
    ]
    if "error" in df.columns:
        cols.append("error")

    # Filter if columns exist
    cols = [c for c in cols if c in df.columns]
    table_html = df[cols].to_html(classes="table table-striped", index=False)

    html_content = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>LLM Eval Report</title>
        <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css">
        <style>
            body {{ padding: 20px; }}
            pre {{ white-space: pre-wrap; background: #f8f9fa; padding: 10px; border-radius: 5px; }}
        </style>
    </head>
    <body>
        <h1>🛡️ LLM Evaluation Report</h1>
        <p><strong>File:</strong> {path.name}</p>
        <div class="table-responsive">
            {table_html}
        </div>
    </body>
    </html>
    """

    output_path = path.with_suffix(".html")
    with open(output_path, "w") as f:
        f.write(html_content)

    print(f"✅ Report generated: {output_path}")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python -m src.evaluation.visualize <path_to_detailed_json>")
    else:
        generate_html_report(sys.argv[1])
