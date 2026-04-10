#!/bin/bash

# --- Color Constants ---
GREEN='\033[0;32m'
CYAN='\033[0;36m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
PURPLE='\033[0;35m'
NC='\033[0m' # No Color
BOLD='\033[1m'

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" &> /dev/null && pwd)"
LOGS_DIR="$SCRIPT_DIR/logs"
TRACKER_FILE="$LOGS_DIR/cost_tracker.jsonl"

echo -e "\n${BOLD}${CYAN}========================================${NC}"
echo -e "${BOLD}${CYAN}          DAEMON.MD | SYSTEM STATUS     ${NC}"
echo -e "${BOLD}${CYAN}========================================${NC}\n"

# --- Service Health ---
echo -e "${BOLD}${CYAN}► Background Services:${NC}"

DAEMON_STATUS=$(launchctl list | grep "com.user.daemon.md")
if [ -n "$DAEMON_STATUS" ]; then
    echo -e "  [${GREEN}✓${NC}] Ingestion Engine (daemon.py) is ${GREEN}RUNNING${NC}"
else
    echo -e "  [${RED}✗${NC}] Ingestion Engine is ${RED}STOPPED${NC} or NOT LOADED"
fi

LINTER_STATUS=$(launchctl list | grep "com.user.daemon.linter")
if [ -n "$LINTER_STATUS" ]; then
    echo -e "  [${GREEN}✓${NC}] Synthesis Linter (lint_wiki.py) is ${GREEN}SCHEDULED${NC}"
else
    echo -e "  [${RED}✗${NC}] Synthesis Linter is ${RED}STOPPED${NC} or NOT LOADED"
fi
echo ""

# --- Token & Cost Metrics ---
echo -e "${BOLD}${CYAN}► API Token Usage:${NC}"
if [ -f "$TRACKER_FILE" ]; then
    # Use a single awk process to parse the entire JSONL file instantly, avoiding subshell hangs
    awk -F'"' '
        /"prompt_tokens":/ {
            for (i=1; i<=NF; i++) {
                if ($i == "prompt_tokens") {
                    gsub(/[^0-9]/, "", $(i+1))
                    p += $(i+1)
                }
                if ($i == "candidates_tokens") {
                    gsub(/[^0-9]/, "", $(i+1))
                    c += $(i+1)
                }
            }
            count++
        }
        END {
            printf "  Total Ingestions/Lints: \033[1;33m%d\033[0m\n", count
            printf "  Total Prompt Tokens:    \033[1;33m%d\033[0m\n", p
            printf "  Total Output Tokens:    \033[1;33m%d\033[0m\n", c
        }
    ' "$TRACKER_FILE"
else
    echo -e "  ${YELLOW}No token usage recorded yet.${NC}"
fi
echo ""

# --- Recent Activity (Daemon) ---
echo -e "${BOLD}${CYAN}► Recent Ingestion Activity:${NC}"
if [ -f "$LOGS_DIR/daemon.log" ]; then
    # Print the last 3 lines, formatted cleanly
    tail -n 3 "$LOGS_DIR/daemon.log" | while read -r line; do
        echo -e "  ${NC}$line${NC}"
    done
else
    echo -e "  ${YELLOW}No daemon logs found.${NC}"
fi
echo ""

# --- Recent Activity (Linter) ---
echo -e "${BOLD}${CYAN}► Last Synthesis Linter Run:${NC}"
if [ -f "$LOGS_DIR/linter.log" ]; then
    # Grab the last "Successfully generated" or "Error" line
    LAST_LINT=$(grep -E "Successfully generated|Error" "$LOGS_DIR/linter.log" | tail -n 1)
    if [ -n "$LAST_LINT" ]; then
        echo -e "  ${NC}$LAST_LINT${NC}"
    else
        echo -e "  ${YELLOW}Linter has not completed a run yet.${NC}"
    fi
else
    echo -e "  ${YELLOW}No linter logs found.${NC}"
fi
echo ""

echo -e "${BOLD}${CYAN}========================================${NC}\n"
