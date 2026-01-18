#!/bin/bash
# Generate the gRPC python files in the current directory
# Bulletproof version - uses local paths only

set -e

echo "🔧 Generating gRPC Python classes from proto.chimera.proto..."

# Use current directory (where script is located)
cd "$(dirname "$0")"

# Verify proto file exists
if [ ! -f "proto.chimera.proto" ]; then
    echo "❌ ERROR: proto.chimera.proto not found in current directory"
    echo "   Current directory: $(pwd)"
    echo "   Files in directory:"
    ls -la *.proto 2>/dev/null || echo "   (no .proto files found)"
    exit 1
fi

# Create proto output directory
mkdir -p proto

# Generate Python code using local proto file
# Try python3 first, fallback to python
if command -v python3 &> /dev/null; then
    PYTHON_CMD=python3
elif command -v python &> /dev/null; then
    PYTHON_CMD=python
else
    echo "❌ ERROR: Python not found"
    exit 1
fi

$PYTHON_CMD -m grpc_tools.protoc \
    -I. \
    --python_out=proto \
    --grpc_python_out=proto \
    proto.chimera.proto

# Verify generation succeeded
if [ $? -eq 0 ] && [ -f "proto/chimera_pb2.py" ] && [ -f "proto/chimera_pb2_grpc.py" ]; then
    echo "✅ Successfully generated gRPC classes:"
    echo "   - proto/chimera_pb2.py"
    echo "   - proto/chimera_pb2_grpc.py"
else
    echo "❌ ERROR: Proto generation failed or files not created"
    exit 1
fi

# Ensure __init__.py exists
touch proto/__init__.py

echo "✅ Proto generation complete!"
