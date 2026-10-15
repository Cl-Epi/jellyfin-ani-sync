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

MARKER = "ForkSingleSeasonSeriesAniDb"
TARGET = "jellyfin-ani-sync/Helpers/AnimeListHelpers.cs"
TARGET_STATUS = "jellyfin-ani-sync/UpdateProviderStatus.cs"
ANILIST_CHECK = 'episode.Series.ProviderIds.ContainsKey("AniList") &&'
ANILIST_GUARD = 'episode.Series.ProviderIds.ContainsKey("AniList") && jellyfin_ani_sync.Helpers.AnimeListHelpers.ForkSingleSeasonSeriesAniDb(_logger, episode) == null &&'
SIGNATURE = "public static async Task<(int? aniDbId, int? episodeOffset)> GetAniDbId("

HELPER = '''
        // [fork fix] Shoko single-season AniDB fix. See fork-fix/apply_fix.py.
        private static int? ForkGetAniDb(Dictionary<string, string> ids) {
            if (ids == null) return null;
            foreach (var forkKv in ids) {
                if (string.Equals(forkKv.Key, "Anidb", StringComparison.OrdinalIgnoreCase) && int.TryParse(forkKv.Value, out var forkId)) return forkId;
            }
            return null;
        }

        internal static int? ForkSingleSeasonSeriesAniDb(ILogger logger, Video video) {
            if (video is not Episode forkEp || forkEp.Series == null || forkEp.Season == null) return null;
            int? seasonId = ForkGetAniDb(forkEp.Season.ProviderIds);
            int? seriesId = ForkGetAniDb(forkEp.Series.ProviderIds);
            int seasonCount = forkEp.Series.Children.OfType<Season>().Count(s => s.IndexNumber is > 0);
            int? result = forkEp.Season.IndexNumber == 1 && seasonCount <= 1 ? (seasonId ?? seriesId) : null;
            logger?.LogInformation($"(Anidb) [fork fix] {forkEp.Series.Name}: season index {forkEp.Season.IndexNumber}, seasons {seasonCount}, season AniDB {seasonId?.ToString() ?? "-"}, series AniDB {seriesId?.ToString() ?? "-"} -> {(result != null ? "using AniDB " + result : "no override")}");
            return result;
        }

'''

CALL = '''
            { var forkFixId = ForkSingleSeasonSeriesAniDb(logger, video); if (forkFixId != null) return (forkFixId, null); }'''


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

    # Do not let a series-level AniList ID (which may point at season 1)
    # short-circuit the AniDB lookup for such single-season series.
    status_path = pathlib.Path(sys.argv[1]) / TARGET_STATUS
    status_src = status_path.read_text(encoding="utf-8")
    count = status_src.count(ANILIST_CHECK)
    if count < 1:
        print(f"ERROR: AniList shortcut not found in {TARGET_STATUS}.")
        return 1
    status_src = status_src.replace(ANILIST_CHECK, ANILIST_GUARD)

    path.write_text(src, encoding="utf-8")
    status_path.write_text(status_src, encoding="utf-8")
    print(f"Fix applied (AniList shortcut guarded in {count} place(s)).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
