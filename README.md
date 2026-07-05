# Navigate to project
cd /Users/shantanu/Downloads/CodeProjects/AGENTIC_AI_PROJECTS/trader-daily-india
# Create and activate virtual environment
python3 -m venv .venv

# Activate it
source .venv/bin/activate

pip install --upgrade pip

# Install all requirements (including CDK)
pip install -r requirements.txt

# If requirements.txt is missing some packages, install these:
pip install aws-cdk-lib constructs boto3

Now , cdk deploy created the supporting infrastructure like IAM roles and databases. To actually deploy   agent code to Bedrock AgentCore, need a separate, dedicated tool: the AgentCore CLI . AWS distributes this tool exclusively as a Node.js package named @aws/agentcore on the npm registry. So, run 

npm install -g @aws/agentcore

# Verify installation
agentcore --version

# Navigate to your agent directory
cd /Users/shantanu/Downloads/CodeProjects/AGENTIC_AI_PROJECTS/trader-daily-india/agent

# Configure the agent (this packages and uploads your code)
agentcore create

# Deploy the agent
agentcore launch \
  --runtime-name svc-trd-strands-agent \
  --region eu-west-1





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

ARCHITECTURE:
-----------------------
┌─────────────────────────────────────────────────────────────────────────────┐
│                         GITHUB ACTION (Daily at 2:00 PM IST)                │
└─────────────────────────────────────────────────────────────────────────────┘
                                      │
                                      ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                    ORCHESTRATOR AGENT (Strands - Agents-as-Tools)           │
│  "Analyze NIFTY stocks and execute trades for high-confidence signals"      │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │                    PHASE 1: ANALYSIS (YOUR EXISTING CODE)           │    │
│  │  ┌────────────┐ ┌────────────┐ ┌────────────┐ ┌────────────┐        │    │
│  │  │ Technical  │ │ Sentiment  │ │ Funda-     │ │Derivatives.│        │    │
│  │  │ Analyst    │ │ Analyst    │ │ mentals    │ │ Analyst    │        │    │
│  │  │ @tool      │ │ @tool      │ │ @tool      │ │ @tool      │        │    │
│  │  └────────────┘ └────────────┘ └────────────┘ └────────────┘        │    │
│  └─────────────────────────────────────────────────────────────────────┘    │
│                                      │                                      │
│                                      ▼                                      │
│  ┌──────────────────────────────────────────────────────────────────────┐   │
│  │              PHASE 2: EXECUTION DECISION (NEW LAYER)                 │   │
│  │                                                                      │   │
│  │  Decision Rules:                                                     │   │
│  │  • Confidence > 80% AND Risk = LOW → Auto-execute                    │   │
│  │  • Confidence 60-80% AND Risk = MEDIUM → Alert, require approval     │   │
│  │  • Confidence < 60% OR Risk = HIGH → Skip (log only)                 │   │
│  └──────────────────────────────────────────────────────────────────────┘   │
│                                      │                                      │
│                                      ▼                                      │
│  ┌──────────────────────────────────────────────────────────────────────┐   │
│  │              PHASE 3: EXECUTION (ICICI Breeze API)                   │   │
│  │  ┌────────────────────────────────────────────────────────────────┐  │   │
│  │  │  Execution Agent (@tool)                                       │  │   │
│  │  │  • Calls breeze.place_order() with signal parameters           │  │   │
│  │  │  • Handles order response and order IDs                        │  │   │
│  │  │  • Logs to DynamoDB for audit trail                            │  │   │
│  │  └────────────────────────────────────────────────────────────────┘  │   │
│  └──────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
                                      │
                                      ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                         AWS (Persistent Infrastructure)                     │
├─────────────────────────────────────────────────────────────────────────────┤
│  DynamoDB: TradesTable        │  ICICI Breeze API (External)                │
│  ┌─────────────────────────┐  │  ┌─────────────────────────────────────────┐│
│  │ tradeId (PK)            │  │  │ place_order(                            ││
│  │ date (SK)               │  │  │   stock_code, action, quantity, price,  ││
│  │ signal_action           │  │  │   order_type='limit', validity='day'    ││
│  │ execution_status        │  │  │ )                                       ││
│  │ order_id                │  │  └─────────────────────────────────────────┘│
│  │ filled_quantity         │  │                                             │
│  └─────────────────────────┘  │                                             │
└─────────────────────────────────────────────────────────────────────────────┘

