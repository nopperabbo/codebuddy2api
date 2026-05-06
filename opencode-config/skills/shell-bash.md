# Skill: Shell / Bash
# Loaded on-demand when working with .sh, .bash, Makefile, shell scripts

## Script Header & Safety

```bash
#!/usr/bin/env bash
set -euo pipefail  # ALWAYS use this
# -e: exit on error
# -u: error on undefined variables
# -o pipefail: pipe fails if any command fails

IFS=$'\n\t'  # Safer word splitting (optional but recommended)
```

## Shellcheck — Lint Everything

```bash
# Install: apt install shellcheck / brew install shellcheck
shellcheck myscript.sh
# Inline directives for false positives:
# shellcheck disable=SC2086
echo $unquoted_var  # intentional
```

## Quoting Rules

```bash
# ALWAYS double-quote variables — prevents word splitting & globbing
echo "$filename"           # Correct
echo $filename             # WRONG — breaks on spaces

# Single quotes: literal strings, no expansion
echo 'No $expansion here'

# Arrays need special quoting
files=("file one.txt" "file two.txt")
for f in "${files[@]}"; do  # "${array[@]}" preserves elements
    echo "$f"
done
```

## Parameter Expansion

```bash
name="world"
echo "${name:-default}"     # Use default if unset
echo "${name:=default}"     # Assign default if unset
echo "${name:+alternate}"   # Use alternate if set
echo "${name:?error msg}"   # Error if unset

# String manipulation
path="/home/user/file.tar.gz"
echo "${path##*/}"          # file.tar.gz  (strip longest prefix)
echo "${path%.*}"           # /home/user/file.tar  (strip shortest suffix)
echo "${path%%.*}"          # /home/user/file  (strip longest suffix)
echo "${path/user/admin}"   # /home/admin/file.tar.gz  (substitute)
```

## Functions & Error Handling

```bash
log() {
    local level="$1"; shift
    printf '[%s] [%s] %s\n' "$(date -Iseconds)" "$level" "$*" >&2
}

die() { log ERROR "$@"; exit 1; }

# Trap for cleanup
cleanup() {
    rm -f "$tmpfile"
    log INFO "Cleaned up"
}
trap cleanup EXIT ERR

tmpfile=$(mktemp)
# tmpfile is auto-cleaned on exit or error
```

## Argument Parsing (getopts)

```bash
usage() { echo "Usage: $0 [-v] [-o output] [-n count] input" >&2; exit 1; }

verbose=false
output="/dev/stdout"
count=1

while getopts ":vo:n:" opt; do
    case "$opt" in
        v) verbose=true ;;
        o) output="$OPTARG" ;;
        n) count="$OPTARG" ;;
        :) die "Option -$OPTARG requires an argument" ;;
        *) usage ;;
    esac
done
shift $((OPTIND - 1))

[[ $# -lt 1 ]] && usage
input="$1"
```

## Process Substitution & Here Documents

```bash
# Process substitution — treat command output as a file
diff <(sort file1.txt) <(sort file2.txt)

# Here document
cat <<EOF
Hello, $USER
Today is $(date +%A)
EOF

# Here document (no expansion)
cat <<'EOF'
Literal $USER — no expansion
EOF

# Here string
grep "pattern" <<< "$variable"
```

## Common Patterns

```bash
# Safe temp directory
workdir=$(mktemp -d)
trap 'rm -rf "$workdir"' EXIT

# Check command exists
command -v docker &>/dev/null || die "docker not found"

# Read file line by line
while IFS= read -r line; do
    echo "Line: $line"
done < "$input_file"

# Parallel execution with wait
for url in "${urls[@]}"; do
    curl -sO "$url" &
done
wait
```

## Portable POSIX vs Bash-Specific

```bash
# POSIX (works in sh, dash, etc.)
[ -f "$file" ]              # File test
command -v git >/dev/null   # Check command exists

# Bash-specific (NOT portable)
[[ "$str" =~ ^[0-9]+$ ]]   # Regex match
declare -A map              # Associative arrays
```

## Makefile Patterns

```makefile
.PHONY: all build test clean lint

SHELL := /bin/bash
.SHELLFLAGS := -euo pipefail -c

# Variables
APP_NAME := myapp
VERSION  := $(shell git describe --tags --always)
LDFLAGS  := -ldflags "-X main.version=$(VERSION)"

all: lint test build

build:
	go build $(LDFLAGS) -o bin/$(APP_NAME) ./cmd/$(APP_NAME)

test:
	go test -race -cover ./...

lint:
	golangci-lint run

clean:
	rm -rf bin/ dist/

# Pattern rule
%.pb.go: %.proto
	protoc --go_out=. $<

# Help target
help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "  %-15s %s\n", $$1, $$2}'
```

## Anti-Patterns to Avoid

```bash
# NEVER parse ls output
ls *.txt | while read f; do ...   # WRONG
for f in *.txt; do ...            # Correct

# NEVER use eval with user input
eval "$user_input"                # DANGEROUS

# NEVER use unquoted variables
rm -rf $dir/$file                 # Could delete / if vars are empty
rm -rf "${dir:?}/${file:?}"       # Safe — errors if empty

# Don't use cat unnecessarily
cat file | grep pattern           # Useless use of cat
grep pattern file                 # Correct
```

## Best Practices

- Run `shellcheck` on every script — treat warnings as errors in CI.
- Quote every variable: `"$var"`, `"${array[@]}"`.
- Use `local` for function variables to avoid polluting global scope.
- Prefer `[[ ]]` over `[ ]` in bash scripts (safer, more features).
- Use `readonly` for constants: `readonly CONFIG_DIR="/etc/myapp"`.
- Write `--` before filenames in commands: `rm -- "$file"` (handles `-` prefixed names).
- Log to stderr (`>&2`), output data to stdout — enables piping.
