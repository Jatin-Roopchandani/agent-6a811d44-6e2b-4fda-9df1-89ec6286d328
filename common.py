import logging
import os
import subprocess
from pathlib import Path
from typing import List, Optional

from google.adk.runners import InMemoryRunner
from google.genai import types

from logger import get_logger


def redeclare_scm_envs():
    """
    The envs passed aren't as expected by gh cli etc. Redeclare them accordingly.
    """
    if os.environ.get("GITHUB_API_KEY") and not (os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")):
        os.environ["GH_TOKEN"] = os.environ["GITHUB_API_KEY"]


def is_gh_authenticated() -> None:
    """Check if GitHub CLI is authenticated and raise error if not."""

    if os.system("gh auth status > /dev/null 2>&1; echo $?") != 0:
        raise ValueError("❌ GitHub is not authenticated, run `gh auth login` or set the GH_TOKEN environment variable")


def clone_repository(git_url: str, branch: Optional[str] = None) -> str:
    """Clone the repository and return the path to the cloned directory."""
    # Create a temporary directory name based on the repo name
    repo_name = git_url.split("/")[-1].replace(".git", "")
    clone_dir = Path.cwd() / f"cloned_{repo_name}"

    # Remove existing clone if it exists
    if clone_dir.exists():
        import shutil

        shutil.rmtree(clone_dir)

    try:
        # Clone the repository
        if branch:
            cmd = ["git", "clone", "--branch", branch, git_url, str(clone_dir)]
        else:
            cmd = ["git", "clone", git_url, str(clone_dir)]
        subprocess.run(cmd, check=True, capture_output=True, text=True)
        logger = get_logger("common")
        logger.info(f"Successfully cloned repository to {clone_dir}")
        return str(clone_dir)
    except subprocess.CalledProcessError as e:
        logger = get_logger("common")
        logger.error(f"Failed to clone repository: {e.stderr}")
        if branch:
            raise ValueError(f"Failed to clone repository {git_url} (branch: {branch}): {e.stderr}")
        else:
            raise ValueError(f"Failed to clone repository {git_url}: {e.stderr}")


def raise_if_env_absent(required_api_keys: List[str]):
    """
    Check for required environment variables.

    Args:
        required_api_keys: List of required environment variable names (e.g., ['ANTHROPIC_API_KEY', 'GOOGLE_API_KEY'])
    """
    errors = []

    for api_key in required_api_keys:
        if os.environ.get(api_key, None) is None:
            errors.append(f"❌ {api_key} is not set")

    if len(errors) > 0:
        raise ValueError("The following checks failed:\n" + "\n".join(errors))


async def run_agent_with_common_setup(
    app_name: str, agent_class, agent_name: str, session_state: dict, user_id: str = "1234"
):
    """
    Common setup for running an agent with InMemoryRunner.

    Args:
        app_name: Name of the application
        agent_class: The agent class to instantiate
        agent_name: Name for the agent instance
        session_state: State dictionary to initialize the session with
        user_id: User ID for the session
    """
    logging.basicConfig(level=logging.INFO)
    logger = get_logger(app_name)

    runner = InMemoryRunner(
        app_name=app_name,
        agent=agent_class(name=agent_name),
    )

    session = await runner.session_service.create_session(app_name=app_name, user_id=user_id, state=session_state)

    async for event in runner.run_async(
        user_id=user_id,
        session_id=session.id,
        new_message=types.Content(role="user", parts=[types.Part(text="Follow the system instruction.")]),
    ):
        logger.info(event.model_dump_json(exclude_unset=True, exclude_defaults=True, exclude_none=True))