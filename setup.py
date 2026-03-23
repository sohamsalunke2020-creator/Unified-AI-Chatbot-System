#!/usr/bin/env python
"""
Setup and Installation Script for Unified Chatbot System
Handles initial setup and configuration
"""

import os
import sys
import subprocess
from pathlib import Path
import shutil


def print_header(text):
    """Print formatted header"""
    print("\n" + "=" * 60)
    print(f"  {text}")
    print("=" * 60 + "\n")


def print_step(step_num, text):
    """Print step message"""
    print(f"[{step_num}] {text}")


def check_python_version():
    """Check if Python version is sufficient"""
    print_step(1, "Checking Python version...")

    version = sys.version_info
    if version.major < 3 or (version.major == 3 and version.minor < 8):
        print(f"❌ Python 3.8+ required, you have {version.major}.{version.minor}")
        return False

    print(f"✅ Python {version.major}.{version.minor}.{version.micro}")
    return True


def create_directories():
    """Create necessary directories"""
    print_step(2, "Creating directories...")

    directories = [
        "data/vector_db",
        "data/medquad",
        "data/arxiv",
        "data/arxiv_cache",
        "logs",
    ]

    for directory in directories:
        Path(directory).mkdir(parents=True, exist_ok=True)
        print(f"  ✅ Created {directory}/")

    return True


def create_env_file():
    """Create .env file from template"""
    print_step(3, "Setting up configuration file...")

    env_path = Path(".env")
    env_example_path = Path(".env.example")

    if not env_example_path.exists():
        print("  ⚠️  .env.example not found, skipping")
        return False

    if env_path.exists():
        print("  ℹ️  .env already exists, skipping")
        return True

    shutil.copy(env_example_path, env_path)
    print("  ✅ Created .env file (configure with your API keys)")
    print("  ⚠️  IMPORTANT: Add your API keys to .env before running")

    return True


def install_dependencies():
    """Install Python dependencies"""
    print_step(4, "Installing Python dependencies...")
    print("  This may take a few minutes...\n")

    try:
        # Upgrade pip
        subprocess.check_call(
            [sys.executable, "-m", "pip", "install", "--upgrade", "pip"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

        # Install requirements
        result = subprocess.run(
            [sys.executable, "-m", "pip", "install", "-r", "requirements.txt"],
            capture_output=True,
            text=True,
        )

        if result.returncode == 0:
            print("  ✅ Dependencies installed successfully")
            return True
        else:
            print("  ❌ Error installing dependencies:")
            print(result.stderr)
            return False

    except Exception as e:
        print(f"  ❌ Error: {str(e)}")
        return False


def download_spacy_models():
    """Download required spacy models"""
    print_step(5, "Downloading NLP models...")

    models = [
        ("en_core_web_sm", "English core model"),
        ("en_core_sci_md", "Scientific NER model (optional)"),
    ]

    for model_name, description in models:
        try:
            print(f"  Downloading {description}...", end=" ")
            result = subprocess.run(
                [sys.executable, "-m", "spacy", "download", model_name],
                capture_output=True,
                text=True,
            )
            if result.returncode == 0:
                print("✅")
            else:
                if "scientific" in description.lower():
                    print("⚠️  (optional)")
                else:
                    print("❌")
                    return False

        except Exception as e:
            print(f"⚠️  (skipped: {str(e)})")

    return True


def test_imports():
    """Test if all imports work"""
    print_step(6, "Testing imports...")

    critical_modules = [
        ("sentence_transformers", "Sentence Transformers"),
        ("faiss", "FAISS"),
        ("transformers", "Transformers"),
        ("streamlit", "Streamlit"),
        ("langdetect", "Language Detection"),
        ("spacy", "Spacy"),
    ]

    all_ok = True
    for module_name, display_name in critical_modules:
        try:
            __import__(module_name)
            print(f"  ✅ {display_name}")
        except ImportError:
            print(f"  ❌ {display_name} - not found")
            all_ok = False

    return all_ok


def display_next_steps():
    """Display next steps for user"""
    print_header("Setup Complete!")

    print("Next Steps:\n")
    print("1. Configure API Keys:")
    print("   Edit .env file and add your API keys:")
    print("   - GOOGLE_GEMINI_API_KEY (from Google AI Studio)")
    print("   - GOOGLE_VISION_API_KEY (for image processing)")
    print("")
    print("2. Prepare Datasets (Optional):")
    print("   - MedQuAD: Download from https://github.com/abachaa/MedQuAD")
    print("   - Place in data/medquad/")
    print("")
    print("3. Run the Chatbot:")
    print("   Option A - Web Interface (Recommended):")
    print("     streamlit run ui/streamlit_app.py")
    print("")
    print("   Option B - Command Line:")
    print("     python chatbot_main.py")
    print("")
    print("4. Start Chatting:")
    print("   • Ask medical questions")
    print("   • Query research papers")
    print("   • Use natural language in multiple languages")
    print("   • Upload images for analysis")
    print("")
    print("📖 For detailed docs, see README.md")
    print("")


def verify_setup():
    """Final setup verification"""
    print_step(7, "Verifying setup...")

    # Check critical files
    files_to_check = [
        "chatbot_main.py",
        "requirements.txt",
        ".env",
        "README.md",
        "modules/vector_db.py",
        "modules/multimodal.py",
        "modules/medical_qa.py",
        "modules/domain_expert.py",
        "modules/sentiment_analysis.py",
        "modules/language_support.py",
        "ui/streamlit_app.py",
    ]

    missing_files = []
    for file in files_to_check:
        if not Path(file).exists():
            missing_files.append(file)

    if missing_files:
        print(f"  ⚠️  Missing files: {', '.join(missing_files)}")
        return False

    print("  ✅ All critical files present")
    return True


def main():
    """Main setup function"""
    print_header("🤖 Unified Chatbot System - Setup")

    steps = [
        ("Python Version", check_python_version),
        ("Directories", create_directories),
        ("Configuration", create_env_file),
        ("Dependencies", install_dependencies),
        ("NLP Models", download_spacy_models),
        ("Import Tests", test_imports),
    ]

    failed_steps = []

    for step_name, step_func in steps:
        try:
            if not step_func():
                failed_steps.append(step_name)
        except Exception as e:
            print(f"  ❌ Error: {str(e)}")
            failed_steps.append(step_name)

    # Verify setup
    if not verify_setup():
        failed_steps.append("File Verification")

    print("\n" + "=" * 60)

    if failed_steps:
        print("\n⚠️  Setup completed with issues:")
        for step in failed_steps:
            print(f"  - {step}")
        print("\nPlease fix these issues before running the chatbot.")
    else:
        print("\n✅ Setup completed successfully!")

    # Display next steps
    display_next_steps()

    return 0 if not failed_steps else 1


if __name__ == "__main__":
    sys.exit(main())