-------------------------------------
## Directory structure 
trader-daily-india/
├── app.py                     # CDK entry point
├── requirements.txt                    # Python dependencies
├── README.md   
├── .gitignore   
├── cicd/                    # CI/CD and infrastructure assets
│   ├── env/                   # Environment configuration
│   │   └── prod.json
│   ├── stacks/                # CDK stacks (from above)
│   │   ├── auth_stack.py
│   │   ├── storage_stack.py
│   │   └── agent_runtime_stack.py
│   ├── ecstasks_unused/       # Legacy ECS task JSONs, not active deploy source
│   │   ├── dashboard.json
│   │   ├── overnight-analysis.json
│   │   └── trading-bot.json
│   └── cfn/                   # Hand-written CloudFormation, if needed
├── containers/                         # Docker containers
│   ├── trading-bot/
│   │   ├── Dockerfile
│   │   ├── requirements.txt
│   │   └── entrypoint.sh
│   └── dashboard/
│       ├── Dockerfile
│       ├── requirements.txt
│       └── api_server.py               # FastAPI + embedded HTML dashboard
│
│       └── static/      
├── agent/                     # Your trading agent code
|   |___init__.py
│   ├── main.py
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

Whats deployed 

Architecture Diagram of What's Deployed
text

┌─────────────────────────────────────────────────────────────────────────────────────┐
│                              OVERNIGHT BATCH (10:30 PM - 6:00 AM)                    │
├─────────────────────────────────────────────────────────────────────────────────────┤
│                                                                                      │
│  ┌──────────────────────────────────────────────────────────────────────────────┐   │
│  │                    GLOBAL & MACRO INGESTION LAYER                             │   │
│  │  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐      │   │
│  │  │  News API    │  │  Twitter/X   │  │  Reddit      │  │  Economic    │      │   │
│  │  │  (Global)    │  │  Sentiment   │  │  (r/India    │  │  Calendars   │      │   │
│  │  │              │  │              │  │  Stocks)     │  │  (Forex,     │      │   │
│  │  └──────────────┘  └──────────────┘  └──────────────┘  │  Commodities) │      │   │
│  │                                                         └───────────────┘      │   │
│  └──────────────────────────────────────────────────────────────────────────────┘   │
│                                      │                                              │
│                                      ▼                                              │
│  ┌──────────────────────────────────────────────────────────────────────────────┐   │
│  │                    PRE-MARKET ANALYSIS ENGINE                                │   │
│  │  ┌────────────────────────────────────────────────────────────────────────┐  │   │
│  │  │  • NIFTY 50 + Bank Nifty + 100 liquid stocks pre-screening            │  │   │
│  │  │  • Identify stocks with unusual options activity (OI changes)         │  │   │
│  │  │  • Flag stocks with breaking news (positive/negative)                 │  │   │
│  │  │  • Generate pre-market watchlist (5-10 candidates)                    │  │   │
│  │  └────────────────────────────────────────────────────────────────────────┘  │   │
│  └──────────────────────────────────────────────────────────────────────────────┘   │
│                                      │                                              │
│                                      ▼                                              │
│  ┌──────────────────────────────────────────────────────────────────────────────┐   │
│  │                    PATTERN LEARNING LAYER (Historical Analysis)              │   │
│  │  ┌────────────────────────────────────────────────────────────────────────┐  │   │
│  │  │  • Analyze past trades: What RSI ranges produced profits?              │  │   │
│  │  │  • What sentiment thresholds worked?                                   │  │   │
│  │  │  • Update agent weights/confidence thresholds dynamically             │  │   │
│  │  └────────────────────────────────────────────────────────────────────────┘  │   │
│  └──────────────────────────────────────────────────────────────────────────────┘   │
│                                                                                      │
└─────────────────────────────────────────────────────────────────────────────────────┘
                                      │
                                      │ Pre-market watchlist + updated models
                                      ▼
