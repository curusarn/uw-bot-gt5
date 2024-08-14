#!/bin/bash

# Activate the virtual environment
source ./venv/Scripts/activate

# export UNNATURAL_ROOT=/c/Program\ Files\ \(x86\)/Steam/steamapps/common/Unnatural\ Worlds/
# echo $UNNATURAL_ROOT

# Run the Python script
python main.py

# tail -f -n 500 /c/Program\ Files\ \(x86\)/Steam/steamapps/common/Unnatural\ Worlds/bin/python3.12.log