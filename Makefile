# Define the virtual environment directory and the Python interpreter within it.
VENV_DIR := .venv
VENV_PYTHON := $(VENV_DIR)/bin/python

# Set the default goal to 'help'
.DEFAULT_GOAL := help

# Phony targets are rules that don't represent files.
.PHONY: help install uninstall test test-slow test-all clean

help:
	@echo "Available commands:"
	@echo "  install     - Create a virtual environment and install the project in editable mode."
	@echo "  test        - Run fast tests only (skips slow integration tests)."
	@echo "  test-slow   - Run only slow integration tests (~2 min docling import)."
	@echo "  test-all    - Run all tests (fast + slow)."
	@echo "  uninstall   - Remove the virtual environment and cached files."
	@echo "  clean       - Remove all build artifacts, caches, and the virtual environment."

# This rule depends on the virtual environment's Python executable existing.
# If it doesn't, make will run the rule to create it first.
install: $(VENV_PYTHON)
	@echo "Installing project in editable mode with test dependencies..."
	@$(VENV_PYTHON) -m pip install -e '.[test]'

# This rule runs pytest using the virtual environment's interpreter.
# We depend on 'install' to ensure the package is installed in editable mode,
# which is required for Python to find the package in the 'src' directory.
test: install
	$(VENV_PYTHON) -m pytest

test-slow: install
	$(VENV_PYTHON) -m pytest -m slow

test-all: install
	$(VENV_PYTHON) -m pytest -m ''

# This rule removes the virtual environment and cached files.
uninstall:
	rm -rf $(VENV_DIR)
	find . -type d -name "__pycache__" -exec rm -r {} +
	find . -type d -name ".pytest_cache" -exec rm -r {} +

# This rule cleans everything that 'uninstall' does, plus build artifacts.
clean: uninstall
	rm -rf build/
	find . -type d -name "*.egg-info" -exec rm -r {} +

# This is a helper rule that creates the virtual environment if it's missing.
# The 'install' rule depends on its target file.
$(VENV_PYTHON):
	@echo "Creating virtual environment in $(VENV_DIR) and upgrading dependencies..."
	@echo "This may take a few moments. Please be patient."
	@python3 -m venv --upgrade-deps $(VENV_DIR) < /dev/null
	@echo "Virtual environment created."
	@echo "To activate it, run: source $(VENV_DIR)/bin/activate"
	@echo "To deactivate it, run: deactivate"
