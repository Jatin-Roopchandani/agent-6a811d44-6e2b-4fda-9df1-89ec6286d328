import argparse
import asyncio
import logging
import json
from typing import Dict, Any
from quart import Quart, request, jsonify
from dotenv import load_dotenv
import os

from agent import CodeReviewAgent
from common import run_agent_with_common_setup, raise_if_env_absent

# Load environment variables
load_dotenv()

app_name = "code_review_agent"
quart_app = Quart(__name__)

def validate_review_criteria(criteria: Dict[str, Any]) -> Dict[str, bool]:
    """Validate and normalize review criteria."""
    default_criteria = {
        "code_quality": True,
        "security": True,
        "performance": True,
        "style": True,
        "documentation": True
    }
    
    if not criteria:
        return default_criteria
    
    # Validate that all keys are boolean
    for key, value in criteria.items():
        if key in default_criteria:
            default_criteria[key] = bool(value)
    
    return default_criteria

def validate_severity_threshold(threshold: str) -> str:
    """Validate severity threshold."""
    valid_thresholds = ["low", "medium", "high", "critical"]
    if threshold not in valid_thresholds:
        return "low"
    return threshold

async def run_code_review_agent(session_state: Dict[str, Any]) -> Dict[str, Any]:
    """Run the code review agent and return the result."""
    # Create a minimal version of run_agent_with_common_setup that returns result
    logging.basicConfig(level=logging.INFO)
    
    from google.adk.runners import InMemoryRunner
    from google.genai import types
    from logger import get_logger
    
    logger = get_logger(app_name)
    
    runner = InMemoryRunner(
        app_name=app_name,
        agent=CodeReviewAgent(name="code_review_agent"),
    )
    
    session = await runner.session_service.create_session(
        app_name=app_name, 
        user_id="api_user", 
        state=session_state
    )
    
    # Capture the final result
    final_result = None
    
    async for event in runner.run_async(
        user_id="api_user",
        session_id=session.id,
        new_message=types.Content(role="user", parts=[types.Part(text="Start code review process.")])
    ):
        logger.info(event.model_dump_json(exclude_unset=True, exclude_defaults=True, exclude_none=True))
        # Check if this is the final result
        if hasattr(event, 'content') and event.content:
            # Try to get the final result from session state
            session_data = await runner.session_service.get_session(session.id)
            if session_data and 'final_result' in session_data.state:
                final_result = session_data.state['final_result']
    
    # Get the final session state
    if not final_result:
        session_data = await runner.session_service.get_session(session.id)
        if session_data and 'final_result' in session_data.state:
            final_result = session_data.state['final_result']
    
    return final_result or {
        "success": False,
        "error": "No result generated",
        "review_summary": "Failed to complete review",
        "comments_added": [],
        "issues_found": [],
        "approval_recommendation": "comment"
    }

@quart_app.route('/agent', methods=['POST'])
async def agent_endpoint():
    """Main agent endpoint for processing code review requests."""
    try:
        # Parse request data
        data = await request.get_json()
        
        # Validate required fields
        if not data or 'pull_request_url' not in data:
            return jsonify({
                "success": False,
                "error": "pull_request_url is required"
            }), 400
        
        pull_request_url = data['pull_request_url']
        review_criteria = validate_review_criteria(data.get('review_criteria', {}))
        severity_threshold = validate_severity_threshold(data.get('severity_threshold', 'low'))
        post_comments = data.get('post_comments', False)
        
        # Prepare session state
        session_state = {
            "pull_request_url": pull_request_url,
            "review_criteria": review_criteria,
            "severity_threshold": severity_threshold,
            "post_comments": post_comments
        }
        
        # Run the agent
        result = await run_code_review_agent(session_state)
        
        return jsonify(result)
        
    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500

