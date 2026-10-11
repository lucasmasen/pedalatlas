# PedalAtlas

Explore further. Ride informed.

PedalAtlas is a map-based bicycle touring atlas for the Alaska-to-Vancouver corridor. Community notes, maps, weather, and official sources are kept as separate evidence so a claim is not published just because someone said it in chat.

The first research agent is the community-knowledge agent. It reads the existing WhatsApp exports and stores private claim drafts. It does not publish them.

## WhatsApp data already in the repo

Two German-format exports are already committed as zip files. They were not modified.

| Export | Zip | Uncompressed chat | Dated entries | Of which |
| --- | --- | --- | --- | --- |
| Cycling Alaska to the Darien Gap | 268 KB | 715 KB `.txt` plus 13 `.vcf` contact cards | 3,949 | 739 system, 203 media |
| Cycling South America | 469 KB | 1.2 MB `.txt` plus 28 `.vcf` contact cards | 6,687 | 1,134 system, 562 media |

Format: `DD.MM.YY, HH:MM - Sender: message`, UTF-8, with multiline messages. There was no existing parser.

The Alaska chat is the one that overlaps this atlas. Place names that show up there include Anchorage, Fairbanks, Tok, Whitehorse, Cassiar, Vancouver, and a few Cassiar and Highway 97 towns. Most of that chat, and nearly all of the South America chat, is south of Vancouver (Mexico, Central America, Colombia). Those messages stay in the export. They are not forced onto the Alaska–Vancouver map. Almost every sender label is a phone number.

Contact cards (`.vcf`) are ignored. They are address-book data.

## Privacy

Repository access is permission to build against the exports, not permission to publish them.

- Senders become `rider-` pseudonyms. Phone numbers and display names are not stored by the inspect script.
- Message text is not printed.
- Nothing from the chats is sent to an external API.
- Original zips stay as they are. No second copy is written.

## Community knowledge agent

`python -m scripts.run_community_agent` parses both exports and writes `data/private/community.sqlite`. That directory is gitignored. The script prints counts, not messages.

On the current exports it kept 1,044 claim drafts. All of them stay `private_draft`, and none are treated as verified facts. 306 are jokes, speculation, opinions, or questions. 42 are personal experiences. 13 are corrections. Support and contradiction links are marked as one community evidence family, so a repeated chat note is not an independent source.

17 drafts mention a place in the Alaska-to-Vancouver gazetteer (Anchorage, Fairbanks, Vancouver, the Cassiar, Williams Lake, Jasper). The other drafts stay unlocated rather than being pinned to a town that was not named. Most of the conversation is south of Vancouver.

## Run it

```bash
python3.12 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
pytest
python -m scripts.inspect_exports
python -m scripts.run_community_agent
```

## What is next

The mapping agent is next. Weather, official information, claim verification, Jev checks, and the map wiki come after that. WhatsApp claims stay private until there is explicit permission to publish.
