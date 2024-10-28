from pylint.checkers import BaseChecker
import os


class PytestNameChecker(BaseChecker):

    name = "pytest-naming"
    priority = -1
    msgs = {
        "W9001": (
            "Test file does not follow naming convention: must be test_*.py or *_test.py",
            "invalid-pytest-filename",
            "All test files must be named test_*.py or *_test.py",
        ),
    }

    options = (
        (
            "allowed-test-file-patterns",
            {
                "default": ("__init__.py", "conftest.py", "helpers.py", "fixtures.py"),
                "type": "csv",
                "metavar": "<pattern>",
                "help": "Files that are allowed in test directories without following the naming convention",
            },
        ),
        (
            "allowed-test-dirs",
            {
                "default": ("helpers", "fixtures", "utils", "common"),
                "type": "csv",
                "metavar": "<dirname>",
                "help": "Directories under tests/ where files can ignore the naming convention",
            },
        ),
    )

    def process_module(self, node):
        """Process a module."""
        filepath = node.stream().name

        # Check if file is in a tests directory
        path_parts = filepath.split(os.sep)
        if "tests" in path_parts:
            filename = os.path.basename(filepath)

            # Skip if filename matches any of the allowed patterns
            if filename in self.config.allowed_test_file_patterns:
                return

            # Skip if file is in an allowed directory
            test_index = path_parts.index("tests")
            if len(path_parts) > test_index + 1:
                parent_dir = path_parts[test_index + 1]
                if parent_dir in self.config.allowed_test_dirs:
                    return

            if filename.endswith(".py") and not (filename.startswith("test_") or filename.endswith("_test.py")):
                self.add_message("W9001", line=1)


def register(linter):
    """Register the checker."""
    linter.register_checker(PytestNameChecker(linter))
