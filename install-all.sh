#!/bin/bash
set -e

# Find all requirements.txt files
requirements=$(find . -name "requirements.txt")
# Execute pip once, with all requirements.txt files as arguments, in the form -r r1.txt -r r2.txt ...
# We could have just find -xargs pip install -r, but that would execute pip once for each file
# And we can't do pip install -r $(find ...) or pip install **/requirements.txt because we need the -r for each file
pip install -r $(echo $requirements | sed 's/ / -r /g')
