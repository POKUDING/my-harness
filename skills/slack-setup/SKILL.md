---
name: slack-setup
description: Configure project-level API tokens saved to .harness/config.env (gitignored)
---

# Project Service Setup

Store API tokens for this project in .harness/config.env (gitignored, local only).

## Step 1: Check existing config

Read .harness/config.env if it exists. Show the user which keys are already saved (mask values). If the file does not exist, inform the user there is no config yet.

## Step 2: Ask which service to configure

Ask the user: "Which service would you like to configure? 1. Slack  2. Exit"

## Step 3: Slack token input

If Slack is selected, ask: "Enter your Slack Bot Token (xoxb-...) or User Token (xoxp-...):"

Validate the input starts with xoxb- or xoxp-. If not, ask again.

Save Bot Tokens as SLACK_BOT_TOKEN and User Tokens as SLACK_USER_TOKEN.

## Step 4: Save .harness/config.env

Use the Write tool to create or update .harness/config.env in the project root.

Format: one KEY=value per line. Add a comment at the top: "# DO NOT COMMIT - this file is gitignored".

If the file already exists, update only the relevant key and preserve other entries.

## Step 5: Check .gitignore

Verify .harness/ is in .gitignore. If not, add it.

## Step 6: Confirm

Show the saved key names (mask values). Tell the user they can now run /slack-list-plan.
