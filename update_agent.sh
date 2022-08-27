#!/bin/bash
curl -o update_agent.py https://raw.githubusercontent.com/pollinations/pollinator/update-agent/update_agent.py
pip3 install python-dotenv
python3 update_agent.py > /tmp/update_agent.log 2>&1