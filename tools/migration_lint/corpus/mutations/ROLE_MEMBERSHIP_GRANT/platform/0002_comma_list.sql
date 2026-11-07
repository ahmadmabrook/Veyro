-- Same violation with two roles granted at once; the comma form used to fail the match entirely.
GRANT veyro_cp_platform, veyro_cp_migrator TO veyro_cp_app;