┌─────────────────────────────────────────────────────────────────────────────────────┐
│                              MARKET HOURS (9:15 AM - 3:30 PM)                        │
│                              CYCLE: EVERY 3 MINUTES                                  │
├─────────────────────────────────────────────────────────────────────────────────────┤
│                                                                                      │
│  ┌──────────────────────────────────────────────────────────────────────────────┐   │
│  │                    ORCHESTRATOR AGENT (Strands - CEO of Trading)             │   │
│  │                                                                               │   │
│  │  Input: Watchlist of 5-10 pre-screened stocks                                │   │
│  │  Output: Final BUY/SELL/HOLD with confidence, entry, stop, target           │   │
│  └──────────────────────────────────────────────────────────────────────────────┘   │
│                                      │                                              │
│         ┌────────────────────────────┼────────────────────────────┐                │
│         ▼                            ▼                            ▼                │
│  ┌──────────────┐           ┌──────────────┐           ┌──────────────┐            │
│  │  Technical   │           │   News &     │           │  Company     │            │
│  │  Analyst     │           │  Sentiment   │           │  Funda-      │            │
│  │  Agent       │           │  Agent       │           │  mentals     │            │
│  │              │           │              │           │  Agent       │            │
│  │  • Real-time │           │  • Live news │           │  • P/E vs    │            │
│  │    RSI (1min)│           │    sentiment │           │    industry  │            │
│  │  • MACD      │           │  • Social    │           │  • Results   │            │
│  │  • VWAP      │           │    sentiment │           │    impact    │            │
│  │  • Order flow│           │  • Global    │           │  • M&A news  │            │
│  │  • Support/  │           │    macro cues│           │              │            │
│  │    Resistance│           │              │           │              │            │
│  └──────────────┘           └──────────────┘           └──────────────┘            │
│         │                            │                            │                │
│         └────────────────────────────┼────────────────────────────┘                │
│                                      ▼                                              │
│  ┌──────────────────────────────────────────────────────────────────────────────┐   │
│  │                    RISK MANAGEMENT MODULE (Non-negotiable)                   │   │
│  │  ┌────────────────────────────────────────────────────────────────────────┐  │   │
│  │  │  Checks before execution:                                              │  │   │
│  │  │  • Daily loss limit exceeded? → HALT                                   │  │   │
│  │  │  • Position size > 10% of capital? → REJECT                            │  │   │
│  │  │  • Consecutive losses > 3? → HALT                                      │  │   │
│  │  │  • Market volatility > threshold? → REDUCE SIZE                        │  │   │
│  │  │  • Time < 3:20 PM? → Allow (square-off by 3:20 PM)                     │  │   │
│  │  └────────────────────────────────────────────────────────────────────────┘  │   │
│  └──────────────────────────────────────────────────────────────────────────────┘   │
│                                      │                                              │
│                                      ▼                                              │
│  ┌──────────────────────────────────────────────────────────────────────────────┐   │
│  │                    EXECUTION MODULE (ICICI Breeze API)                       │   │
│  │  • Place limit orders only                                                  │   │
│  │  • Max 10 orders/second (with 100ms spacing)                                │   │
│  │  • Auto square-off at 3:20 PM IST                                           │   │
│  │  • Stop-loss always attached                                                │   │
│  └──────────────────────────────────────────────────────────────────────────────┘   │
│                                                                                      │
└─────────────────────────────────────────────────────────────────────────────────────┘
                                      │
                                      ▼
┌─────────────────────────────────────────────────────────────────────────────────────┐
│                              PERSISTENCE LAYER (DynamoDB)                            │
├─────────────────────────────────────────────────────────────────────────────────────┤
│                                                                                      │
│  ┌────────────────────────────┐    ┌────────────────────────────────────────────┐   │
│  │  TradesTable               │    │  SessionTable (Agent Memory)               │   │
│  │  ┌──────────────────────┐  │    │  ┌──────────────────────────────────────┐  │   │
│  │  │ tradeId (PK)         │  │    │  │ sessionId (PK)                       │  │   │
│  │  │ date (SK)            │  │    │  │ timestamp (SK)                       │  │   │
│  │  │ stock_symbol         │  │    │  │ conversation_history                 │  │   │
│  │  │ action (BUY/SELL)    │  │    │  │ extracted_preferences                │  │   │
│  │  │ entry_price          │  │    │  │ past_patterns_learned                │  │   │
│  │  │ exit_price           │  │    │  └──────────────────────────────────────┘  │   │
│  │  │ pnl                  │  │    │                                           │   │
│  │  │ confidence_at_entry  │  │    └────────────────────────────────────────────┘   │
│  │  │ sentiment_at_entry   │  │                                                    │
│  │  │ rsi_at_entry         │  │    ┌────────────────────────────────────────────┐   │
│  │  └──────────────────────┘  │    │  MarketStateTable (Overnight Analysis)     │   │
│  └────────────────────────────┘    │  ┌──────────────────────────────────────┐  │   │
│                                    │  │ date (PK)                            │  │   │
│  ┌────────────────────────────┐    │  │ global_sentiment_score               │  │   │
│  │  LearningTable             │    │  │ india_vix                            │  │   │
│  │  ┌──────────────────────┐  │    │  │ pre_market_watchlist                │  │   │
│  │  │ pattern_id (PK)      │  │    │  │ overnight_news_summary               │  │   │
│  │  │ rsi_range            │  │    │  └──────────────────────────────────────┘  │   │
│  │  │ sentiment_threshold  │  │    │                                           │   │
│  │  │ win_rate             │  │    └────────────────────────────────────────────┘   │
│  │  │ avg_profit           │  │                                                    │
│  │  └──────────────────────┘  │                                                    │
│  └────────────────────────────┘                                                    │
│                                                                                      │
└─────────────────────────────────────────────────────────────────────────────────────┘


