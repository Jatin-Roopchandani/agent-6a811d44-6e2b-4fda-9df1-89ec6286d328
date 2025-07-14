import fnmatch
import itertools
import os
from pathlib import Path
from typing import Callable, List, Optional

from .logger import get_tool_logger

find_text_char_limit = 1000
# Common directories and files to skip
BLACKLIST_PATTERNS = [
    ".git/*",
    "node_modules/*",
    ".next/*",
    ".turbo/*",
    "*.wasm",
    "*.woff2",
    "*.pack",
    "*.pack.gz",
    "*.tar.zst",
    "*.pyc",
    "__pycache__/*",
    "*.so",
    "*.dll",
    "*.dylib",
    "*.exe",
    "*.bin",
    "*.dat",
    "*.db",
    "*.sqlite",
    "*.sqlite3",
    "*.log",
    "*.cache",
    "*.tmp",
    "*.temp",
    "*.swp",
    "*.swo",
    "*.bak",
    "*.backup",
    "*.orig",
    "*.rej",
    "*.patch",
    "*.diff",
    "*.tar",
    "*.gz",
    "*.zip",
    "*.rar",
    "*.7z",
    "*.bz2",
    "*.xz",
    "*.lzma",
    "*.lz4",
    "*.zst",
    "*.tgz",
    "*.tbz2",
    "*.txz",
    "*.tlz",
    "*.tlz4",
    "*.tzst",
    "*.pdf",
    "*.docx",
    "*.doc",
    "*.xls",
    "*.xlsx",
    "*.ppt",
    "*.pptx",
    "*.png",
    "*.jpg",
    "*.jpeg",
    "*.gif",
    "*.bmp",
    "*.tiff",
    "*.ico",
]

# File reading constants
FILE_READ_CHAR_LIMIT = 5000
FILE_READ_TRUNCATED_TEXT = "<TRUNCATED>"

def should_skip_path(path: Path) -> bool:
    """Check if a path should be skipped based on blacklist patterns."""
    path_str = str(path)
    return any(fnmatch.fnmatch(path_str, pattern) for pattern in BLACKLIST_PATTERNS)

