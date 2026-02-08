# Development

This document provides instructions for setting up a development environment to contribute to `gamagama-pdf`.

## Setup

This project uses a local Python virtual environment managed via the `Makefile`.

1.  **Install Dependencies**: Run the following command. It will create a virtual environment in `.venv/` if one does not exist, and then install the project and its test dependencies into it.
    ```bash
    make install
    ```

2.  **Activate the Virtual Environment**: To use the tools installed in the virtual environment (like `gg-pdf` and `pytest`) directly from your shell, you must activate it.
    *   On macOS and Linux:
        ```bash
        source .venv/bin/activate
        ```
    *   On Windows (PowerShell):
        ```powershell
        .venv\Scripts\Activate.ps1
        ```
    Your shell prompt should change to indicate that the environment is active.

## Running Tests

There are two ways to run the test suite.

### 1. Using the Makefile (Recommended for CI/Clean State)

You can run the test suite using the `make` command:
```bash
make test
```
**Why use this?**
This command automatically ensures that your virtual environment is created and all dependencies are up-to-date before running the tests. It is the safest way to ensure you are testing against the correct environment state.

### 2. Manual Execution (Faster)

If you have already installed dependencies and activated your virtual environment (see Setup step 2), you can run `pytest` directly:
```bash
pytest
```
**Why use this?**
This is faster than `make test` because it skips the dependency installation check. It is ideal for rapid iteration during development (e.g., TDD cycles).
