#!/bin/bash
cd /home/kavia/workspace/code-generation/event-booking-and-management-app-13870-14379/BookingService
source venv/bin/activate
flake8 .
LINT_EXIT_CODE=$?
if [ $LINT_EXIT_CODE -ne 0 ]; then
  exit 1
fi

