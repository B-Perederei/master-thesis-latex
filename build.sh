export TEXINPUTS=".:./style-classes//:$TEXINPUTS"
latexmk -xelatex -outdir=build src/bachelor-thesis.tex