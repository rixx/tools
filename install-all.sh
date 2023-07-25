#!/bin/bash

set -e

# Get full base directory path
BASEDIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" >/dev/null 2>&1 && pwd )"
echo "BASEDIR: $BASEDIR"

# For each subdirectory, link all executables to ~/.local/bin

for dir in */; do
    for file in "$dir"*; do
        # If the file is executable and not a directory
        if [[ -x "$file" && ! -d "$file" ]]; then
            # Link the file to ~/.local/bin if it doesn't already exist
            if [[ ! -L "$HOME/.local/bin/$(basename "$file")" ]]; then
                # Link the file by full path to avoid issues with relative paths
                echo "Linking $BASEDIR/$file to ~/.local/bin/$(basename "$file")"
                ln -s "$BASEDIR/$file" "$HOME/.local/bin/$(basename "$file")"
            fi
        fi
    done
done
