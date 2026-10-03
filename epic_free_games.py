"""Posts this week's free Epic Games Store games to a Discord webhook."""
import os
import sys
from datetime import datetime
import requests

API = "https://store-site-backend-static.ak.epicgames.com/freeGamesPromotions"
WEBHOOK = os.environ.get("DISCORD_WEBHOOK_URL")
DRY_RUN = os.environ.get("DRY_RUN", "").lower() in ("1", "true", "yes")

# Optional: paste a Discord role ID between the quotes to ping that role.
# Leave it as "" for no ping.
ROLE_ID = "1555989818314326056"

GREEN = 0x2ECC71
BLUE = 0x3498DB


def is_free(offer):
    # Epic reports a 100% discount as discountPercentage == 0
    return offer["discountSetting"]["discountPercentage"] == 0


def get_games():
    r = requests.get(API, params={"locale": "en-US", "country": "PH"}, timeout=15)
    r.raise_for_status()
    elements = r.json()["data"]["Catalog"]["searchStore"]["elements"]

    current, upcoming = [], []
    for g in elements:
        promos = g.get("promotions") or {}

        if promos.get("promotionalOffers"):
            for block in promos["promotionalOffers"]:
                for o in block["promotionalOffers"]:
                    if is_free(o):
                        current.append((g, o["endDate"]))
                        break

        if promos.get("upcomingPromotionalOffers"):
            for block in promos["upcomingPromotionalOffers"]:
                for o in block["promotionalOffers"]:
                    if is_free(o):
                        upcoming.append((g, o["startDate"]))
                        break
    return current, upcoming


def get_slug(game):
    mappings = game.get("offerMappings") or []
    if mappings and mappings[0].get("pageSlug"):
        return mappings[0]["pageSlug"]
    attrs = (game.get("catalogNs") or {}).get("mappings") or []
    if attrs and attrs[0].get("pageSlug"):
        return attrs[0]["pageSlug"]
    return game.get("productSlug") or game.get("urlSlug")


def to_unix(iso):
    # Epic format: 2026-10-08T15:00:00.000Z
    return int(datetime.fromisoformat(iso.replace("Z", "+00:00")).timestamp())


def make_embed(game, date_str, label, color):
    slug = get_slug(game)
    image = next(
        (i["url"] for i in game.get("keyImages", [])
         if i["type"] in ("OfferImageWide", "Thumbnail")),
        None,
    )
    ts = to_unix(date_str)
    embed = {
        "title": game["title"],
        "description": f"{label} <t:{ts}:F> (<t:{ts}:R>)",
        "color": color,
    }
    if slug:
        embed["url"] = f"https://store.epicgames.com/en-US/p/{slug}"
    if image:
        embed["image"] = {"url": image}
    return embed


def send(payload):
    if DRY_RUN or not WEBHOOK:
        print("DRY RUN, would post:", payload["content"])
        for e in payload["embeds"]:
            print("-", e["title"], "|", e["description"])
        return
    requests.post(WEBHOOK, json=payload, timeout=15).raise_for_status()
    print("Posted:", payload["content"])


def main():
    current, upcoming = get_games()

    # Keep upcoming separate from current, no duplicates
    seen = {g["title"] for g, _ in current}
    upcoming = [(g, d) for g, d in upcoming if g["title"] not in seen]

    if not current and not upcoming:
        print("No free games found, nothing to post.")
        return

    if current:
        ping = f"<@&{ROLE_ID}> " if ROLE_ID else ""
        payload = {
            "content": f"{ping}**Free now on the Epic Games Store**",
            "embeds": [make_embed(g, d, "Free until", GREEN) for g, d in current][:10],
        }
        if ROLE_ID:
            payload["allowed_mentions"] = {"roles": [ROLE_ID]}
        send(payload)

    if upcoming:
        send({
            "content": "**Coming next week**",
            "embeds": [make_embed(g, d, "Free starting", BLUE) for g, d in upcoming][:10],
        })


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)  # non-zero exit makes the workflow fail so GitHub emails you
