#!/bin/bash
# Test script to verify RevertIT commands are available

echo "Testing RevertIT command availability..."
echo "======================================="

# Check if revertit command exists
if command -v revertit &> /dev/null; then
    echo "✓ revertit command found at: $(which revertit)"
else
    echo "✗ revertit command not found"
fi

# Check if revertit-daemon command exists
if command -v revertit-daemon &> /dev/null; then
    echo "✓ revertit-daemon command found at: $(which revertit-daemon)"
else
    echo "✗ revertit-daemon command not found"
fi

# Check Python entry points
echo ""
echo "Python entry points:"
pip3 show revertit 2>/dev/null | grep -A5 "Entry-points" || echo "Package not installed"

echo ""
echo "Done!"
