# Publishing to PyPI

This guide covers how to build and publish Attach Gateway to PyPI for distribution.

## Prerequisites

### 1. Install Build Tools

```bash
pip install build twine
```

### 2. PyPI Account Setup

- Create accounts on [TestPyPI](https://test.pypi.org/account/register/) and [PyPI](https://pypi.org/account/register/)
- Generate API tokens:
  - TestPyPI: https://test.pypi.org/manage/account/token/
  - PyPI: https://pypi.org/manage/account/token/
- Configure tokens in `~/.pypirc`:

```ini
[distutils]
index-servers =
    pypi
    testpypi

[pypi]
username = __token__
password = pypi-YOUR_API_TOKEN_HERE

[testpypi]
repository = https://test.pypi.org/legacy/
username = __token__
password = pypi-YOUR_TESTPYPI_TOKEN_HERE
```

## Build Process

### 1. Pre-build Checklist

Ensure all components are properly configured:

- [ ] Version updated in `attach/__init__.py`
- [ ] `LICENSE` file exists
- [ ] All packages listed in `pyproject.toml` packages array:
  ```toml
  packages = ["attach", "auth", "middleware", "mem", "proxy", "a2a", "attach_pydid"]
  ```
- [ ] Dependencies are up to date in `pyproject.toml`
- [ ] Tests pass: `pytest`

### 2. Clean Build

```bash
# Remove previous builds
rm -rf dist/ .venv/

# Create fresh virtual environment
python -m venv .venv && source .venv/bin/activate

# Install build dependencies
pip install -U build twine
```

### 3. Build Package

```bash
# Build source distribution and wheel
python -m build

# Verify build contents
ls -la dist/
# Should show: attach_dev-X.Y.Z.tar.gz and attach_dev-X.Y.Z-py3-none-any.whl
```

### 4. Local Testing

Test the built package before publishing:

```bash
# Install from wheel
pip install dist/attach_dev-*.whl

# Test basic import
python -c "import attach; print(attach.__version__)"

# Test CLI command
attach-gateway --help

# Test with memory backend disabled
export MEM_BACKEND=none
python -c "import attach; print('✅ Import successful')"
```

## Publishing Process

### 1. Test on TestPyPI (Recommended)

Always test on TestPyPI first:

```bash
# Upload to TestPyPI
twine upload --repository testpypi dist/*

# Test installation in a fresh environment
# Create a completely separate test directory
mkdir test-attach-install && cd test-attach-install

# Create fresh virtual environment
python -m venv test-env && source test-env/bin/activate

# Test installation from TestPyPI
pip install --index-url https://test.pypi.org/simple/ attach-dev

# Verify it works
attach-gateway --help

# Test basic functionality
python -c "import attach; print(f'✅ Installed version: {attach.__version__}')"

# Clean up test directory
cd .. && rm -rf test-attach-install
```

### 2. Publish to Production PyPI

Once TestPyPI testing is successful:

```bash
# Upload to production PyPI
twine upload dist/*

# Verify on PyPI
pip install attach-dev
attach-gateway --help
```

## Version Management

### Semantic Versioning

Follow semantic versioning (MAJOR.MINOR.PATCH):

- **PATCH** (0.1.1): Bug fixes, no API changes
- **MINOR** (0.2.0): New features, backward compatible
- **MAJOR** (1.0.0): Breaking changes

### Update Version

Update version in `attach/__init__.py`:

```python
__version__ = "0.1.1"  # Update this line
```

### Git Tagging

Tag releases for tracking:

```bash
# Create and push tag
git tag v0.1.1
git push origin v0.1.1

# Or create annotated tag with message
git tag -a v0.1.1 -m "Release version 0.1.1"
git push origin v0.1.1
```

## Troubleshooting

### Common Build Issues

**Missing LICENSE file:**
```bash
# Create LICENSE file if missing
cat > LICENSE << 'EOF'
MIT License
...
EOF
```

**Package not found after install:**
```bash
# Check if all packages are included in pyproject.toml
grep -A 10 "packages.*=" pyproject.toml
```

**Import errors:**
```bash
# Test with minimal memory backend
export MEM_BACKEND=none
python -c "import attach"
```

### Version Conflicts

If you need to republish the same version:

```bash
# Delete from TestPyPI (cannot delete from production PyPI)
# Or increment patch version
```

### Authentication Issues

```bash
# Check PyPI credentials
twine check dist/*

# Test authentication
twine upload --repository testpypi dist/* --verbose
```

## Automation (Future)

For CI/CD automation, consider GitHub Actions:

```yaml
# .github/workflows/publish.yml
name: Publish to PyPI
on:
  release:
    types: [published]
jobs:
  publish:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - name: Set up Python
        uses: actions/setup-python@v4
        with:
          python-version: '3.12'
      - name: Install dependencies
        run: pip install build twine
      - name: Build package
        run: python -m build
      - name: Publish to PyPI
        env:
          TWINE_USERNAME: __token__
          TWINE_PASSWORD: ${{ secrets.PYPI_API_TOKEN }}
        run: twine upload dist/*
```

## Quick Reference

### Complete Build & Publish Workflow

```bash
# 1. Clean environment
rm -rf dist/ && python -m venv .venv && source .venv/bin/activate

# 2. Install tools
pip install build twine

# 3. Build
python -m build

# 4. Test locally
pip install dist/attach_dev-*.whl && attach-gateway --help

# 5. Test on TestPyPI
twine upload --repository testpypi dist/*

# 6. Publish to PyPI
twine upload dist/*
```

---

For questions or issues with the publishing process, refer to the [PyPI documentation](https://packaging.python.org/tutorials/packaging-projects/) or open an issue in the repository. 