#!/bin/bash

while true; do
    # Activate the virtual environment
    source ./venv/Scripts/activate

    # export UNNATURAL_ROOT=/c/Program\ Files\ \(x86\)/Steam/steamapps/common/Unnatural\ Worlds/
    # echo $UNNATURAL_ROOT

    # Run the Python script

    # export UNNATURAL_CONNECT_ADDR=1
    python main.py

    # tail -f -n 500 /c/Program\ Files\ \(x86\)/Steam/steamapps/common/Unnatural\ Worlds/bin/python3.12.log

    read -p "Press any key to continue... " -n1 -s
done