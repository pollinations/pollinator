#!/bin/bash
python pollinator/main.py --db_name pollen |& utils/pipe_to_pollinator_logs_discord.sh