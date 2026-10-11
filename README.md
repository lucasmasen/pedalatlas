# PedalAtlas

Explore further. Ride informed.

PedalAtlas is a map-based bicycle touring atlas for the Alaska-to-Vancouver corridor. Community notes, maps, weather, and official sources are kept as separate evidence so a claim is not published just because someone said it in chat.

This push is the foundation: read the existing WhatsApp exports, and keep phone numbers and raw conversations out of anything public.

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

## Run the inspect script

```bash
python3.12 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
pytest
python -m scripts.inspect_exports
```

`inspect_exports` prints only counts: messages, system lines, media placeholders, and how many senders look like phone numbers.

## What is next

Claim extraction, the five research agents, Jev publication checks, and the map wiki are not in this commit. Private claims will default to draft and will not be published without permission. The public demo will use synthetic examples, not raw chat.
