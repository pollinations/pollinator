#!/bin/bash

# pipe_stdin_to_discord_webhook.sh
# This script triggers discord webhook with input from stdin line-by-line

set -eu

# generate short random id using openssl
ID=$(openssl rand -hex 2)


# discord webhook url, pay attention to add ?wait=true at the end
WEBHOOK_URL='https://discord.com/api/webhooks/1002128254871810129/oWSxYluan9mlrK4LrduiKxvi8kyiKWAuRPGZWDvbpnboT6Pa-KPjs6RVMtwLGYTbyhSs'
# grep filter per line, lines not matching won't be sent
FILTER=''
# delay in seconds between each message to avoid getting rate limit banned
SPAM_DELAY=0.1
# message length limit beyond which message trims and ellipsis(...) is added
MAX_LENGTH=1000

function send_to_discord {
    local message=$ID - ${1//\"/\\\"}
    echo "$message" | awk -v len=${MAX_LENGTH} '{ if (length($0) > len) print substr($0, 1, len-3) "..."; else print; }'
    local content="{\"content\": \"${message}\"}"


    # the sed contraption from depths of abyss at the end extracts message id from
    # json response fragile af but can't be bothered to take jq dependency, and
    # its just an indicator

    curl -s \
        -H "Content-Type: application/json" \
        -X POST \
        -d "${content}" \
        "${WEBHOOK_URL}" | sed -n -e 's/.* \"id\": \"\([[:alnum:]]\+\)\", \"pinned\".*/\1\n/p'
}

FIRST_LINE=true

while IFS='$\n' read -r line; do
    if [ "$FILTER" = "" ] || (echo "${line}" | grep -q "${FILTER}"); then
        if [ "$FIRST_LINE" == 'true' ] ; then
            FIRST_LINE=false
        else
            sleep "$SPAM_DELAY"
        fi

        send_to_discord "$line"
    fi
done
