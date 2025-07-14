from typing import Any, AsyncGenerator, Dict, List, Optional
import re
import os
import requests
from github import Github
from github.Repository import Repository
from github.PullRequest import PullRequest

from google.adk.agents import BaseAgent, LlmAgent
from google.adk.agents.invocation_context import InvocationContext
from google.adk.events import Event
from google.genai import types
from pydantic import BaseModel
from typing_extensions import override

from tools.bash_tool import BashTools
from tools.grep_tool import GrepTools
from google.adk.models.lite_llm import LiteLlm
from utils.structure_output import structure_output

# Configure your preferred model
CLAUDE_4_SONNET = LiteLlm("anthropic/claude-4-sonnet-20250514")
GEMINI_2_5_FLASH = "gemini-2.5-flash"
MODEL = CLAUDE_4_SONNET


# Pydantic models for structured output
class ReviewComment(BaseModel):
    """Individual review comment model"""
    file_path: str
    line_number: int
    comment: str
    severity: str  # low, medium, high, critical
    category: str  # code_quality, security, performance, documentation

class Issue(BaseModel):
    """Issue found during review"""
    category: str
    severity: str
    description: str
    file_path: str
    line_number: Optional[int] = None
    suggestion: Optional[str] = None

class ReviewCriteria(BaseModel):
    """Review criteria configuration"""
    code_quality: bool = True
    security: bool = True
    performance: bool = True
    style: bool = True
    documentation: bool = True

class ReviewResult(BaseModel):
    """Final review result wrapper"""
    review_summary: str
    comments_added: List[ReviewComment]
    issues_found: List[Issue]
    approval_recommendation: str  # approve, request_changes, comment
    success: bool
    error: Optional[str] = None

