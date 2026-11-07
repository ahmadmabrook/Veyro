-- Stripping the pinned search_path off a function, which is the D6.6 test 10 hijack vector.
ALTER FUNCTION plt01_api.resolve_placement(uuid) RESET search_path;
