#!/usr/bin/env python3
"""
MCP Server for Sentiment Analysis using Amazon Bedrock
No PyTorch, no local models - pure API calls to Bedrock
"""

import asyncio
import json
import boto3
import os
from typing import Any, Dict, List, Optional

from mcp.server import Server
import mcp.server.stdio
import mcp.types as types

# Initialize Bedrock client
bedrock_runtime = boto3.client(
    service_name='bedrock-runtime',
    region_name=os.environ.get('AWS_REGION', 'eu-west-1')
)

MODEL_ID = "anthropic.claude-3-haiku-20240307-v1:0"

server = Server("bedrock-sentiment")

@server.list_tools()
async def handle_list_tools() -> List[types.Tool]:
    """List available sentiment analysis tools"""
    return [
        types.Tool(
            name="analyze_sentiment",
            description="Analyze sentiment of a news headline using Amazon Bedrock Claude 3",
            inputSchema={
                "type": "object",
                "properties": {
                    "text": {"type": "string", "description": "News headline to analyze"}
                },
                "required": ["text"]
            }
        ),
        types.Tool(
            name="batch_sentiment",
            description="Analyze sentiment for multiple headlines",
            inputSchema={
                "type": "object",
                "properties": {
                    "headlines": {"type": "array", "items": {"type": "string"}}
                },
                "required": ["headlines"]
            }
        )
    ]

@server.call_tool()
async def handle_call_tool(
    name: str,
    arguments: Optional[Dict[str, Any]] = None
) -> List[types.TextContent]:
    
    if name == "analyze_sentiment":
        text = arguments.get("text", "")
        
        prompt = f"""Analyze this financial news sentiment. Return ONLY JSON: {{"bullish": X, "neutral": Y, "bearish": Z}} where X+Y+Z=100.
        
        Headline: {text}"""
        
        response = bedrock_runtime.invoke_model(
            modelId=MODEL_ID,
            contentType="application/json",
            body=json.dumps({
                "anthropic_version": "bedrock-2023-05-31",
                "max_tokens": 200,
                "temperature": 0.2,
                "messages": [{"role": "user", "content": prompt}]
            })
        )
        
        result = json.loads(response['body'].read())
        return [types.TextContent(type="text", text=json.dumps(result))]
    
    return [types.TextContent(type="text", text=json.dumps({"error": f"Unknown tool: {name}"}))]

async def main():
    async with mcp.server.stdio.stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            mcp.server.models.InitializationOptions(
                server_name="bedrock-sentiment",
                server_version="1.0.0"
            )
        )

if __name__ == "__main__":
    asyncio.run(main())