# Optional Discord notifications

LAN/Tailscale signing works without Discord. Skip it in the wizard for a smaller
setup; failures then appear in the worker log and CLI retries remain available.

1. Create an application and dedicated bot at https://discord.com/developers/applications.
2. Invite it to your server using the OAuth2 URL Generator with the `bot` scope.
   Give it **View Channel**, **Send Messages**, **Read Message History**, and
   **Add Reactions** in your chosen channel. No administrator permission or
   privileged Gateway intents are required: this worker polls Discord's REST API.
3. Enable **Developer Mode** in Discord's Advanced settings. Copy the channel ID
   and your own user ID using their context menus.
4. Choose Discord in the wizard and enter those IDs. Paste the bot token into the
   hidden prompt. It goes into `discord-credentials.json` in your owner-only runtime,
   never into source, command-line arguments, or the LaunchAgent.

Automatic failure: `Failed during <stage>. Installed profiles expire <timestamp>.
React to this message to retry.` Manual/reaction retry failure: `Apollo retry failed
during <stage>. React to this message to retry.`

Any emoji reaction **from the configured user** on the newest failure message
requests a retry. Acknowledgement is sent when it starts. Bot/other-user reactions
are ignored. Reactions bypass the hourly limit; the daily limit and process lock
remain. Polling usually detects a reaction within ten seconds when the worker is
available, but it cannot interrupt an installation already in progress. React to
the new failure message after another failure. Success adds ✅ to its most recent
message. Persistent queues retry notifications during outages.

Rotate a leaked token in Discord's developer portal, then replace only the `token`
value in the private credential file (mode 0600). Never send tokens in bug reports.
To disable Discord, stop the job, set `"discord": null` in its private `config.json`,
and restart. Existing notification history can remain in private state.
