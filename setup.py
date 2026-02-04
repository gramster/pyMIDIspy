"""
Setup file for pyMIDIspy Python package.

This custom setup.py handles building the SnoizeMIDISpy framework from source
and bundling it into the wheel.
"""

import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path

from setuptools import setup, find_packages
from setuptools.command.build_py import build_py
from setuptools.command.develop import develop
from setuptools.command.egg_info import egg_info

try:
    from wheel.bdist_wheel import bdist_wheel
    HAS_WHEEL = True
except ImportError:
    HAS_WHEEL = False


# Paths
ROOT_DIR = Path(__file__).parent.absolute()
SNOIZE_DIR = ROOT_DIR / "src" / "SnoizeMIDISpy"
PACKAGE_DIR = ROOT_DIR / "pyMIDIspy"
LIB_DIR = PACKAGE_DIR / "lib"

# Xcode build configuration
XCODE_CONFIG = os.environ.get("XCODE_CONFIG", "Release")


def check_macos():
    """Ensure we're running on macOS."""
    if platform.system() != "Darwin":
        print("Warning: pyMIDIspy only works on macOS. Building without native libraries.")
        return False
    return True


def build_snoize_midi_spy():
    """Build the SnoizeMIDISpy framework and driver plugin from source."""
    if not check_macos():
        return False
    
    project = SNOIZE_DIR / "SnoizeMIDISpy.xcodeproj"
    if not project.exists():
        print(f"Error: SnoizeMIDISpy project not found at {project}")
        return False
    
    # Create the lib directory
    LIB_DIR.mkdir(parents=True, exist_ok=True)
    
    # Build deriveddata path
    derived_data = ROOT_DIR / "_build" / "DerivedData"
    derived_data.mkdir(parents=True, exist_ok=True)
    
    print(f"Building SnoizeMIDISpy framework ({XCODE_CONFIG})...")
    
    # Build the SnoizeMIDISpy scheme using the project directly
    cmd = [
        "xcodebuild",
        "-project", str(project),
        "-scheme", "SnoizeMIDISpy.framework",
        "-configuration", XCODE_CONFIG,
        "-derivedDataPath", str(derived_data),
        "ONLY_ACTIVE_ARCH=NO",
        "BUILD_LIBRARY_FOR_DISTRIBUTION=YES",
        # Build for both architectures for universal binary
        "ARCHS=x86_64 arm64",
        "build",
    ]
    
    try:
        subprocess.run(cmd, check=True, cwd=str(SNOIZE_DIR))
    except subprocess.CalledProcessError as e:
        print(f"Error building SnoizeMIDISpy: {e}")
        return False
    
    # Find and copy the built framework
    build_products = derived_data / "Build" / "Products" / XCODE_CONFIG
    framework_src = build_products / "SnoizeMIDISpy.framework"
    
    if not framework_src.exists():
        print(f"Error: Built framework not found at {framework_src}")
        return False
    
    # Copy framework to lib directory
    framework_dst = LIB_DIR / "SnoizeMIDISpy.framework"
    if framework_dst.exists():
        shutil.rmtree(framework_dst)
    
    print(f"Copying framework to {framework_dst}...")
    shutil.copytree(framework_src, framework_dst, symlinks=True)
    
    # The MIDI Monitor.plugin (spy driver) is embedded in the framework's Resources
    # Verify it exists
    driver_plugin = framework_dst / "Resources" / "MIDI Monitor.plugin"
    if driver_plugin.exists():
        print(f"Driver plugin found at {driver_plugin}")
    else:
        print("Warning: Driver plugin not found in framework bundle")
    
    print("SnoizeMIDISpy framework built successfully!")
    return True


def ensure_framework_built():
    """Ensure the framework is built before packaging."""
    framework_path = LIB_DIR / "SnoizeMIDISpy.framework"
    
    # Check if framework already exists
    if framework_path.exists() and (framework_path / "SnoizeMIDISpy").exists():
        print("Using existing SnoizeMIDISpy framework")
        return True
    
    # Try to build from source
    return build_snoize_midi_spy()


class BuildPyCommand(build_py):
    """Custom build command that builds the native framework first."""
    
    def run(self):
        if check_macos():
            ensure_framework_built()
        super().run()


class DevelopCommand(develop):
    """Custom develop command that builds the native framework first."""
    
    def run(self):
        if check_macos():
            ensure_framework_built()
        super().run()


class EggInfoCommand(egg_info):
    """Custom egg_info command that builds the native framework first."""
    
    def run(self):
        if check_macos():
            ensure_framework_built()
        super().run()


# Custom bdist_wheel to tag as platform-specific (macOS only)
if HAS_WHEEL:
    class BdistWheelCommand(bdist_wheel):
        """Custom bdist_wheel that marks the wheel as macOS-only."""
        
        def finalize_options(self):
            super().finalize_options()
            # Mark as not pure Python (contains native code)
            self.root_is_pure = False
        
        def get_tag(self):
            # Get the default tags
            python, abi, plat = super().get_tag()
            # Force macOS platform tag for universal2 (arm64 + x86_64)
            if platform.system() == "Darwin":
                # Use macosx_10_9_universal2 for compatibility
                plat = "macosx_10_13_universal2"
            return python, abi, plat


# Read long description
with open("README.md", "r", encoding="utf-8") as fh:
    long_description = fh.read()


setup(
    name="pyMIDIspy",
    version="1.0.0",
    author="gramster",
    description="Python wrapper for SnoizeMIDISpy - capture outgoing MIDI on macOS",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/gramster/pyMIDIspy",
    packages=find_packages(include=["pyMIDIspy*"]),
    package_data={
        "pyMIDIspy": [
            "lib/SnoizeMIDISpy.framework/**/*",
            "lib/MIDI Monitor.plugin/**/*",
        ],
    },
    include_package_data=True,
    classifiers=[
        "Development Status :: 4 - Beta",
        "Intended Audience :: Developers",
        "License :: OSI Approved :: BSD License",
        "Operating System :: MacOS :: MacOS X",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
        "Programming Language :: Python :: 3.13",
        "Topic :: Multimedia :: Sound/Audio :: MIDI",
    ],
    python_requires=">=3.8",
    install_requires=[
        "pyobjc-core",
        "pyobjc-framework-Cocoa",
    ],
    extras_require={
        "dev": ["pytest", "mypy", "build", "twine"],
    },
    cmdclass={
        "build_py": BuildPyCommand,
        "develop": DevelopCommand,
        "egg_info": EggInfoCommand,
        **({"bdist_wheel": BdistWheelCommand} if HAS_WHEEL else {}),
    },
)
