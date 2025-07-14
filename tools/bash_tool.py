import asyncio
import subprocess
from typing import Awaitable, Callable, List, Optional

from .logger import get_tool_logger

truncate_str = "<truncated>"

class BashTools:
    def __init__(
        self,
        allowed_commands: Optional[List[str]] = None,
        truncate_length: Optional[int] = None,
        working_dir: Optional[str] = None,
    ):
        """
        Initialize BashTools with configuration options.

        Args:
            allowed_commands: List of commands that are allowed to be executed
            truncate_length: Maximum length of output before truncation
            working_dir: Working directory for command execution
        """
        self.allowed_commands = allowed_commands or []
        self.truncate_length = truncate_length
        self.working_dir = working_dir

    def _create_runtime_cli_tool(self, command: str):
        """Create a runtime CLI tool for a specific command."""
        func_name = f"{command}_cli"
        logger = get_tool_logger(func_name)

        async def cli_tool(args: list[str]) -> str:
            logger.info(f"{func_name} called with command: {command} {args}")
            process = await asyncio.create_subprocess_exec(
                command,
                *args,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                cwd=self.working_dir,
            )
            stdout, stderr = await process.communicate()
            if process.returncode != 0:
                err_msg = stderr.decode("utf-8")
                err_str = f"Command {command} {args} failed with return code {process.returncode} and stderr: {err_msg}"
                logger.error(err_str)
                return f"Error: {err_str}"
            output = stdout.decode("utf-8")
            if self.truncate_length and len(output) > self.truncate_length:
                output = output[: self.truncate_length] + truncate_str
            logger.info(f"{func_name} output: {output}")
            return output

        cli_tool.__name__ = func_name
        cli_tool.__doc__ = f"""
        Run a {command}.
        {f"Note: The output will be truncated to {self.truncate_length} characters, ending with {truncate_str} if it is longer than that." if self.truncate_length else ""}

        Args:
            args: list[str]: The arguments to pass to the command.

        Returns:
            The output of the {command}.
        """
        return cli_tool

    def get_tools(self) -> List[Callable[[list[str]], Awaitable[str]]]:
        """
        Get list of available bash tools based on allowed commands.

        Returns:
            List of callable tools for the allowed commands
        """
        return [self._create_runtime_cli_tool(command) for command in self.allowed_commands]
