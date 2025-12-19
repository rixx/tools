[private]
default:
    @just --list

# Format code with black
[group('linting')]
black *args=".":
    uvx black {{ args }}

# Check code with black (check only)
[group('linting')]
black-check *args=".":
    just black --check {{ args }}

# Check import sorting with isort (check only)
[group('linting')]
isort-check *args=".":
    just isort --check {{ args }}

# Sort imports with isort
[group('linting')]
isort *args=".":
    uvx isort --profile black {{ args }}

# Run flake8 linter
[group('linting')]
flake8 *args=".":
    uvx flake8 --max-line-length=160 --extend-ignore=E203 {{ args }}

# Run all formatters and linters
[group('linting')]
fmt: black isort flake8

# Run all code quality checks
[group('linting')]
check: black-check isort-check flake8
