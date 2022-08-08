#!/bin/bash
python pollinator/main.py --db_name $DB_NAME |& utils/pipe_to_pollinator_logs_discord.sh