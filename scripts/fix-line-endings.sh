#!/usr/bin/env bash
# Fix Windows line endings (CRLF) to Unix line endings (LF)
# Run this if you get: /usr/bin/env: 'bash\r': No such file or directory

cd "$(dirname "$0")/.."

echo "🔧 Fixing line endings for shell scripts..."

# Fix all shell scripts
find . -name "*.sh" -type f -exec sed -i 's/\r$//' {} \;

echo "✅ Line endings fixed!"
echo ""
echo "📝 To prevent this in the future, configure git:"
echo "   git config core.autocrlf input"
echo ""
