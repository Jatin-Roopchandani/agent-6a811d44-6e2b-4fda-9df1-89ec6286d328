# Code Review Agent

An AI-powered code review agent that automatically reviews GitHub pull requests and provides comprehensive feedback on code quality, security, performance, and best practices.

## Features

- **Comprehensive Code Analysis**: Reviews code for quality, security vulnerabilities, performance issues, and documentation
- **GitHub Integration**: Fetches PR details and can post review comments directly to GitHub
- **Structured Feedback**: Provides categorized issues with severity levels and actionable suggestions
- **Flexible Configuration**: Configurable review criteria and severity thresholds
- **Multiple Interfaces**: Available as both CLI tool and REST API server

## Installation

1. Install dependencies:
```bash
uv sync
```

2. Set up environment variables:
```bash
cp .env.example .env
# Edit .env with your API keys
```

## Usage

### CLI Usage

Review a pull request from command line:

```bash
python -m agent.main --pull_request_url "https://github.com/owner/repo/pull/123"
```

With custom review criteria:

```bash
python -m agent.main \
  --pull_request_url "https://github.com/owner/repo/pull/123" \
  --review_criteria '{"code_quality": true, "security": true, "performance": false}' \
  --severity_threshold "medium" \
  --post_comments
```

### Server Usage

Start the API server:

```bash
python -m agent.main --server --port 5000
```

### API Endpoints

#### POST /agent

Reviews a pull request and returns structured feedback.

**Request Body:**
```json
{
  "pull_request_url": "https://github.com/owner/repo/pull/123",
  "review_criteria": {
    "code_quality": true,
    "security": true,
    "performance": true,
    "style": true,
    "documentation": true
  },
  "severity_threshold": "low",
  "post_comments": false
}
```

**Response:**
```json
{
  "review_summary": "Overall assessment of the pull request",
  "comments_added": [
    {
      "file_path": "src/main.py",
      "line_number": 45,
      "comment": "Consider using a more descriptive variable name",
      "severity": "low",
      "category": "code_quality"
    }
  ],
  "issues_found": [
    {
      "category": "security",
      "severity": "high",
      "description": "Potential SQL injection vulnerability",
      "file_path": "src/database.py",
      "line_number": 123,
      "suggestion": "Use parameterized queries instead of string concatenation"
    }
  ],
  "approval_recommendation": "request_changes",
  "success": true,
  "error": null
}
```

#### GET /schema

Returns the OpenAPI schema for the agent endpoint.

## Configuration

### Environment Variables

- `GOOGLE_API_KEY`: Required for Gemini models
- `OPENAI_API_KEY`: Optional, for OpenAI models via LiteLLM
- `ANTHROPIC_API_KEY`: Optional, for Claude models via LiteLLM
- `GITHUB_API_KEY`: Required for posting comments to GitHub PRs
- `GH_TOKEN`: Alternative to GITHUB_API_KEY

### Review Criteria

- `code_quality`: Style, formatting, complexity, maintainability
- `security`: Vulnerabilities, secrets, input validation
- `performance`: Bottlenecks, algorithms, memory usage
- `style`: Code style and formatting consistency
- `documentation`: Comments, API docs, README updates

### Severity Thresholds

- `low`: Report all issues
- `medium`: Report medium, high, and critical issues
- `high`: Report only high and critical issues
- `critical`: Report only critical issues

## Agent Behavior

The agent performs a comprehensive 7-step review process:

1. **Fetch PR Details**: Retrieves PR metadata, changed files, and commit history
2. **Analyze Code Changes**: Examines code for quality, security, and performance issues
3. **Generate Review Comments**: Creates structured, actionable feedback
4. **Post Comments** (optional): Submits review comments to the GitHub PR
5. **Provide Summary**: Generates overall assessment and recommendation

The agent maintains a professional tone, provides constructive feedback, and focuses on actionable improvements rather than criticism.

## Error Handling

The agent includes comprehensive error handling for:
- Invalid PR URLs or inaccessible repositories
- GitHub API authentication failures
- Rate limiting and API quota issues
- Network timeouts and connection problems
- Invalid configuration parameters

All errors return structured JSON responses with descriptive error messages.
