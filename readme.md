                    ┌─────────────────────────────────────┐
                    │     COORDINATOR AGENT (Orchestrator)│
                    │     "Analyze RELIANCE for today"    │
                    └──────────────────┬──────────────────┘
                                       │
         ┌──────────────┬──────────────┼──────────────┬──────────────┐
         ▼              ▼              ▼              ▼              ▼
┌─────────────┐  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐
│  Technical  │  │   News &    │  │  Company    │  │  Social     │  │  Options/   │
│   Analyst   │  │  Sentiment  │  │  Funda-     │  │  Sentiment  │  │  Derivatives│
│   Agent     │  │   Agent     │  │  mentals    │  │  Agent      │  │  Agent      │
└──────┬──────┘  └──────┬──────┘  └──────┬──────┘  └──────┬──────┘  └──────┬──────┘
       │                │                │                │                │
       ▼                ▼                ▼                ▼                ▼
┌─────────────┐  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐
│ RSI, MACD,  │  │ FinBERT +   │  │ P/E, Market │  │ Reddit/Twtr │  │ IV, Greeks, │
│ Bollinger   │  │ NRC Emotion │  │ Cap, Growth │  │ Sentiment   │  │ Option Chain│
└─────────────┘  └─────────────┘  └─────────────┘  └─────────────┘  └─────────────┘


## Directory structure 
trading-agent-python/
├── app.py                     # CDK entry point
├── stacks/                    # CDK stacks (from above)
│   ├── auth_stack.py
│   ├── storage_stack.py
│   └── agent_runtime_stack.py
├── agent/                     # Your trading agent code
│   ├── main.py                # Orchestrator agent
│   ├── specialists/           # Specialist agents
│   │   ├── technical.py
│   │   ├── sentiment.py
│   │   ├── fundamentals.py
│   │   ├── social.py
│   │   └── derivatives.py
│   └── tools/                 # Shared tools
│       ├── market_data.py
│       ├── news_fetcher.py
│       └── order_execution.py
├── .github/workflows/         # GitHub Action
│   └── daily-trading.yml
├── requirements.txt
└── setup.py

## How to 
bash
# Create project directory
mkdir trading-agent-python && cd trading-agent-python

# Create CDK app with Python
cdk init app --language=python

# Activate virtual environment
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

# Install dependencies
pip install aws-cdk-lib constructs boto3
pip install -r requirements.txt

# mcp
pip install mcp strands-agents-mcp-server
