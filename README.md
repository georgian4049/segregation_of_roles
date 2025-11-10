# 🔍 Toxic Combo Scanner: Segregation of Duties (SoD) Detector

**SoD violation detector with LLM justification for manager-ready reports.**

| Live Links | |
| :--- | :--- |
| **Try the App** | [https://myapp-production-d4ce.up.railway.app](https://myapp-production-d4ce.up.railway.app) |
| **API Docs (Swagger)** | [https://myapp-production-d4ce.up.railway.app/docs](https://myapp-production-d4ce.up.railway.app/docs) |
| **Video Walkthrough** | [YouTube Video link](https://www.youtube.com/watch?v=3tei_u6LiI8) |

-----

## Project Overview

This service addresses the challenge of identifying **Segregation of Duties (SoD) violations** from large-scale user role assignments. It is built for **memory efficiency**, processing data row-by-row without reliance on tools like Pandas to ensure large CSV files can be handled without memory overflow.

The core value proposition is the use of an **LLM (Large Language Model)** to generate **manager-ready justifications** for each detected toxic combination, focusing on optimal and minimally disruptive remediation actions.

-----

## 🚀 Getting Started (One-Command Run)

The preferred method for running this project is using **Docker Compose**, which manages all dependencies and Bedrock configuration in a single step.

### Prerequisites

  * **Docker and Docker Compose** installed.
  * **AWS credentials** configured in your shell environment or a local `.env` file (required for Bedrock access).

### 1\. Configure AWS Access

Create a `.env` file in the project root to include your live AWS credentials for Bedrock access.

```ini
# .env (Example Configuration)

# --- AWS Credentials (Required for Bedrock) ---
AWS_ACCESS_KEY_ID=AKIA...
AWS_SECRET_ACCESS_KEY=wXyZ...
# AWS_SESSION_TOKEN=... (if using temporary credentials)

# --- LLM Configuration (Override defaults in src/config.py) ---
LLM_PROVIDER=bedrock
USE_MOCK_LLM=false
AWS_REGION=eu-central-1
BEDROCK_MODEL_ID=anthropic.claude-3-haiku-20240307-v1:0
BEDROCK_MODEL_TEMPERATURE=0.2
BEDROCK_MODEL_MAX_TOKENS=300
```

*Note: Setting `USE_MOCK_LLM=true` will bypass the need for AWS credentials entirely.*

### 2\. Build and Run the Service

Run this command from the project root:

```bash
docker compose up --build
```

### 3\. Access the Application

The service will be available at the following locations:

| Service | URL |
| :--- | :--- |
| **Web UI** | `http://localhost:8080/` |
| **Interactive Docs (Swagger UI)** | `http://localhost:8080/docs` |

Source data files for testing are located in the `/data` folder.

-----

## 🤖 LLM Integration and AI Usage Note

### LLM Implementation Details

The service is configured to use **AWS Bedrock** for generating remedial justifications, utilizing a strategic inference configuration:

  * **Provider**: Configured via environment variables (defaults to `anthropic.claude-3-haiku-20240307-v1:0`).
  * **Low Temperature (`0.2`)**: Ensures the model output is **deterministic, reliable**, and strictly grounded in the supplied policy rules.
  * **Max Tokens (`300`)**: Limits the response length to control costs and enforce the small size required for a "manager-ready" report.
  * **Streaming Justification**: The `/api/v1/findings` endpoint uses **Server-Sent Events (SSE)** to stream justifications asynchronously, preventing API throttling and providing a real-time, responsive user experience.
  * **Intelligent Prompting**: The prompt includes comprehensive context (role grant dates, department, full policy context) and strict **Decision-Making Rules** to guide the LLM toward the most secure and minimally disruptive remediation action. *(The prompt logic is defined in `src/utils/prompts.py`.)*

### Data and Compliance

  * **GDPR Compliance**: All **Personally Identifiable Information (PII)** is removed from the data sent to the LLM. The `/evidence` log ensures compliance by manually redacting the user's name and storing the email in the required redacted format (e.g., `a***@domain.tld`).

### AI Tool Usage Transparency

In accordance with the challenge guidelines, AI tools were utilized to accelerate development:

  * **Code Generation/Refactoring**: Anthropic Claude and Google Gemini Pro were instrumental in developing the `asyncio` streaming logic, discussing doubts, writing UI code, and formatting this README.
  * **Testing/Data**: ChatGPT was used to generate initial seed files and testing datasets.

-----

## 🌐 Core Ingestion Logic & API Reference

### Core Ingestion Logic

The ingestion engine implements critical business rules for resilience and accuracy:

  * **Resilient Processing**: CSV files are streamed and processed row-by-row. If **data corruption** is detected (e.g., bad format, missing required fields), only the corrupt rows are rejected, and findings generation proceeds with the valid subset of data.
  * **Error Reporting**: Corrupt data is isolated, and download links are provided after ingestion, allowing users to review and remediate bad rows in CSV format.
  * **Logging**: All application activities are logged to `app.log`. Critical failures are isolated to `error.log`.

### API Endpoints

| Endpoint | Method | Description | Output |
| :--- | :--- | :--- | :--- |
| `/api/v1/ingest` | `POST` | Loads user assignments and policies into the system. | `IngestResponse` |
| `/api/v1/ingest/errors/assignments` | `GET` | Downloads a CSV of all **rejected rows** from the assignments file. | `text/csv` |
| `/api/v1/ingest/errors/policies` | `GET` | Downloads a CSV of all invalid or single-role policies. | `text/csv` |
| `/api/v1/findings` | `GET` | Initiates the scan and **streams findings** with LLM justifications. | `text/event-stream` |
| `/api/v1/simulate` | `POST` | Runs a **"what-if" scenario** by temporarily removing a role. | `SimulationResponse` |
| `/api/v1/evidence` | `GET` | Generates a complete, GDPR-redacted JSON audit pack. | `EvidenceLog (JSON)` |

-----

## 🚧 Future Work

If given more time, the following features would be prioritized:

  * **Scalability Testing**: Explore advanced patterns for handling very large numbers of LLM Bedrock calls (e.g., thousands of findings) to ensure the streaming architecture maintains stability and performance under production load.
  * **CI/CD Maturity**: Fully implement and automate a Continuous Integration pipeline to run linting and comprehensive unit tests automatically on every push.
  * **Advanced Remediation Logic**: Implement more complex heuristics in the detection engine to guarantee the absolute optimal role revocation when one role is the common denominator in multiple toxic policy violations across a user.
