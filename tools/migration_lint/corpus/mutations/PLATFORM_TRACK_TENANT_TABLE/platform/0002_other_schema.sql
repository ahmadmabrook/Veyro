-- The platform track owns plt01_platform and plt01_api only; any other schema is the wrong track.
CREATE TABLE plt01x.leaky (tenant_id uuid NOT NULL, data text);