@quart_app.route('/schema', methods=['GET'])
def schema_endpoint():
    """Return OpenAPI schema for the agent endpoint."""
    schema = {
        "openapi": "3.0.0",
        "info": {
            "title": "Code Review Agent API",
            "version": "1.0.0",
            "description": "AI-powered code review agent that automatically reviews pull requests"
        },
        "paths": {
            "/agent": {
                "post": {
                    "summary": "Review a pull request",
                    "description": "Analyze a GitHub pull request and provide comprehensive review feedback",
                    "requestBody": {
                        "required": True,
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "required": ["pull_request_url"],
                                    "properties": {
                                        "pull_request_url": {
                                            "type": "string",
                                            "description": "GitHub pull request URL",
                                            "example": "https://github.com/owner/repo/pull/123"
                                        },
                                        "review_criteria": {
                                            "type": "object",
                                            "description": "Review focus areas configuration",
                                            "properties": {
                                                "code_quality": {"type": "boolean", "default": True},
                                                "security": {"type": "boolean", "default": True},
                                                "performance": {"type": "boolean", "default": True},
                                                "style": {"type": "boolean", "default": True},
                                                "documentation": {"type": "boolean", "default": True}
                                            }
                                        },
                                        "severity_threshold": {
                                            "type": "string",
                                            "enum": ["low", "medium", "high", "critical"],
                                            "default": "low",
                                            "description": "Minimum severity level for reporting issues"
                                        },
                                        "post_comments": {
                                            "type": "boolean",
                                            "default": False,
                                            "description": "Whether to post comments to the PR"
                                        }
                                    }
                                }
                            }
                        }
                    },
                    "responses": {
                        "200": {
                            "description": "Review completed successfully",
                            "content": {
                                "application/json": {
                                    "schema": {
                                        "type": "object",
                                        "properties": {
                                            "review_summary": {"type": "string"},
                                            "comments_added": {
                                                "type": "array",
                                                "items": {
                                                    "type": "object",
                                                    "properties": {
                                                        "file_path": {"type": "string"},
                                                        "line_number": {"type": "integer"},
                                                        "comment": {"type": "string"},
                                                        "severity": {"type": "string"},
                                                        "category": {"type": "string"}
                                                    }
                                                }
                                            },
                                            "issues_found": {
                                                "type": "array",
                                                "items": {
                                                    "type": "object",
                                                    "properties": {
                                                        "category": {"type": "string"},
                                                        "severity": {"type": "string"},
                                                        "description": {"type": "string"},
                                                        "file_path": {"type": "string"},
                                                        "line_number": {"type": "integer"},
                                                        "suggestion": {"type": "string"}
                                                    }
                                                }
                                            },
                                            "approval_recommendation": {"type": "string"},
                                            "success": {"type": "boolean"},
                                            "error": {"type": "string"}
                                        }
                                    }
                                }
                            }
                        }
                    }
                }
            }
        }
    }
    return jsonify(schema)

async def main():
    """
    Main entry point for the code review agent.
    
    This can be run either as a CLI or as a Flask server.
    """
    
    # Check for required API keys
    raise_if_env_absent(["GOOGLE_API_KEY"])  # GitHub token will be checked when needed

    # Parse command line arguments
    parser = argparse.ArgumentParser(description="Code Review Agent - AI-powered PR review")
    parser.add_argument("--pull_request_url", type=str, help="GitHub pull request URL")
    parser.add_argument("--review_criteria", type=str, help="JSON string of review criteria")
    parser.add_argument("--severity_threshold", type=str, default="low", 
                       choices=["low", "medium", "high", "critical"],
                       help="Minimum severity level for reporting issues")
    parser.add_argument("--post_comments", action="store_true", help="Post comments to the PR")
    parser.add_argument("--server", action="store_true", help="Run as Flask server")
    parser.add_argument("--port", type=int, default=5000, help="Server port")
    
    args = parser.parse_args()

    if args.server:
        # Run as Quart server
        quart_app.run(host='0.0.0.0', port=args.port, debug=False)
    else:
        # Run as CLI
        if not args.pull_request_url:
            raise ValueError("pull_request_url is required when not running as server")

        # Parse review criteria if provided
        review_criteria = {}
        if args.review_criteria:
            try:
                review_criteria = json.loads(args.review_criteria)
            except json.JSONDecodeError:
                raise ValueError("Invalid JSON format for review_criteria")
        
        review_criteria = validate_review_criteria(review_criteria)
        
        # Prepare session state
        session_state = {
            "pull_request_url": args.pull_request_url,
            "review_criteria": review_criteria,
            "severity_threshold": args.severity_threshold,
            "post_comments": args.post_comments
        }

        # Run the agent
        await run_agent_with_common_setup(
            app_name=app_name,
            agent_class=CodeReviewAgent,
            agent_name="code_review_agent",
            session_state=session_state,
        )


def run():
    """Entry point for running the agent."""
    asyncio.run(main())


if __name__ == "__main__":
    run()