import React from "react";
import { mediaUrl } from "@/lib/api";
import "./FramedAvatar.css";

/**
 * Square avatar with an optional animated frame around it.  The frame is a
 * pure-CSS effect chosen by `effectKey`; colors come from the frame doc.
 *
 * Props:
 *   src           — raw avatar relative path (or "" / null)
 *   username      — fallback initials
 *   size          — pixel size of the avatar square (frame adds ~14% around it)
 *   frame         — { effect_key, color_primary, color_secondary } | null
 *   className     — extra wrapper classes
 *   onClick       — optional click handler
 *   "data-testid" — passthrough
 */
export default function FramedAvatar({
  src,
  username = "",
  size = 48,
  frame = null,
  className = "",
  onClick,
  ...rest
}) {
  const initials = (username || "?").slice(0, 1).toUpperCase();
  // Frame box is 16% larger than the avatar so the ring/effect sits AROUND it.
  const ringPad = Math.max(3, Math.round(size * 0.08));
  const boxSize = size + ringPad * 2;

  const cssVars = frame
    ? {
        "--frame-c1": frame.color_primary || "#f43f5e",
        "--frame-c2": frame.color_secondary || "#fb7185",
      }
    : {};

  const frameClass = frame ? `fa-frame fa-${frame.effect_key}` : "";

  return (
    <div
      className={`fa-wrap inline-block ${className}`}
      style={{ width: boxSize, height: boxSize, ...cssVars }}
      onClick={onClick}
      {...rest}
    >
      {frame && <span className={frameClass} aria-hidden="true" />}
      <div
        className="fa-avatar overflow-hidden bg-zinc-800 text-white flex items-center justify-center"
        style={{
          width: size,
          height: size,
          fontSize: size * 0.4,
          left: ringPad,
          top: ringPad,
        }}
      >
        {src ? (
          <img
            src={mediaUrl(src)}
            alt={username}
            className="w-full h-full object-cover"
            draggable={false}
          />
        ) : (
          <span className="font-semibold">{initials}</span>
        )}
      </div>
    </div>
  );
}
