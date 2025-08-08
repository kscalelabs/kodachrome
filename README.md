# Using this template

Choose one of the following to set up your new repository.

## Option 1 (recommended): One-time config + script

1) Edit `one_time_setup_config.yaml`
- `distribution_name`: Project/PyPI name (e.g., my-package)
- `import_name`: Python package import name (directory, e.g., my_package)
- `description`: Short summary
- `url`: Project URL (e.g., repository URL)
- `author`, `author_email`: Your details
- `python_min_version`: Minimum Python version (e.g., 3.11)
- `version`: Initial package version (sets `<import_name>/__init__.py`)
- `default_branch`: CI default branch (`master` or `main`)
- `year`: Copyright year

2) Run the one-time setup script from the repository root
- The script reads the config and will:
  - Rename `template_package/` to `<import_name>/`
  - Update `setup.py` (name, description, author, author_email, url, python_requires, paths)
  - Update `pyproject.toml` (ruff `target-version`, isort `known-first-party`)
  - Update `MANIFEST.in` (package directory)
  - Update `Makefile` (displayed project name and Python version)
  - Update `LICENSE` (year and author)
  - Update `.github/workflows/test.yml` and `publish.yml` (Python version; default branch in tests)
  - Update `<import_name>/__init__.py` (`__version__`)
- Requires PyYAML.
- Review and commit the changes when satisfied.

(Optional) After completing setup you may remove `one_time_setup.py` and `one_time_setup_config.yaml`.

## Option 2: Manual setup

### Pick your project details
- Distribution name (project/PyPI name), e.g., "my-package"
- Python package import name (directory name), e.g., "my_package"
- Short description
- Project URL (e.g., GitHub repo URL)
- Author name and email
- Minimum supported Python version (e.g., 3.11)
- Copyright year

### Rename the package directory
- Rename `template_package/` to your chosen Python import name (e.g., `my_package/`).

### Edit these files
- `setup.py`:
  - `name`: distribution/project name
  - `description`: short description
  - `author`: your name
  - `url`: project URL
  - `python_requires`: minimum Python version (e.g., ">=3.11")
  - Update paths referencing the package directory (`template_package/requirements.txt`, `template_package/__init__.py`) to point to your renamed package
  - Optional: add `author_email`, `classifiers`, and console `entry_points` for a CLI

- `pyproject.toml`:
  - `[tool.ruff] target-version`: set to your target (e.g., `py311`)
  - `[tool.ruff.lint.isort] known-first-party`: replace `template_package` with your package import name

- `MANIFEST.in`:
  - Replace `template_package/` with your package directory

- `Makefile`:
  - Update the displayed project name and Python version in the help text

- `LICENSE`:
  - Update the year and author name

- `.github/workflows/test.yml` and `.github/workflows/publish.yml`:
  - Update the `python-version` to your minimum
  - Optional: change the default branch in triggers if using `main` instead of `master`

- `README.md` (this file):
  - Replace the title and content with your project documentation

- `<your_package>/__init__.py`:
  - Set `__version__` to your starting version (e.g., `0.1.0`)

- `<your_package>/requirements.txt`:
  - List runtime dependencies (one per line)

### Start coding
- Place your source code inside the renamed package directory.
- Tests live under `tests/`. Adjust or extend as needed.
