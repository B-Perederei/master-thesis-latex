#!/bin/bash

export TEXINPUTS=".:./style-classes//:./tex//:"
export BIBINPUTS=".:./tex//:"
export BSTINPUTS=".:./tex//:"

latexmk -xelatex -output-directory=build -interaction=nonstopmode tex/thesis.tex
wslview ./build/thesis.pdf

