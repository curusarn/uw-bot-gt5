#!/bin/bash

ps -e | grep uw-bot-gt5 | tr -s ' ' | cut -d' ' -f2 | xargs kill
#ps -e | grep yes | tr -s ' ' | cut -d' ' -f2 | xargs kill