🔍 Toxic Combo Scanner
SoD violation detector with LLM justification

Try me on -> https://myapp-production-d4ce.up.railway.app

API DOCS -> https://myapp-production-d4ce.up.railway.app/docs

YouTube Video link -> https://www.youtube.com/watch?v=3tei_u6LiI8

This service detects Segregation of Duties (SoD) violations from uploaded CSVs of user role assignments and toxic policies. It is built to be memory-efficient, handling large files by streaming and processing data row-by-row, without relying on tools like Pandas. The core functionality centers around generating manager-ready justifications using an LLM.

🚀 Getting Started (One-Command Run)
The preferred method for running this project is using Docker Compose, which handles all dependencies and sets up the required Bedrock configuration in one step.

Prerequisites

Docker and Docker Compose installed.

AWS credentials configured in your shell environment (recommended for security) or saved in a local .env file.

1. Configure AWS Access

Create a .env file in the project root based on docker-compose.yml (or your local shell) and include your live AWS credentials for Bedrock access:

Ini, TOML
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

Note: Setting USE_MOCK_LLM=true will bypass the need for AWS credentials entirely.

2. Build and Run the Service

Run this command from the project root:

Bash
docker compose up --build
3. Access the API

The application will be available at: http://localhost:8080.

Interactive Docs (Swagger UI): http://localhost:8080/docs

Web UI: http://localhost:8080/

Datas are in /data folder

🤖 LLM Integration and AI Usage Note
LLM Implementation Details

The service utilizes AWS Bedrock for generating manager-ready justifications, focusing on optimal remediation.

Provider: Configured via environment variables (defaults to anthropic.claude-3-haiku-20240307-v1:0).

Inference Configuration:

BEDROCK_MODEL_TEMPERATURE=0.2: A low temperature is used to ensure the model output is deterministic, reliable, and grounded in the supplied policy rules rather than creative language.

BEDROCK_MODEL_MAX_TOKENS=300: This limits the length of the LLM's raw response to control costs and enforce the small size required for a "manager-ready" report.

Streaming Justification: The GET /api/v1/findings endpoint uses an SSE (Server-Sent Event) stream to send justifications to the client asynchronously. This prevents API throttling and provides a real-time, responsive UI experience.

Intelligent Prompting: The prompt provides comprehensive context (role grant dates, department, full policy context) and strict Decision-Making Rules to guide the LLM toward the most secure and minimally disruptive remediation action.

The prompt logic is defined in src/utils/prompts.py.

GDPR Compliance: All Personally Identifiable Information (PII) is removed from the data sent to the LLM. The /evidence log ensures compliance by manually redacting the user's name and storing the email in the required redacted format (a***@domain.tld).

AI Tool Usage

As per the challenge guidelines, AI tools were utilized to accelerate development:

Code Generation/Refactoring: Anthropic Claude Code and Google Gemini Pro were instrumental in developing the asyncio streaming logic and some other parts of code, discussing doubts, writing UI code and formatting README.md file.

Testing/Data: ChatGPT was used to generate initial seed files and testing datasets.

🌐 API Usage and Error Reporting
Endpoint	Method	Description	Output
/api/v1/ingest	POST	Loads user assignments and policies.	IngestResponse

/api/v1/ingest/errors/assignments	GET	Downloads a CSV containing all rejected rows from the assignments file.	text/csv

/api/v1/ingest/errors/policies	GET	Downloads a CSV containing all invalid or single-role policies.	text/csv

/api/v1/findings	GET	Initiates scan and streams findings + LLM justifications.	text/event-stream

/api/v1/simulate	POST	Runs a "what-if" scenario by temporarily removing a role.	SimulationResponse

/api/v1/evidence	GET	Generates a complete, GDPR-redacted JSON audit pack.	EvidenceLog (JSON)

Logging: All application activities are logged to app.log, while only critical failures (ERROR/CRITICAL) are isolated and logged to error.log.

Core Ingestion Logic

The ingestion engine implements critical business rules:

Resilient Processing: The service streams CSV files (Need to test on super large files) and processes all valid rows immediately. If corruption is detected (e.g., bad format, missing required fields), only the corrupt rows are rejected, and findings generation proceeds with the valid subset of data.

Error Reporting: Corrupt data is isolated, and links to download the error files are provided after ingestion, allowing users to review and remediate the bad rows in CSV format.

Logging: All application activities are logged to app.log, while only critical failures (ERROR/CRITICAL) are isolated and logged to error.log.

🎯 Future Work
If given more time, the following features would be prioritized:

Scalability Testing: Explore advanced patterns for handling very large numbers of LLM Bedrock calls (e.g., thousands of findings) to ensure the streaming architecture maintains stability and performance under production load.

CI/CD Maturity: Fully implement and automate a Continuous Integration pipeline to run linting and comprehensive unit tests automatically on every push.

Advanced Remediation Logic: Implement more complex heuristics in the detection engine to guarantee the absolute optimal role revocation when one role is the common denominator in multiple toxic policy violations across a user.
