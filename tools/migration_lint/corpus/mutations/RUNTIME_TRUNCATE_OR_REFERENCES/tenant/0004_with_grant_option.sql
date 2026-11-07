-- Same violation with a trailing option clause. The grantee used to parse as the single token
-- "veyro_cp_app with grant option", which matched no runtime role and defeated four grant rules.
GRANT TRUNCATE ON plt01.brand_appearance TO veyro_cp_app WITH GRANT OPTION;
