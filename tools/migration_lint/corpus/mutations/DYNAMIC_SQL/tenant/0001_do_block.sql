-- Mutation: DDL routed through a DO block. Its body is blanked out of the text the statement
-- rules read, so without this rule every other rule reports nothing for this file.
DO $mig$
BEGIN
    EXECUTE 'GRANT TRUNCATE ON plt01.brand_appearance TO veyro_cp_app';
    EXECUTE 'CREATE TABLE plt01.naked (id uuid)';
END
$mig$;
