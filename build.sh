#!/bin/bash

# Define paths correctly without the broken $ variables
# // means search subdirectories recursively
export TEXINPUTS=".:./style-classes//:./tex//:"
export BIBINPUTS=".:./tex//:"
export BSTINPUTS=".:./tex//:"

# Run latexmk
latexmk -xelatex -output-directory=build -interaction=nonstopmode tex/thesis.tex
wslview ./build/thesis.pdf

