"""Explicit collection command; never called by HTTP routes."""

import argparse

from app.data.json_source import CachedJSONSource
from app.data.provider import DataProviderError
from app.data.statsbomb import StatsBombOpenDataProvider


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--competition", help="Namespaced competition ID from the catalog")
    parser.add_argument("--season", help="Namespaced season ID")
    parser.add_argument("--events", action="store_true", help="Download every available match's events in this season")
    parser.add_argument("--refresh", action="store_true")
    args = parser.parse_args()
    if bool(args.competition) != bool(args.season) or (args.events and not args.season):
        parser.error("Provide both --competition and --season; --events requires both")
    provider = StatsBombOpenDataProvider(CachedJSONSource(refresh=args.refresh))
    try:
        competitions = provider.get_competitions()
        for competition in competitions:
            for season in provider.get_seasons(competition.id):
                print(competition.id, season.id, competition.name, season.name)
        if not args.season:
            return
        season = next((s for s in provider.get_seasons(args.competition) if s.id == args.season), None)
        if season is None:
            parser.error("Season is not listed in this competition")
        matches = provider.get_matches(args.competition, season)
        print(f"Prepared {len(matches)} match records; this does not certify season completeness.")
        if matches:
            print("Match data SHA-256:", matches[0].provenance.sha256)
        if args.events:
            for match in matches:
                events = provider.get_match_events(match.id)
                print(match.id, len(events), "events; SHA-256:", events[0].provenance.sha256 if events else "empty")
        print("Downloads do not attest event completeness or verify roster counts. See docs/API.md.")
    except DataProviderError as exc:
        parser.exit(1, f"Data preparation failed: {exc}\n")


if __name__ == "__main__":
    main()