class GrepTools:
    def __init__(self, working_dir: Optional[Path] = None):
        if working_dir is None:
            working_dir = Path.cwd()
        self.working_dir = working_dir

    def find_files(
        self, path: str, unix_pattern: str, depth: int = 1, is_case_sensitive: bool = False, **kwargs
    ) -> str:
        """
        Finds files within a specified directory based on a given pattern.

        Args:
            path: The directory to search within.
            unix_pattern: The Unix shell style pattern to match files against.
                    (e.g., '*.txt', 'data*.csv', 'image?.png')
            depth: The maximum directory depth to search (default: 1).
            is_case_sensitive: Whether the pattern matching should be case-sensitive (default: False).

        Returns:
            A string containing a list of files and directories that match the pattern,
            relative to the starting directory. The results are formatted for readability.

            Example:
            ```
            Files:
            * file1.txt
            * file2.txt

            Directories:
            * dir1
            * dir2
            ```
            If no files or directories are found, a message indicating this will be returned.
        """
        logger = get_tool_logger("find_files")
        logger.info(
            f"find_files called with path {path}, pattern {unix_pattern}, depth {depth}, is_case_sensitive {is_case_sensitive}"
        )

        if kwargs:
            err = f"Error: Unexpected arguments: {kwargs}\nSupported args: path, pattern, depth, is_case_sensitive"
            logger.error(err)
            return err

        resolved_path = Path(path).resolve()

        if "*" not in unix_pattern:
            unix_pattern = f"*{unix_pattern}*"

        if self.working_dir not in resolved_path.parents and self.working_dir != resolved_path:
            err = f"Error: {resolved_path} is not a subdirectory of {self.working_dir}. Please provide a relative path, or a subdirectory of {self.working_dir}."
            logger.error(err)
            return err

        if not resolved_path.exists():
            err = f"Error: {resolved_path} does not exist"
            logger.error(err)
            return err

        if resolved_path.is_file():
            err = f"Error: {resolved_path} is a file, not a directory"
            logger.error(err)
            return err

        matcher = fnmatch.fnmatch
        if is_case_sensitive:
            matcher = fnmatch.fnmatchcase

        file_matches = []
        dir_matches = []

        for root, dirs, files in os.walk(resolved_path):
            root_path = Path(root)
            if len(root_path.resolve().relative_to(resolved_path).parts) > depth:
                continue  # Skip directories deeper than the specified depth

            # Skip blacklisted directories
            dirs[:] = [d for d in dirs if not should_skip_path(root_path / d)]

            for file in itertools.chain(dirs, files):
                file_path = root_path / file

                # Skip blacklisted files and directories
                if should_skip_path(file_path):
                    continue

                # Skip dot files and directories
                if any(part.startswith(".") for part in file_path.relative_to(resolved_path).parts):
                    continue

                if file_path.is_file():
                    list_to_append = file_matches
                else:
                    list_to_append = dir_matches

                if matcher(str(file_path), unix_pattern):
                    relative_file_path = file_path.relative_to(resolved_path)
                    list_to_append.append(str(relative_file_path))

        delim = "\n  * "
        files_part = (delim + delim.join(file_matches)) if len(file_matches) > 0 else "\n  No files found"
        dirs_part = (delim + delim.join(dir_matches)) if len(dir_matches) > 0 else "\n  No directories found"

        return_val = f"""\
    Files:{files_part}

    Directories:{dirs_part}

    """
        logger.debug(f"find_files output: {return_val}")
        return return_val

    def find_text_in_files(
        self, unix_pattern: str, path: str, recursive: bool = True, is_case_sensitive: bool = False, **kwargs
    ) -> str:
        """
        Tool to find text in a file or files in a directory using a pattern based on the Unix shell style.
        The path provided should either be absolute or relative to the current working directory.

        This tool will match each line of the file with the provided pattern and prints the line number and the line content.
        If the line contains too many characters, the line content will be replaced with a message indicating it's too long.

        Args:
            unix_pattern: The Unix shell style pattern to match files using.
                Unix shell style:
                    *       matches everything
                    ?       matches any single character
                    [seq]   matches any character in seq
                    [!seq]  matches any char not in seq

                Example:
                * 'class T*' will match the line 'class Team:' but not '    class Team:' because the second line is indented.
                * '*var1: str' will match the line '    var1: str' but not 'var1: str = "test"'
                * '*class Team*' will match both the lines 'class Team:' and 'class TeamMember(BaseTeam):'
                * 'TeamMember' will not match 'class TeamMember:' because the pattern should match the entire line

            path: The path to the file to find text in.
                If not given, will search all file content in the current working directory.
                If the path is a directory, will search all file content in the directory.

            recursive: Set as False to only search specified file or immediate files in the specified directory. Default is True.
            is_case_sensitive: Whether the pattern should be case-sensitive.

        Returns:
            A string containing the lines that match the pattern, along with the filename and line number.
        """
        logger = get_tool_logger("find_text_in_files")
        logger.info(
            f"find_text_in_files called with path {path}, pattern {unix_pattern}, recursive {recursive}, is_case_sensitive {is_case_sensitive}"
        )

        if kwargs:
            err = f"Error: Unexpected arguments: {kwargs}\nSupported args: path, pattern, recursive, is_case_sensitive"
            logger.error(err)
            return err

        # Check for wildcard pattern
        if unix_pattern == "*":
            err = "Error: pattern * is too broad. Please provide a more specific pattern"
            logger.error(err)
            return err

        if "*" not in unix_pattern:
            unix_pattern = f"*{unix_pattern}*"

        resolved_path = Path(path).resolve()

        if self.working_dir not in resolved_path.parents and self.working_dir != resolved_path:
            err = f"Error: {resolved_path} is not a subdirectory of {self.working_dir}. Please provide a relative path, or a subdirectory of {self.working_dir}."
            logger.error(err)
            return err

        if not resolved_path.exists():
            err = f"Error: {resolved_path} does not exist"
            logger.error(err)
            return err

        matcher = fnmatch.fnmatch
        if is_case_sensitive:
            matcher = fnmatch.fnmatchcase

        if resolved_path.is_file():
            paths = [resolved_path]
        elif recursive:
            paths = []
            for p in resolved_path.rglob("*"):
                # Skip dot files and directories
                if any(part.startswith(".") for part in p.relative_to(resolved_path).parts):
                    continue

                if p.is_file() and not should_skip_path(p):
                    paths.append(p)
        else:
            paths = [p for p in resolved_path.iterdir() if p.is_file() and not should_skip_path(p)]

        file_matches = {}  # Changed from defaultdict to regular dict

        for file_path in paths:
            try:
                with open(file_path, "r") as f:
                    matches_in_file = []
                    for i, line in enumerate(f):  # Removed readlines() for memory efficiency
                        if matcher(line, unix_pattern):
                            if len(line) > find_text_char_limit:
                                content = f"Line {i + 1}: <Too many characters>"
                            else:
                                content = f"Line {i + 1}: {line.strip()}"  # strip whitespace
                            matches_in_file.append(content)

                    if matches_in_file:  # Only add to file_matches if there are matches
                        file_matches[str(file_path.relative_to(Path(path).resolve()))] = matches_in_file

            except Exception as e:
                logger.warning(f"Error reading file {file_path}: {e}")
                continue  # Skip file on error

        total_file_matches = ""
        for rel_path, matches in file_matches.items():
            total_file_matches += f"\nPattern matches found in '{rel_path}':\n" + "\n".join(matches)

        if not total_file_matches:
            err = "Error: No matches found."
            logger.error(err)
            return err
        logger.debug(f"find_text_in_files output: {total_file_matches}")
        return total_file_matches

    def read_file(self, path: str, start_line: Optional[int] = None, end_line: Optional[int] = None) -> str:
        """
        Reads the contents of a file.

        Args:
            path: The path to the file to read, relative to the working directory.
            start_line: Optional line number to start reading from (1-indexed)
            end_line: Optional line number to end reading at (1-indexed)

        Returns:
            The contents of the file as a string. If the file is too large, it will be truncated.
            If start_line and end_line are provided, only returns content between those lines.

        Raises:
            ValueError: If the path is not within the working directory or if the file cannot be read.
        """
        logger = get_tool_logger("read_file")
        
        resolved_path = Path(path).resolve()

        if self.working_dir not in resolved_path.parents and self.working_dir != resolved_path:
            err = f"Error: {resolved_path} is not a subdirectory of {self.working_dir}. Please provide a relative path, or a subdirectory of {self.working_dir}."
            logger.error(err)
            return err

        if not resolved_path.is_file():
            err = f"Error: {resolved_path} is not a file"
            logger.error(err)
            return err

        try:
            with open(resolved_path, "r") as f:
                # Read all lines if no line range specified
                if start_line is None and end_line is None:
                    content = f.read()
                    if len(content) > FILE_READ_CHAR_LIMIT:
                        return f"{content[:FILE_READ_CHAR_LIMIT]}\n{FILE_READ_TRUNCATED_TEXT}"
                    return content

                # Read specific line range
                lines = []
                for i, line in enumerate(f, 1):  # 1-indexed line numbers
                    if start_line is not None and i < start_line:
                        continue
                    if end_line is not None and i > end_line:
                        break
                    lines.append(line)

                content = "".join(lines)
                if len(content) > FILE_READ_CHAR_LIMIT:
                    return f"{content[:FILE_READ_CHAR_LIMIT]}\n{FILE_READ_TRUNCATED_TEXT}"
                return content

        except Exception as e:
            err = f"Error reading file {resolved_path}: {e}"
            logger.error(err)
            return err

    def get_tools(self) -> List[Callable]:
        return [
            self.find_files,
            self.find_text_in_files,
            self.read_file,
        ]