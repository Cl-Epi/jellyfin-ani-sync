#!/usr/bin/env python3
"""Apply the Shoko single-season AniDB fix to upstream jellyfin-ani-sync source.

Usage: python3 apply_fix.py <path to upstream checkout>

Shokofin can expose every AniDB entry (e.g. season 3 of a show) as its own
Jellyfin series containing a single "Season 1", with the correct AniDB ID on
the series. Upstream then looks that ID up in the anime-lists XML using the
Jellyfin season number (always 1) and ends up returning the FIRST AniDB entry
of the TVDB show, i.e. season 1. This fix makes the plugin trust the series
AniDB ID directly in that situation.
"""
import pathlib
import sys

MARKER = "ShokoSingleSeasonAniDbFix"
TARGET = "jellyfin-ani-sync/Helpers/AnimeListHelpers.cs"
SIGNATURE = "public static async Task<(int? aniDbId, int? episodeOffset)> GetAniDbId("

HELPER = '''
        // [fork fix] Shoko single-season AniDB fix. See fork-fix/apply_fix.py.
        internal static int? ShokoSingleSeasonAniDbFix(ILogger logger, Video video) {
            if (video is not Episode forkEp || forkEp.Series == null || forkEp.Season == null) return null;
            if (forkEp.Season.IndexNumber != 1) return null;
            if (forkEp.Series.Children.OfType<Season>().Count(s => s.IndexNumber is > 0) != 1) return null;
            if (forkEp.Season.ProviderIds != null &&
                forkEp.Season.ProviderIds.Keys.Any(k => string.Equals(k, "Anidb", StringComparison.OrdinalIgnoreCase))) return null;
            if (forkEp.Series.ProviderIds == null) return null;
            foreach (var forkKv in forkEp.Series.ProviderIds) {
                if (string.Equals(forkKv.Key, "Anidb", StringComparison.OrdinalIgnoreCase) && int.TryParse(forkKv.Value, out var forkId)) {
                    logger.LogInformation($"(Anidb) [fork fix] Series {forkEp.Series.Name} has a single season and its own AniDB ID ({forkId}); using it directly with no episode offset");
                    return forkId;
                }
            }
            return null;
        }

'''

CALL = '''
            { var forkFixId = ShokoSingleSeasonAniDbFix(logger, video); if (forkFixId != null) return (forkFixId, null); }'''


def main() -> int:
    path = pathlib.Path(sys.argv[1]) / TARGET
    src = path.read_text(encoding="utf-8")

    if MARKER in src:
        print("Fix already present; nothing to do.")
        return 0

    if src.count(SIGNATURE) != 1:
        print(f"ERROR: expected exactly one GetAniDbId signature in {TARGET}, found {src.count(SIGNATURE)}.")
        return 1

    sig_start = src.index(SIGNATURE)
    line_start = src.rindex("\n", 0, sig_start) + 1
    brace = src.index("{", sig_start + len(SIGNATURE))
    # The opening brace must end the signature line.
    if src[sig_start:brace].count("\n") != 0:
        print("ERROR: unexpected GetAniDbId signature layout.")
        return 1

    src = src[:brace + 1] + CALL + src[brace + 1:]
    src = src[:line_start] + HELPER.lstrip("\n") + src[line_start:]

    path.write_text(src, encoding="utf-8")
    print("Fix applied.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
