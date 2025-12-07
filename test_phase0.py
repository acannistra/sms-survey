"""Quick test script to verify Phase 0 setup."""

import sys


def test_imports():
    """Test that all core modules can be imported."""
    print("Testing imports...")

    try:
        import app
        print("  ✓ app module")
    except ImportError as e:
        print(f"  ✗ app module: {e}")
        return False

    try:
        import app.config
        print("  ✓ app.config module")
    except ImportError as e:
        print(f"  ✗ app.config module: {e}")
        return False

    try:
        import app.logging_config
        print("  ✓ app.logging_config module")
    except ImportError as e:
        print(f"  ✗ app.logging_config module: {e}")
        return False

    return True


def test_dependencies():
    """Test that all required dependencies are installed."""
    print("\nTesting dependencies...")

    dependencies = [
        "fastapi",
        "sqlalchemy",
        "alembic",
        "pydantic",
        "pydantic_settings",
        "twilio",
        "jinja2",
        "yaml",
        "pytest",
    ]

    all_ok = True
    for dep in dependencies:
        try:
            __import__(dep)
            print(f"  ✓ {dep}")
        except ImportError as e:
            print(f"  ✗ {dep}: {e}")
            all_ok = False

    return all_ok


def test_directory_structure():
    """Test that all required directories exist."""
    print("\nTesting directory structure...")

    from pathlib import Path

    required_dirs = [
        "app",
        "app/models",
        "app/schemas",
        "app/services",
        "app/routes",
        "app/middleware",
        "tests",
        "tests/unit",
        "tests/integration",
        "tests/fixtures",
        "alembic",
        "alembic/versions",
        "surveys",
    ]

    all_ok = True
    for dir_path in required_dirs:
        path = Path(dir_path)
        if path.exists() and path.is_dir():
            print(f"  ✓ {dir_path}/")
        else:
            print(f"  ✗ {dir_path}/ - missing")
            all_ok = False

    return all_ok


def test_files_exist():
    """Test that all required files exist."""
    print("\nTesting required files...")

    from pathlib import Path

    required_files = [
        "pyproject.toml",
        "README.md",
        ".env.example",
        ".gitignore",
        "app/__init__.py",
        "app/config.py",
        "app/logging_config.py",
        "surveys/README.md",
    ]

    all_ok = True
    for file_path in required_files:
        path = Path(file_path)
        if path.exists() and path.is_file():
            print(f"  ✓ {file_path}")
        else:
            print(f"  ✗ {file_path} - missing")
            all_ok = False

    return all_ok


def test_python_version():
    """Test Python version meets requirements."""
    print("\nTesting Python version...")

    version_info = sys.version_info
    version_str = f"{version_info.major}.{version_info.minor}.{version_info.micro}"

    if version_info >= (3, 11):
        print(f"  ✓ Python {version_str} (>= 3.11)")
        return True
    else:
        print(f"  ✗ Python {version_str} (< 3.11 required)")
        return False


def main():
    """Run all Phase 0 verification tests."""
    print("=" * 60)
    print("Phase 0 Setup Verification")
    print("=" * 60)

    results = {
        "Python Version": test_python_version(),
        "Imports": test_imports(),
        "Dependencies": test_dependencies(),
        "Directory Structure": test_directory_structure(),
        "Required Files": test_files_exist(),
    }

    print("\n" + "=" * 60)
    print("Summary")
    print("=" * 60)

    all_passed = True
    for test_name, result in results.items():
        status = "✓ PASS" if result else "✗ FAIL"
        print(f"{test_name:25} {status}")
        if not result:
            all_passed = False

    print("=" * 60)

    if all_passed:
        print("\n🎉 Phase 0 setup completed successfully!")
        return 0
    else:
        print("\n❌ Some tests failed. Please review the output above.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
