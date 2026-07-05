# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Development Setup

To set up the trading agent project:

1. **Environment Setup**:
   ```bash
   # Create virtual environment
   python3 -m venv .venv
   
   # Activate it
   source .venv/bin/activate
   
   # Install dependencies
   pip install --upgrade pip
   pip install -r requirements.txt
   
   # Install AgentCore CLI for deployment
   npm install -g @aws/agentcore
   ```

2. **Common Commands**:
   - Validate AWS CDK configuration: `cdk synth`
   - Deploy infrastructure: `cdk deploy`
   - Destroy resources: `cdk destroy`
   - Run tests: `python -m pytest tests/`
   - Run local trading bot: `python agent/main.py`

## Project Architecture

This is a multi-agent trading system built with AWS CDK and Strands Agents framework that analyzes Indian stocks and executes trades via ICICI Breeze API.

### Core Components

1. **Orchestrator Agent** (`agent/main.py`):
   - Main trading bot that runs on ECS Fargate during market hours (9:15 AM - 3:30 PM IST)
   - Uses Strands Agents-as-Tools pattern to coordinate specialist agents
   - Implements risk management, position sizing, and execution logic
   - Runs continuous analysis cycles every 3 minutes during market hours

2. **Specialist Agents** (`agent/specialists/`):
   - TechnicalAnalyst: RSI, MACD, Bollinger Bands analysis
   - SentimentAnalyst: News and emotion analysis using FinBERT
   - FundamentalAnalyst: P/E, market cap, growth metrics
   - SocialAnalyst: Reddit/Twitter sentiment analysis
   - DerivativesAnalyst: Options chain and implied volatility

3. **Shared Tools** (`agent/tools/`):
   - Market data: Yahoo Finance integration for live/historical data
   - Order execution: ICICI Breeze API wrapper
   - Database: DynamoDB operations for trade signals and learning data

4. **Overnight Processing** (`agent/overnight/` and `agent/learning/`):
   - Global macro data collection
   - News aggregation and sentiment analysis
   - Pre-market watchlist generation
   - Pattern learning and confidence adjustment

5. **Infrastructure** (`cicd/stacks/` and `app.py`):
   - AWS CDK stacks for Auth (Cognito), Storage (DynamoDB/S3), and Agent Runtime
   - ECS Fargate service for continuous trading bot execution
   - GitHub Actions for scheduled overnight processing

### Data Flow

1. **Overnight (10:30 PM - 6:00 AM IST)**:
   - Global macro and news ingestion
   - Pre-market analysis engine generates watchlist
   - Pattern learning updates agent weights/confidence thresholds

2. **Market Hours Cycle (Every 3 minutes, 9:15 AM - 3:30 PM IST)**:
   - Orchestrator analyzes watchlist stocks using all specialist agents
   - Risk management checks (daily loss, position size, circuit breakers)
   - Trading signals executed via ICICI Breeze API (limit orders only)
   - Position monitoring for stop-loss/target hits
   - Auto square-off by 3:20 PM IST

3. **Persistence Layer**:
   - DynamoDB tables for trades, sessions, market state, and learning patterns
   - S3 bucket for additional storage needs

### Key Configuration

- **Model**: Anthropic Claude 3 Haiku via Amazon Bedrock
- **Trading Parameters**: Configurable via environment variables
  - Paper trading mode (default: true)
  - Capital allocation, confidence thresholds, risk limits
  - Analysis interval (default: 180 seconds)
- **Static IP**: 3.8.245.57 (NAT Gateway for outbound traffic)

### MCP Servers

The project includes Model Context Protocol servers for extending agent capabilities:
- News sentiment server
- Market data server  
- Trading execution server
- Bedrock sentiment server
