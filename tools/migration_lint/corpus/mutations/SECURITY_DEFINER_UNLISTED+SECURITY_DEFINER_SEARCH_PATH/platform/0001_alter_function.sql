-- Making an existing function SECURITY DEFINER by ALTER, with no allowlist entry and no pinned
-- search_path. Both definer checks used to sit under CREATE FUNCTION only.
ALTER FUNCTION plt01_api.resolve_placement(uuid) SECURITY DEFINER;
