#!/bin/bash
# Build script for pyMIDIspy
# This script builds the SnoizeMIDISpy framework and creates a wheel

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "========================================"
echo "pyMIDIspy Build Script"
echo "========================================"

# Check for Xcode
if ! command -v xcodebuild &> /dev/null; then
    echo "Error: xcodebuild not found. Please install Xcode."
    exit 1
fi

# Initialize submodules if needed
if [ ! -f "vendor/MIDIApps/MIDIApps.xcworkspace/contents.xcworkspacedata" ]; then
    echo "Initializing git submodules..."
    git submodule update --init --recursive
fi

# Build configuration (Release by default)
CONFIG="${XCODE_CONFIG:-Release}"
echo "Build configuration: $CONFIG"

# Clean previous build
echo "Cleaning previous build..."
rm -rf _build/
rm -rf dist/
rm -rf pyMIDIspy/lib/SnoizeMIDISpy.framework
rm -rf *.egg-info

# Build the framework using setup.py
echo "Building framework and wheel..."
python -m pip install --upgrade pip build wheel
python -m build

echo ""
echo "========================================"
echo "Build complete!"
echo "========================================"
echo ""
echo "Wheel files are in dist/"
ls -la dist/*.whl 2>/dev/null || echo "No wheel files found"
echo ""
echo "To install locally: pip install dist/pyMIDIspy-*.whl"
echo "To upload to PyPI:  twine upload dist/*"
