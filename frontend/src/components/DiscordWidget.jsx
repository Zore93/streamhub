import React, { useState } from "react";
import { ExternalLink } from "lucide-react";

/**
 * Embeds the official Discord server widget iframe when an admin has both
 * (a) configured `discord_guild_id` in Admin → Settings AND
 * (b) enabled the server widget in Discord → Server Settings → Widget.
 *
 * Falls back to a simple "Join our Discord" card linking to the invite URL
 * if no guild ID is provided or the iframe fails to load (network/widget
 * disabled).
 */
export default function DiscordWidget({ guildId, inviteUrl }) {
  const [embedFailed, setEmbedFailed] = useState(false);
  if (!inviteUrl && !guildId) return null;

  const canEmbed = !!guildId && !embedFailed;
  const widgetSrc = canEmbed
    ? `https://discord.com/widget?id=${encodeURIComponent(guildId)}&theme=dark`
    : null;

  return (
    <div className="mt-4" data-testid="discord-widget">
      <div className="flex items-center justify-between mb-2">
        <div className="text-xs font-bold uppercase tracking-[0.2em] text-zinc-600 inline-flex items-center gap-2">
          <DiscordIcon className="text-[#5865F2]" />
          <span>Discord</span>
        </div>
        {inviteUrl && (
          <a
            href={inviteUrl}
            target="_blank"
            rel="noopener noreferrer"
            className="text-[10px] text-zinc-500 hover:text-zinc-200 inline-flex items-center gap-0.5"
            data-testid="discord-open"
          >
            Open <ExternalLink size={10} />
          </a>
        )}
      </div>

      {canEmbed ? (
        <iframe
          src={widgetSrc}
          title="Discord server widget"
          width="100%"
          height="380"
          frameBorder="0"
          sandbox="allow-popups allow-popups-to-escape-sandbox allow-same-origin allow-scripts"
          className="rounded-lg border border-zinc-800 bg-[#2f3136]"
          onError={() => setEmbedFailed(true)}
          data-testid="discord-iframe"
        />
      ) : (
        <DiscordJoinCard inviteUrl={inviteUrl} />
      )}
    </div>
  );
}

function DiscordJoinCard({ inviteUrl }) {
  if (!inviteUrl) return null;
  return (
    <a
      href={inviteUrl}
      target="_blank"
      rel="noopener noreferrer"
      className="block rounded-lg border border-[#5865F2]/40 bg-gradient-to-br from-[#5865F2]/15 via-zinc-900 to-[#5865F2]/10 p-4 hover:border-[#5865F2] hover:from-[#5865F2]/25 transition-colors group"
      data-testid="discord-join-card"
    >
      <div className="flex items-center gap-3">
        <div className="w-10 h-10 rounded-md bg-[#5865F2] flex items-center justify-center flex-shrink-0">
          <DiscordIcon className="text-white" size={22} />
        </div>
        <div className="flex-1 min-w-0">
          <div className="text-sm font-semibold text-zinc-100 flex items-center gap-1.5">
            #general
            <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse" />
          </div>
          <div className="text-xs text-zinc-400">Join our community on Discord</div>
        </div>
        <ExternalLink size={14} className="text-zinc-500 group-hover:text-zinc-200" />
      </div>
    </a>
  );
}

function DiscordIcon({ size = 16, className = "" }) {
  return (
    <svg
      xmlns="http://www.w3.org/2000/svg"
      width={size}
      height={size}
      viewBox="0 -28.5 256 256"
      preserveAspectRatio="xMidYMid"
      className={className}
      fill="currentColor"
      aria-hidden="true"
    >
      <path d="M216.856 16.597A208.502 208.502 0 0 0 164.042 0c-2.275 4.113-4.933 9.645-6.766 14.046-19.692-2.961-39.203-2.961-58.533 0-1.832-4.4-4.55-9.933-6.846-14.046a207.809 207.809 0 0 0-52.855 16.638C5.618 67.147-3.443 116.4 1.087 164.956c22.169 16.555 43.653 26.612 64.775 33.193A161.094 161.094 0 0 0 79.735 175.3a136.413 136.413 0 0 1-21.846-10.632 108.636 108.636 0 0 0 5.356-4.237c42.122 19.702 87.89 19.702 129.51 0a131.66 131.66 0 0 0 5.355 4.237 136.07 136.07 0 0 1-21.886 10.653c4.006 8.02 8.638 15.67 13.873 22.848 21.142-6.58 42.646-16.637 64.815-33.213 5.316-56.288-9.08-105.09-38.056-148.36ZM85.474 135.095c-12.645 0-23.015-11.805-23.015-26.18s10.149-26.2 23.015-26.2c12.867 0 23.236 11.804 23.015 26.2.02 14.375-10.148 26.18-23.015 26.18Zm85.051 0c-12.645 0-23.014-11.805-23.014-26.18s10.148-26.2 23.014-26.2c12.867 0 23.236 11.804 23.015 26.2 0 14.375-10.148 26.18-23.015 26.18Z" />
    </svg>
  );
}