class CodeReviewAgent(BaseAgent):
    """
    Code review agent that automatically reviews pull requests and adds review comments.
    
    This agent:
    - Fetches pull request details and changed files
    - Analyzes code changes for quality, security, and performance issues
    - Generates structured review feedback
    - Posts review comments to the pull request
    """
    
    @override
    async def _run_async_impl(self, ctx: InvocationContext) -> AsyncGenerator[Event, None]:
        # Check if required inputs exist in session state
        if not ctx.session.state.get("pull_request_url"):
            yield Event(
                content=types.Content(
                    role="system", 
                    parts=[types.Part(text="No pull_request_url found in session state. Please provide a 'pull_request_url' in the session state.")]
                ),
                author=self.name,
            )
            return

        # Get inputs from session state
        pull_request_url = ctx.session.state.get("pull_request_url")
        review_criteria = ctx.session.state.get("review_criteria", {})
        severity_threshold = ctx.session.state.get("severity_threshold", "low")
        
        # Parse PR URL to extract owner, repo, and PR number
        pr_info = self._parse_pr_url(pull_request_url)
        if not pr_info:
            yield Event(
                content=types.Content(
                    role="system", 
                    parts=[types.Part(text="Invalid pull request URL format. Expected format: https://github.com/owner/repo/pull/123")]
                ),
                author=self.name,
            )
            return
        
        # Step 1: Fetch pull request details
        yield Event(
            content=types.Content(
                role="assistant",
                parts=[types.Part(text="🔍 Fetching pull request details...")]
            ),
            author=self.name,
        )
        
        async for event in self._fetch_pr_details(ctx, pr_info):
            yield event
        
        if "pr_details" not in ctx.session.state:
            yield Event(
                content=types.Content(
                    role="system", 
                    parts=[types.Part(text="Failed to fetch pull request details.")]
                ),
                author=self.name,
            )
            return
        
        # Step 2: Analyze code changes
        yield Event(
            content=types.Content(
                role="assistant",
                parts=[types.Part(text="🔍 Analyzing code changes...")]
            ),
            author=self.name,
        )
        
        async for event in self._analyze_code_changes(ctx, review_criteria, severity_threshold):
            yield event
        
        if "code_analysis" not in ctx.session.state:
            yield Event(
                content=types.Content(
                    role="system", 
                    parts=[types.Part(text="Failed to analyze code changes.")]
                ),
                author=self.name,
            )
            return
        
        # Step 3: Generate review comments
        yield Event(
            content=types.Content(
                role="assistant",
                parts=[types.Part(text="💬 Generating review comments...")]
            ),
            author=self.name,
        )
        
        async for event in self._generate_review_comments(ctx):
            yield event
        
        if "review_comments" not in ctx.session.state:
            yield Event(
                content=types.Content(
                    role="system", 
                    parts=[types.Part(text="Failed to generate review comments.")]
                ),
                author=self.name,
            )
            return
        
        # Step 4: Post review comments (if enabled)
        post_comments = ctx.session.state.get("post_comments", False)
        if post_comments:
            yield Event(
                content=types.Content(
                    role="assistant",
                    parts=[types.Part(text="📝 Posting review comments to pull request...")]
                ),
                author=self.name,
            )
            
            async for event in self._post_review_comments(ctx, pr_info):
                yield event
        
        # Step 5: Generate final structured result
        async for event in self._generate_final_result(ctx):
            yield event
        
        # Return the final result
        if "final_result" in ctx.session.state:
            result = ctx.session.state["final_result"]
            success_msg = "✅ Code review completed successfully!" if result.get("success") else "❌ Code review failed."
            yield Event(
                content=types.Content(
                    role="assistant",
                    parts=[types.Part(text=f"{success_msg}\n\nSummary: {result.get('review_summary', 'No summary available')}")]
                ),
                author=self.name,
            )
    
    def _parse_pr_url(self, url: str) -> Optional[Dict[str, str]]:
        """Parse GitHub PR URL to extract owner, repo, and PR number."""
        pattern = r'https://github\.com/([^/]+)/([^/]+)/pull/(\d+)'
        match = re.match(pattern, url)
        if match:
            return {
                "owner": match.group(1),
                "repo": match.group(2),
                "pr_number": match.group(3)
            }
        return None
    
    async def _fetch_pr_details(self, ctx: InvocationContext, pr_info: Dict[str, str]) -> AsyncGenerator[Event, None]:
        """Fetch pull request details using GitHub API."""
        fetch_agent = LlmAgent(
            name="fetch_pr_details",
            model=MODEL,
            instruction=f"""
You are a GitHub API expert. Fetch pull request details for:
- Owner: {pr_info['owner']}
- Repository: {pr_info['repo']}
- PR Number: {pr_info['pr_number']}

Use the GitHub CLI (gh) to fetch:
1. PR metadata (title, description, author, target branch)
2. List of changed files with their diff content
3. Commit messages and change context

Store the results in a structured format with:
- pr_metadata: title, description, author, target_branch
- changed_files: list of files with their diff content
- commits: list of commit messages
- file_types: detected programming languages
            """,
            tools=[
                *BashTools(
                    allowed_commands=["gh", "curl", "jq"],
                    working_dir=None
                ).get_tools()
            ],
            output_key="pr_details",
        )
        
        ctx.branch = fetch_agent.name
        async for event in fetch_agent.run_async(ctx):
            yield event
    
    async def _analyze_code_changes(self, ctx: InvocationContext, review_criteria: Dict, severity_threshold: str) -> AsyncGenerator[Event, None]:
        """Analyze code changes for quality, security, and performance issues."""
        pr_details = ctx.session.state.get("pr_details", "")
        
        analyze_agent = LlmAgent(
            name="analyze_code_changes",
            model=MODEL,
            instruction=f"""
You are a senior software engineer performing a comprehensive code review.

PR Details:
{pr_details}

Review Criteria:
{review_criteria}

Severity Threshold: {severity_threshold}

Analyze the code changes and identify issues in these categories:
1. Code Quality: style, formatting, complexity, maintainability, naming conventions
2. Security: vulnerabilities, hardcoded secrets, input validation, authentication
3. Performance: bottlenecks, inefficient algorithms, memory leaks, database queries
4. Documentation: comments, API docs, README updates
5. Testing: test coverage, edge cases, error handling

For each issue found, provide:
- Category (code_quality, security, performance, documentation, testing)
- Severity (low, medium, high, critical)
- Description of the issue
- File path and line number (if applicable)
- Suggested improvement

Focus on actionable feedback that helps improve the code.
            """,
            output_key="code_analysis",
        )
        
        ctx.branch = analyze_agent.name
        async for event in analyze_agent.run_async(ctx):
            yield event
    
    async def _generate_review_comments(self, ctx: InvocationContext) -> AsyncGenerator[Event, None]:
        """Generate structured review comments based on the analysis."""
        code_analysis = ctx.session.state.get("code_analysis", "")
        
        comment_agent = LlmAgent(
            name="generate_review_comments",
            model=MODEL,
            instruction=f"""
Based on the code analysis, generate structured review comments:

Code Analysis:
{code_analysis}

Create review comments in the following format for each issue:
- File path where the comment should be added
- Line number (if applicable)
- Comment text with constructive feedback
- Severity level (low, medium, high, critical)
- Category (code_quality, security, performance, documentation, testing)

Make comments:
- Constructive and actionable
- Professional and helpful
- Specific with code examples when possible
- Focused on improvement rather than criticism

Output the result in the following JSON schema:
<output_json_schema>
{ReviewResult.model_json_schema()}
</output_json_schema>

Provide:
1. review_summary: Overall assessment of the PR
2. comments_added: List of specific review comments
3. issues_found: Categorized list of issues
4. approval_recommendation: approve, request_changes, or comment
5. success: true/false
            """,
            output_key="raw_review_comments",
        )
        
        ctx.branch = comment_agent.name
        async for event in comment_agent.run_async(ctx):
            yield event
        
        # Structure the output
        if "raw_review_comments" in ctx.session.state:
            async for event in structure_output("raw_review_comments", ReviewResult, "review_comments", ctx, model=GEMINI_2_5_FLASH):
                yield event
    
    async def _post_review_comments(self, ctx: InvocationContext, pr_info: Dict[str, str]) -> AsyncGenerator[Event, None]:
        """Post review comments to the pull request."""
        review_comments = ctx.session.state.get("review_comments", {})
        
        post_agent = LlmAgent(
            name="post_review_comments",
            model=MODEL,
            instruction=f"""
Post review comments to the GitHub pull request:
- Owner: {pr_info['owner']}
- Repository: {pr_info['repo']}
- PR Number: {pr_info['pr_number']}

Review Comments:
{review_comments}

Use the GitHub CLI (gh) to:
1. Post line-specific comments for each issue
2. Submit an overall review with summary
3. Handle API rate limits and authentication
4. Provide fallback if posting fails

Format comments with proper markdown and code blocks.
Return success/failure status for each comment posted.
            """,
            tools=[
                *BashTools(
                    allowed_commands=["gh", "curl", "jq"],
                    working_dir=None
                ).get_tools()
            ],
            output_key="post_result",
        )
        
        ctx.branch = post_agent.name
        async for event in post_agent.run_async(ctx):
            yield event
    
    async def _generate_final_result(self, ctx: InvocationContext) -> AsyncGenerator[Event, None]:
        """Generate the final structured result."""
        review_comments = ctx.session.state.get("review_comments", {})
        post_result = ctx.session.state.get("post_result", "")
        
        # Use the structured review comments if available
        if review_comments:
            ctx.session.state["final_result"] = review_comments
        else:
            # Fallback to a basic success result
            ctx.session.state["final_result"] = {
                "review_summary": "Code review completed",
                "comments_added": [],
                "issues_found": [],
                "approval_recommendation": "comment",
                "success": True,
                "error": None
            }
        
        yield Event(
            content=types.Content(
                role="system",
                parts=[types.Part(text="Final result generated")]
            ),
            author=self.name,
        )