┌─────────────────────────────────────────────────────────────┐
│                    YOUR AWS ACCOUNT (eu-west-1)             │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  ┌────────────────────────────────────────────────────┐     │
│  │           CLOUDFORMATION STACKS                    │     │
│  │  ┌──────────────┐  ┌──────────────┐  ┌───────────┐ │     │
│  │  │   AuthStack  │  │ StorageStack │  │AgentRuntim│ │     │
│  │  │  (Cognito)   │  │(DynamoDB+S3) │  │ eStack    │ │     │
│  │  └──────────────┘  └──────────────┘  └───────────┘ │     │
│  └────────────────────────────────────────────────────┘     │
│                                                             │
│  ┌──────────────────┐  ┌──────────────────────────────────┐ │
│  │   S3 BUCKET      │  │         DYNAMODB TABLES          │ │
│  │ (existing -      │  │  ┌─────────────┐ ┌─────────────┐ │ │
│  │  imported)       │  │  │  Session    │ │   Trades    │ │ │
│  │                  │  │  │   Table     │ │    Table    │ │ │
│  └──────────────────┘  │  └─────────────┘ └─────────────┘ │ │
│                        └──────────────────────────────────┘ │
│                                                             │
│  ┌──────────────────────────────────────────────────────┐   │
│  │                    IAM ROLES                         │   │
│  │  ┌────────────────────────────────────────────────┐  │   │
│  │  │  svc-trd-agent-role (Bedrock + DynamoDB + S3)  │  │   │
│  │  └────────────────────────────────────────────────┘  │   │
│  └──────────────────────────────────────────────────────┘   │
│                                                             │
│  ┌──────────────────────────────────────────────────────┐   │
│  │                    COGNITO                           │   │
│  │  ┌──────────────┐  ┌──────────────┐  ┌────────────┐  │   │
│  │  │  User Pool   │  │ User Pool    │  │ Identity   │  │   │
│  │  │              │  │   Client     │  │   Pool     │  │   │
│  │  └──────────────┘  └──────────────┘  └────────────┘  │   │
│  └──────────────────────────────────────────────────────┘   │
│                                                             │
└─────────────────────────────────────────────────────────────┘

#ECS

┌─────────────────────────────────────────────────────────────────────────────┐
│                           ECS FARGATE SERVICE                               │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  ┌─────────────────────────────┐    ┌─────────────────────────────────────┐ │
│  │   CONTAINER 1: Trading Bot   │    │   CONTAINER 2: Dashboard Frontend   │ │
│  │   (Always running during     │    │   (Static files + FastAPI)          │ │
│  │    market hours)             │    │                                     │ │
│  │                              │    │  • Serves HTML/CSS/JS               │ │
│  │  • Multi-agent analysis      │    │  • REST API endpoints              │ │
│  │  • Position management       │    │  • Real-time trade data            │ │
│  │  • Trade execution           │    │  • P&L charts                      │ │
│  │  • Market data ingestion     │    │                                     │ │
│  └─────────────────────────────┘    └─────────────────────────────────────┘ │
│                                                                              │
│                              Shared Volume / DynamoDB                        │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘

📊 Dashboard ──────► http://trading-dashboard-1234567890.elb.amazonaws.com│
│                                                                              │
│   🤖 Trading Bot ─────► Runs 9:15 AM - 3:30 PM IST, every 3 minutes         │
│                                                                              │
│   🌙 Overnight ───────► Runs daily at 10:30 PM IST                          │
│                                                                              │
│   📈 Multi-Agent ─────► 4 specialists (Technical, Sentiment, Fundamentals,  │
│                         Derivatives) + Orchestrator                         │
│                                                                              │
│   💰 Execution ───────► ICICI Breeze API with 10 orders/sec rate limiting   │
│                                                                              │
│   🛡️ Risk Management ─► Daily loss limit, position caps, circuit breakers   │
│                                                                              │


Connect with Aws Ec2 instance session maager :
Install session mgr : 
sudo installer -pkg session-manager-plugin.pkg -target /
<input mac pass>
Creaye symbolic link : 
sudo ln -s /usr/local/sessionmanagerplugin/bin/session-manager-plugin /usr/local/bin/session-manager-plugin

Connect to instance: 
aws ssm start-session --target i-03681d7414161dd6d --profile tiiqu --region eu-west-2 (Note i-03681d7414161dd6d is instance id of running ec2) 
