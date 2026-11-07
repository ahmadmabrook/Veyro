-- The rule was anchored to a SET statement, so the function form walked past it.
SELECT set_config('search_path', 'plt01_platform', false);
