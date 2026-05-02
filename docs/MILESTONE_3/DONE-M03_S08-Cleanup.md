# Clean Up

Some cleanup tasks I want to take care of before calling 03 done:

- [x] Document the ingestion process including how to use the api_set ps1 scripts
  - Base this on the documentation in M03_S05 because it worked
  - Done — `docs/INGESTION.md` covers prerequisites, script inventory, adding-a-new-set workflow, the alias-table workflow, daily price refresh, backfill, and troubleshooting.
- [x] Get the box and whisker's plot to order from rarest to most common
  - Right now it's common to ultra rare
  - It's at least consistent which I like
  - I can't/shouldn't order by price because sometimes rarity doesn't control price popularity does
  - Done via canonical_rarities (migration 009) + `display_order` ascending sort. Cards now store snake_case canonical rarity (FK-enforced); the API returns both `rarity` and `rarity_label`; the chart sorts rarest-on-the-left using the reference list.
